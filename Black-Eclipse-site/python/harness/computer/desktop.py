"""Desktop provisioners — create, attach to, and tear down a session's desktop.

A `DesktopProvisioner` answers one question: *where does a session run?* The
`LocalDesktopProvisioner` shares the operator's single physical desktop (the
default, zero-config path). The isolated provisioners give a session its OWN
desktop instance so multiple agents can run at once without corrupting each
other:

  * `X11HeadlessProvisioner` — spawns a private `Xvfb` display per instance and
    binds a `LinuxX11Driver` to it. Real, and testable on any host via the
    injected process/socket probes.
  * `WindowsSandboxProvisioner` — declared; a host driver cannot attach to a
    Windows Sandbox session, so it reports unavailable honestly until a genuine
    attach path exists.

Every provisioner is honest: if its backend is absent the provisioner reports
`available: false` with a reason and the local shared desktop is used instead —
never a fabricated virtual desktop. `available_desktop_provider`/`build_provisioner`
return the provisioner so a caller can trust `headless_desktop` from the result.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


@dataclass
class DesktopInstance:
    """A live desktop a session drives. Owns its driver; the provisioner owns it."""

    id: str
    provider_id: str
    driver: Any
    ax: Any = None
    ocr: Any = None
    display: Optional[str] = None
    process: Any = None
    isolated: bool = False
    headless: bool = False
    created_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id, "provider": self.provider_id, "display": self.display,
            "isolated": self.isolated, "headless": self.headless,
            "driver": getattr(self.driver, "id", "unknown"), "createdAt": self.created_at,
            **self.metadata,
        }


class DesktopProvisioner:
    """Base provisioner. `available`/`isolated`/`headless` are honest flags."""

    id = "local"
    label = "Local desktop"
    available = True
    isolated = False
    headless = False

    def __init__(self, reason: str = "") -> None:
        self.reason = reason

    def describe(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "kind": self.id,
            "available": self.available, "isolated": self.isolated,
            "headless": self.headless,
            **({} if self.available else {"reason": self.reason}),
        }

    async def create(self, *, config: Any, base_driver: Any = None, base_ax: Any = None,
                     base_ocr: Any = None) -> DesktopInstance:
        raise NotImplementedError

    async def destroy(self, instance: DesktopInstance) -> None:
        return None


class LocalDesktopProvisioner(DesktopProvisioner):
    """The shared physical desktop: one instance wrapping the process driver.

    It does NOT own the driver (the manager does), so `destroy` is a no-op and the
    desktop stays available for the next session.
    """

    id = "local"
    label = "Local desktop (shared)"
    available = True
    isolated = False

    async def create(self, *, config: Any, base_driver: Any = None, base_ax: Any = None,
                     base_ocr: Any = None) -> DesktopInstance:
        return DesktopInstance(
            id=f"local-{uuid.uuid4().hex[:8]}", provider_id=self.id, driver=base_driver,
            ax=base_ax, ocr=base_ocr, isolated=False, headless=False,
        )


class NullDesktopProvisioner(DesktopProvisioner):
    id = "null"
    label = "No desktop provisioner"
    available = False

    def __init__(self, reason: str = "no desktop provisioner is available") -> None:
        super().__init__(reason)


class X11HeadlessProvisioner(DesktopProvisioner):
    """A private Xvfb display per session.

    `create` allocates a free display number, spawns `Xvfb :N -screen 0 WxHx24`,
    waits for the display socket, then builds and starts a `LinuxX11Driver` bound
    to that DISPLAY. `destroy` stops the driver and terminates the server.

    The process spawn and socket probe are injectable so the full lifecycle is
    testable without Xvfb installed; on a Linux host with Xvfb the same code runs
    for real.
    """

    id = "x11"
    label = "Headless X11 (Xvfb)"
    isolated = True
    headless = True

    def __init__(
        self,
        *,
        display_base: int = 99,
        screen: str = "1920x1080x24",
        process_factory: Optional[Callable[[str, str], Any]] = None,
        socket_exists: Optional[Callable[[str], bool]] = None,
        xvfb_path: Optional[str] = None,
        start_timeout: float = 10.0,
    ) -> None:
        self.display_base = display_base
        self.screen = screen
        self._process_factory = process_factory
        self._socket_exists = socket_exists or (lambda path: os.path.exists(path))
        self._xvfb_path = xvfb_path
        self.start_timeout = start_timeout
        self.available = False
        self.reason = ""
        self._probe()

    def _probe(self) -> None:
        if not sys.platform.startswith("linux") and self._process_factory is None:
            self.reason = "the Xvfb provisioner requires Linux"
            return
        path = self._xvfb_path or _which("Xvfb")
        if path is None and self._process_factory is None:
            self.reason = "Xvfb isn't installed (apt install xvfb)"
            return
        self._xvfb_path = path
        self.available = True

    def _free_display(self) -> int:
        for number in range(self.display_base, self.display_base + 100):
            if not self._socket_exists(f"/tmp/.X11-unix/X{number}"):
                return number
        raise RuntimeError("no free X display number")

    def _spawn(self, number: int) -> Any:
        argv = f"{self._xvfb_path} :{number} -screen 0 {self.screen} -nolisten tcp"
        if self._process_factory is not None:
            return self._process_factory(argv, f":{number}")
        import subprocess  # noqa: PLC0415

        return subprocess.Popen(argv.split(), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def _wait_ready(self, number: int) -> bool:
        deadline = time.monotonic() + self.start_timeout
        while time.monotonic() < deadline:
            if self._socket_exists(f"/tmp/.X11-unix/X{number}"):
                return True
            await asyncio.sleep(0.1)
        return False

    async def create(self, *, config: Any, base_driver: Any = None, base_ax: Any = None,
                     base_ocr: Any = None) -> DesktopInstance:
        if not self.available:
            raise RuntimeError(self.reason)
        number = self._free_display()
        display = f":{number}"
        process = self._spawn(number)
        if not await self._wait_ready(number):
            await self._terminate(process)
            raise RuntimeError(f"Xvfb display {display} didn't become ready")
        from .drivers.linux import LinuxX11Driver  # noqa: PLC0415

        driver = LinuxX11Driver(display=display)
        await driver.start()
        return DesktopInstance(
            id=f"x11-{uuid.uuid4().hex[:8]}", provider_id=self.id, driver=driver,
            ax=getattr(driver, "_ax", None), display=display, process=process,
            isolated=True, headless=True, metadata={"display": display},
        )

    async def _terminate(self, process: Any) -> None:
        if process is None:
            return
        try:
            process.terminate()
        except Exception:  # noqa: BLE001
            pass

    async def destroy(self, instance: DesktopInstance) -> None:
        try:
            await instance.driver.stop()
        except Exception:  # noqa: BLE001
            pass
        await self._terminate(instance.process)


class WindowsSandboxProvisioner(DesktopProvisioner):
    """A Windows Sandbox desktop, attached through its contained window.

    Windows Sandbox renders its desktop inside a host window (`WindowsSandboxClient`).
    This provisioner launches the sandbox and attaches a `WindowDriver` to that
    window, so capture/input are scoped to the guest desktop and never touch the
    host session. It is best-effort: the client must be present, the sandbox must
    be enabled (Windows Pro/Enterprise + virtualization), and keyboard focus must
    reach the client — all checked honestly, never assumed.
    """

    id = "windows_sandbox"
    label = "Windows Sandbox (isolated)"
    isolated = True
    headless = True

    def __init__(
        self,
        *,
        wsb_path: Optional[str] = None,
        config_file: str = "computer_sandbox.wsb",
        launch: bool = True,
        process_factory: Optional[Callable[[str], Any]] = None,
        window_probe: Optional[Callable[[str], Any]] = None,
    ) -> None:
        self._wsb = wsb_path or _which("WindowsSandbox.exe") or _sandbox_default_path()
        self._config_file = config_file
        self._launch = launch
        self._process_factory = process_factory
        self._window_probe = window_probe or _win32_find_window
        self.available = False
        self.reason = ""
        self._probe()

    def _probe(self) -> None:
        if not sys.platform == "win32" and self._process_factory is None:
            self.reason = "the Windows Sandbox provisioner requires Windows"
            return
        if self._wsb is None and self._process_factory is None:
            self.reason = "Windows Sandbox isn't installed (needs Windows Pro/Enterprise + virtualization)"
            return
        self.available = True

    def _spawn(self) -> Any:
        if self._process_factory is not None:
            return self._process_factory(self._wsb or "WindowsSandbox.exe")
        import subprocess  # noqa: PLC0415

        return subprocess.Popen([self._wsb], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def _wait_attach(self, title_hint: str, *, timeout: float = 60.0) -> Any:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            window_id = self._window_probe(title_hint)
            if window_id is not None:
                return window_id
            await asyncio.sleep(0.5)
        return None

    async def create(self, *, config: Any, base_driver: Any = None, base_ax: Any = None,
                     base_ocr: Any = None) -> DesktopInstance:
        if not self.available:
            raise RuntimeError(self.reason)
        if base_driver is None:
            from ..drivers import build_driver  # noqa: PLC0415

            base_driver = build_driver("windows")
            await base_driver.start()
        process = self._spawn() if self._launch else None
        window_id = await self._wait_attach("windows sandbox")
        if window_id is None:
            raise RuntimeError(
                "launched Windows Sandbox but couldn't attach to its desktop window "
                "(the client may not be running, or virtualization is disabled)"
            )
        from .drivers.window import WindowDriver  # noqa: PLC0415

        driver = WindowDriver(base_driver, window_id=window_id, title_hint="windows sandbox",
                              input="foreground", isolated=True, headless=True, ocr=base_ocr)
        await driver.start()
        return DesktopInstance(
            id=f"sandbox-{uuid.uuid4().hex[:8]}", provider_id=self.id, driver=driver,
            process=process, isolated=True, headless=True, metadata={"window": window_id},
        )

    async def _terminate(self, process: Any) -> None:
        if process is None:
            return
        try:
            process.terminate()
        except Exception:  # noqa: BLE001
            pass

    async def destroy(self, instance: DesktopInstance) -> None:
        try:
            await instance.driver.stop()
        except Exception:  # noqa: BLE001
            pass
        await self._terminate(instance.process)


class RdpDesktopProvisioner(DesktopProvisioner):
    """An RDP session driven through the client window.

    Spawns `mstsc` against a host (or an `.rdp` file), waits for the client window,
    and attaches a `WindowDriver` so input/capture target the remote session. All
    credentials come from the operator's `.rdp`/CMDKEY setup — Eclipse never
    handles a password itself.
    """

    id = "rdp"
    label = "RDP session (isolated)"
    isolated = True
    headless = True

    def __init__(
        self,
        *,
        host: str = "",
        rdp_file: str = "",
        mstsc_path: Optional[str] = None,
        process_factory: Optional[Callable[[list[str]], Any]] = None,
        window_probe: Optional[Callable[[str], Any]] = None,
        attach_timeout: float = 60.0,
    ) -> None:
        self._host = host
        self._rdp_file = rdp_file
        self._mstsc = mstsc_path or _which("mstsc.exe") or _which("mstsc")
        self._process_factory = process_factory
        self._window_probe = window_probe or _win32_find_window
        self._attach_timeout = attach_timeout
        self.available = False
        self.reason = ""
        self._probe()

    def _probe(self) -> None:
        if not self._host and not self._rdp_file and self._process_factory is None:
            self.reason = "RDP needs an `rdp.host` or `rdp.file` in configuration"
            return
        if self._mstsc is None and self._process_factory is None:
            self.reason = "the RDP client (`mstsc`) isn't installed"
            return
        self.available = True

    def _spawn(self) -> Any:
        argv = [self._mstsc] if self._mstsc else ["mstsc"]
        if self._rdp_file:
            argv.append(self._rdp_file)
        elif self._host:
            argv += ["/v:" + self._host]
        if self._process_factory is not None:
            return self._process_factory(argv)
        import subprocess  # noqa: PLC0415

        return subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    async def _wait_attach(self) -> Any:
        deadline = time.monotonic() + self._attach_timeout
        hint = self._host.lower() or "remote desktop"
        while time.monotonic() < deadline:
            window_id = self._window_probe(hint)
            if window_id is not None:
                return window_id
            await asyncio.sleep(0.5)
        return None

    async def create(self, *, config: Any, base_driver: Any = None, base_ax: Any = None,
                     base_ocr: Any = None) -> DesktopInstance:
        if not self.available:
            raise RuntimeError(self.reason)
        if base_driver is None:
            from ..drivers import build_driver  # noqa: PLC0415

            base_driver = build_driver("windows")
            await base_driver.start()
        process = self._spawn()
        window_id = await self._wait_attach()
        if window_id is None:
            raise RuntimeError("spawned the RDP client but couldn't attach to its session window")
        from .drivers.window import WindowDriver  # noqa: PLC0415

        driver = WindowDriver(base_driver, window_id=window_id, app_hint="remote desktop",
                              input="foreground", isolated=True, headless=True, ocr=base_ocr)
        await driver.start()
        return DesktopInstance(
            id=f"rdp-{uuid.uuid4().hex[:8]}", provider_id=self.id, driver=driver,
            process=process, isolated=True, headless=True, metadata={"window": window_id},
        )

    async def _terminate(self, process: Any) -> None:
        if process is None:
            return
        try:
            process.terminate()
        except Exception:  # noqa: BLE001
            pass

    async def destroy(self, instance: DesktopInstance) -> None:
        try:
            await instance.driver.stop()
        except Exception:  # noqa: BLE001
            pass
        await self._terminate(instance.process)


class WaylandHeadlessProvisioner(DesktopProvisioner):
    """A private headless Wayland desktop.

    Wayland has no in-session virtual-display API, but wlroots exposes a **headless
    backend** via the `wlheadless-run` launcher (or a compositor's own
    `headless`/`--headless` backend, e.g. `sway`). This provisioner spawns a
    nested headless compositor on a private socket, then attaches a `WaylandDriver`
    (grim for capture, ydotool for input) to that socket. It is honest: with no
    launcher present, or when attaching to an existing session is requested, it
    reports accordingly and never fakes a display.
    """

    id = "wayland"
    label = "Headless Wayland (nested compositor)"
    isolated = True
    headless = True

    def __init__(
        self,
        *,
        launcher: Optional[str] = None,
        compositor: Optional[str] = None,
        process_factory: Optional[Callable[[list[str], dict[str, str]], Any]] = None,
        socket_exists: Optional[Callable[[str], bool]] = None,
        start_timeout: float = 15.0,
    ) -> None:
        # `wlheadless-run` wraps an existing compositor; else use a compositor that
        # has its own headless backend (sway --headless / weston --backend=headless).
        self._launcher = launcher or _which("wlheadless-run")
        self._compositor = compositor or (_which("sway") or _which("weston"))
        self._process_factory = process_factory
        self._socket_exists = socket_exists or (lambda path: os.path.exists(path))
        self.start_timeout = start_timeout
        if not sys.platform.startswith("linux") and process_factory is None:
            self.available = False
            self.reason = "the Wayland headless provisioner requires Linux"
        elif self._launcher is None and self._compositor is None and process_factory is None:
            self.available = False
            self.reason = "no Wayland headless compositor is available (install `wlheadless-run`, `sway`, or `weston`)"
        else:
            self.available = True
            self.reason = ""
        super().__init__(self.reason)

    def _spawn(self, socket: str, runtime_dir: str) -> tuple[Any, dict[str, str]]:
        env = {
            **os.environ,
            "XDG_RUNTIME_DIR": runtime_dir,
            "WAYLAND_DISPLAY": socket,
            # A headless compositor does not need a real seat for capture; input is
            # injected via ydotool (uinput), independent of the compositor seat.
            "WLR_BACKENDS": "headless",
            "WLR_LIBINPUT_NO_DEVICES": "1",
        }
        if self._launcher and self._compositor:
            argv = [self._launcher, self._compositor]
        elif self._compositor:
            argv = [self._compositor, "--headless"] if self._compositor.endswith("sway") else [self._compositor, "--backend=headless"]
        else:
            argv = [self._launcher]
        if self._process_factory is not None:
            return self._process_factory(argv, env), env
        import subprocess  # noqa: PLC0415

        return subprocess.Popen(argv, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL), env

    async def _wait_ready(self, socket: str, runtime_dir: str) -> bool:
        deadline = time.monotonic() + self.start_timeout
        path = os.path.join(runtime_dir, socket)
        while time.monotonic() < deadline:
            if self._socket_exists(path):
                return True
            await asyncio.sleep(0.2)
        return False

    async def create(self, *, config: Any, base_driver: Any = None, base_ax: Any = None,
                     base_ocr: Any = None) -> DesktopInstance:
        if not self.available:
            raise RuntimeError(self.reason)
        runtime_dir = _private_runtime_dir()
        socket = f"wayland-{uuid.uuid4().hex[:6]}"
        process, env = self._spawn(socket, runtime_dir)
        if not await self._wait_ready(socket, runtime_dir):
            await self._terminate(process)
            raise RuntimeError(f"the headless Wayland compositor ({socket}) didn't become ready")
        from .drivers.wayland import WaylandDriver  # noqa: PLC0415

        driver = WaylandDriver(display=socket)
        await driver.start()
        return DesktopInstance(
            id=f"wayland-{uuid.uuid4().hex[:8]}", provider_id=self.id, driver=driver,
            display=socket, process=process, isolated=True, headless=True,
            metadata={"display": socket, "runtimeDir": runtime_dir},
        )

    async def _terminate(self, process: Any) -> None:
        if process is None:
            return
        try:
            process.terminate()
        except Exception:  # noqa: BLE001
            pass

    async def destroy(self, instance: DesktopInstance) -> None:
        try:
            await instance.driver.stop()
        except Exception:  # noqa: BLE001
            pass
        await self._terminate(instance.process)


def _private_runtime_dir() -> str:
    import tempfile  # noqa: PLC0415

    path = tempfile.mkdtemp(prefix="eclipse-wayland-")
    try:
        os.chmod(path, 0o700)
    except Exception:  # noqa: BLE001
        pass
    return path


# The provisioners Eclipse knows how to build, in preference order per platform.
PROVISIONERS: dict[str, type[DesktopProvisioner]] = {
    "local": LocalDesktopProvisioner,
    "x11": X11HeadlessProvisioner,
    "wayland": WaylandHeadlessProvisioner,
    "windows_sandbox": WindowsSandboxProvisioner,
    "rdp": RdpDesktopProvisioner,
}


def build_provisioner(config: Any = None, *, want: Optional[str] = None) -> DesktopProvisioner:
    """Build the provisioner for `config`.

    `isolation=off` (default) ⇒ the local shared desktop. `isolation=auto` picks
    the platform's isolated backend (Xvfb on Linux; Windows Sandbox on Windows),
    which is used only if genuinely available; otherwise it falls back to local.
    An explicit `want` (config.isolation_provider) overrides the platform default.
    """
    if config is None:
        from .config import computer_config  # noqa: PLC0415

        config = computer_config()
    isolation = getattr(config, "isolation", "off")
    if want is None:
        want = getattr(config, "isolation_provider", "auto")
    if isolation == "off" and want in (None, "auto", "local"):
        return LocalDesktopProvisioner()

    choice = (want or "auto").strip().lower()
    if choice == "auto":
        choice = "x11" if sys.platform.startswith("linux") else "windows_sandbox"
    cls = PROVISIONERS.get(choice)
    if cls is None:
        return LocalDesktopProvisioner()
    if cls is LocalDesktopProvisioner:
        return LocalDesktopProvisioner()
    try:
        provisioner = _construct(cls, config)
    except Exception:  # noqa: BLE001 - a broken backend falls back to local
        return LocalDesktopProvisioner()
    if provisioner.available:
        return provisioner
    # An isolated backend that isn't reachable falls back to the local desktop.
    return LocalDesktopProvisioner()


def _construct(cls: type[DesktopProvisioner], config: Any) -> DesktopProvisioner:
    """Build `cls` with the config fields that apply to it."""
    kwargs: dict[str, Any] = {}
    if cls is X11HeadlessProvisioner:
        kwargs = {"display_base": getattr(config, "headless_display_base", 99),
                  "screen": getattr(config, "headless_screen", "1920x1080x24")}
    elif cls is WaylandHeadlessProvisioner:
        kwargs = {}
    elif cls is RdpDesktopProvisioner:
        kwargs = {"host": getattr(config, "rdp_host", ""), "rdp_file": getattr(config, "rdp_file", "")}
    return cls(**kwargs)


def available_desktop_provider(config: Any = None) -> DesktopProvisioner:
    """The provisioner for the configured isolation mode."""
    if config is None:
        from .config import computer_config  # noqa: PLC0415

        config = computer_config()
    return build_provisioner(config)


def _which(binary: str) -> Optional[str]:
    import shutil  # noqa: PLC0415

    return shutil.which(binary)


def _sandbox_default_path() -> Optional[str]:
    import os  # noqa: PLC0415

    candidates = [
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "WindowsSandbox.exe"),
    ]
    for candidate in candidates:
        if os.path.exists(candidate):
            return candidate
    return None


def _win32_find_window(title_hint: str) -> Optional[str]:
    """Find a top-level window whose title/app contains `title_hint`, or None.

    Uses the Win32 driver's enumeration when available; returns None elsewhere so a
    caller (or a test with an injected probe) can supply its own.
    """
    if sys.platform != "win32":
        return None
    try:
        from .drivers import build_driver  # noqa: PLC0415

        driver = build_driver("windows")
        hint = (title_hint or "").lower()
        for window in driver.list_windows():
            if hint and hint in f"{window.title} {window.app}".lower():
                return window.id
    except Exception:  # noqa: BLE001
        return None
    return None


__all__ = [
    "DesktopInstance",
    "DesktopProvisioner",
    "LocalDesktopProvisioner",
    "NullDesktopProvisioner",
    "PROVISIONERS",
    "RdpDesktopProvisioner",
    "WaylandHeadlessProvisioner",
    "WindowsSandboxProvisioner",
    "X11HeadlessProvisioner",
    "available_desktop_provider",
    "build_provisioner",
]
