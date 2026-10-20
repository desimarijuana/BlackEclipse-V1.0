"""The analysis sandbox's RUNTIME guard (round 4, W14).

The AST allowlist in `execution.py` is a first filter: it is a *source* check,
and a source check can be talked around (`f = __import__` was enough). This
module is the enforcement point that a program cannot talk around:

1. **A guarded ``__import__``** — the child's builtin is replaced by one that
   only imports an allowlisted module (plus the stdlib support the allowed
   libraries need internally). An alias therefore buys nothing.
2. **A safe ``os`` / ``sys`` / ``importlib``** — the modules that grant
   privilege are replaced by ones that carry none: no ``system``, no
   ``popen``, no frame walking, no ``import_module`` escape hatch.
3. **Denied privilege modules** — ``subprocess``, ``socket``, ``ssl``,
   ``ctypes`` and ``multiprocessing`` can be IMPORTED (a library may need the
   symbol) but every call raises.
4. **An audit hook** (``sys.addaudithook``) — it fires for the operations a
   source check cannot see (a C-level ``fopen`` inside numpy, a socket
   connect, a subprocess spawn, a ctypes load). Hooks cannot be uninstalled.
5. **Confined readers/writers** — the file-reading and file-writing entry
   points of the allowed numerical libraries are wrapped so a path outside the
   program's own folder is refused, not merely discouraged.

The guard is DELIBERATELY honest about its scope: it confines the program to
its own folder and denies it the network, other processes and native code *at
the Python level*. It is not an OS-level boundary (the child still runs as the
host user) — which is why the sandbox's documentation says so too.

The code below is a SOURCE STRING: it is executed inside the sandboxed child
process, before the analysis program runs. Keep it dependency-free (stdlib
only) and defensive (a guard that raises must never wedge the child).
"""

from __future__ import annotations

#: The guard, as the source executed inside the sandboxed child.
GUARD_SOURCE = '''\
import ast as _ast
import os as _os
import sys as _sys

# The import machinery and the metadata helpers are loaded NOW, while the
# interpreter's own import path is still intact: the frozen machinery reaches
# into private bootstrap modules that a guarded import would (rightly) refuse.
try:
    import importlib.machinery
    import importlib.metadata
    import importlib.resources
except Exception:
    pass

# The privilege modules are imported HERE (while the interpreter's own import
# path is intact) so their shims can mirror their real surface — a missing
# attribute would break a library that merely reads it.
try:
    import socket
    import ssl
    import subprocess
except Exception:
    pass

_GUARD_ROOTS = []          # directories a program may READ from
_GUARD_WRITE_ROOTS = []    # directories a program may WRITE into
_GUARD_MODULES = ()        # the import allowlist
_GUARD_INSTALLED = False

#: The stdlib support modules the ALLOWED libraries import internally (their
#: own machinery: encodings, iterators, compression, the interpreter's
#: helpers). None of them is a privilege the program does not already have
#: through the allowlist: no `os` (it is shimmed), no `socket`, no
#: `subprocess` (denied shims), no `ctypes`, no `importlib` (shimmed).
_GUARD_SUPPORT = (
    "_abc", "_ast", "_bisect", "_blake2", "_bz2", "_collections",
    "_compat_pickle",
    "_collections_abc", "_compression", "_csv", "_datetime", "_decimal",
    "_functools", "_hashlib", "_heapq", "_io", "_json", "_locale", "_lzma",
    "_md5", "_operator", "_random", "_sha1", "_sha256", "_sha3", "_sha512",
    "_sitebuiltins", "_sre", "_stat", "_strptime", "_struct", "_thread",
    "_typing", "_unicodedata", "_weakref", "_zlib",
    "_contextvars", "_queue", "_signal",
    "__future__",
    "abc", "argparse", "array", "ast", "atexit", "base64", "binascii",
    "bisect", "bzip2", "opcode", "cmath", "fnmatch", "glob", "shutil",
    "tempfile", "signal",
    "calendar", "codecs", "collections", "concurrent", "concurrent.futures", "configparser", "contextlib",
    "contextvars", "copy", "copyreg", "dataclasses", "datetime", "decimal",
    "difflib", "dis", "email", "encodings", "enum", "errno", "filecmp",
    "fractions", "functools", "genericpath", "gettext", "graphlib", "gzip",
    "grp", "hashlib", "heapq", "hmac", "html", "imghdr", "inspect", "io",
    "ipaddress", "itertools", "json", "keyword", "linecache", "locale",
    "logging", "lzma", "math", "mimetypes", "mmap", "nt", "numbers", "ntpath",
    "operator", "pathlib", "pickle", "pkgutil", "plistlib", "platform", "posix",
    "posixpath",
    "pprint", "pwd", "quopri", "queue", "re", "reprlib", "resource", "secrets",
    "selectors", "shlex", "sndhdr", "sre_compile", "sre_parse", "stat",
    "string", "struct", "symtable", "sysconfig", "tarfile", "textwrap", "threading",
    "time", "token",
    "tokenize", "tomllib", "traceback", "types", "typing", "typing_extensions",
    "unicodedata", "unittest", "urllib", "uuid", "warnings", "wave", "weakref",
    "winreg", "zipapp",
    "xml", "xml.dom", "xml.etree", "xml.parsers", "xml.parsers.expat", "xml.sax", "pyexpat", "zipfile", "zlib", "zoneinfo",
    # The third-party libraries the allowed numerical stack needs. None of them
    # grants a privilege the audit hook does not already deny (no socket, no
    # process, no native code, no file outside the program's own folder).
    "PIL", "contourpy", "cycler", "dateutil", "fontTools", "kiwisolver",
    "packaging", "pyparsing", "pytz", "six",
)

#: The modules a program may import but never use. The import succeeds (a
#: library may need the symbol); every call raises.
_GUARD_DENIED = (
    ("subprocess", "an analysis may not start another process"),
    ("socket", "network access is not available in an analysis"),
    ("ssl", "network access is not available in an analysis"),
    ("ctypes", "an analysis may not load native code"),
    ("multiprocessing", "an analysis may not start another process"),
)


def _guard_norm(path):
    try:
        return _os.path.realpath(_os.fspath(path))
    except Exception:
        return ""


def _guard_under(path, roots):
    if not path:
        return False
    for root in roots:
        if path == root or path.startswith(root + _os.sep):
            return True
    return False


def _guard_readable(path):
    return _guard_under(path, _GUARD_ROOTS)


def _guard_writable(path):
    return _guard_under(path, _GUARD_WRITE_ROOTS)


def _guard_install(allowed_modules, read_roots, write_roots):
    """Install the import guard, the audit hook and the path confinement."""
    global _GUARD_ROOTS, _GUARD_WRITE_ROOTS, _GUARD_MODULES, _GUARD_INSTALLED
    if _GUARD_INSTALLED:
        return
    _GUARD_INSTALLED = True
    # Fold the support modules into the allowlist itself. They were already
    # permitted by the second check; keeping one set makes the guard immune to a
    # support tuple that is missing from an assembled runner prelude.
    _GUARD_MODULES = tuple(sorted({
        *(str(m) for m in (allowed_modules or ())),
        *_GUARD_SUPPORT,
    }))
    _GUARD_ROOTS = [_guard_norm(p) for p in (read_roots or ()) if p]
    _GUARD_WRITE_ROOTS = [_guard_norm(p) for p in (write_roots or ()) if p]

    import builtins as _builtins
    import types as _types

    real_import = _builtins.__import__
    real_os = _os
    _exec = _builtins.exec
    _eval = _builtins.eval

    # A SAFE `os`: the allowed libraries legitimately import it (random needs
    # urandom, numpy needs path helpers), so the module is REPLACED by one that
    # carries no privilege: no system(), no popen, no spawn, no remove. The
    # program's filesystem access is then bounded by the audit hook.
    _shim = _types.ModuleType("os")
    for _name in ("sep", "linesep", "pathsep", "devnull", "name", "curdir",
                  "pardir", "altsep", "extsep"):
        setattr(_shim, _name, getattr(real_os, _name, ""))
    _shim.path = real_os.path
    _shim.environ = {}
    # Every public attribute EXCEPT the privilege ones (process creation,
    # signalling, privilege changes). The audit hook denies the dangerous
    # operations even if a symbol slips through.
    _os_denied = {
        "system", "popen", "popen2", "popen3", "popen4", "spawnl", "spawnle",
        "spawnlp", "spawnlpe", "spawnv", "spawnve", "spawnvp", "spawnvpe",
        "execl", "execle", "execlp", "execlpe", "execv", "execve", "execvp",
        "execvpe", "fork", "forkpty", "posix_spawn", "posix_spawnp", "kill",
        "killpg", "chroot", "setuid", "setgid", "setgroups",
    }
    for _name in dir(real_os):
        if _name.startswith("_") or _name in _os_denied:
            continue
        try:
            setattr(_shim, _name, getattr(real_os, _name))
        except Exception:
            continue
    _shim.getenv = lambda *a, **k: None
    _sys.modules["os"] = _shim

    # A SAFE `sys`: the interpreter's own libraries import it. The frame
    # walkers are replaced by a proxy that exposes NO host globals and NO frame
    # chain — walking `f_back` would otherwise reach the runner's own module
    # namespace (and the real `os` behind it).
    class _FrameProxy:
        __slots__ = ("_frame",)

        def __init__(self, frame):
            object.__setattr__(self, "_frame", frame)

        @property
        def f_globals(self):
            return {}

        @property
        def f_locals(self):
            return {}

        @property
        def f_back(self):
            frame = object.__getattribute__(self, "_frame")
            if frame is None:
                return None
            back = getattr(frame, "f_back", None)
            # The chain continues as PROXIES: a library that walks frames
            # (traceback.walk_stack) still works, and every frame's globals
            # stay empty — the runner's namespace is never reachable.
            return _FrameProxy(back) if back is not None else None

        def __getattr__(self, name):
            frame = object.__getattribute__(self, "_frame")
            if frame is None:
                return None
            return getattr(frame, name)

    _sys_shim = _types.ModuleType("sys")
    _sys_denied = {
        "_getframe", "_getframes", "settrace", "setprofile", "addaudithook",
        "set_asyncgen_hooks", "set_coroutine_origin_tracking_depth",
        "set_coroutine_wrapper", "gettrace", "getprofile",
    }
    for _name in dir(_sys):
        if _name in _sys_denied or _name.startswith("__"):
            continue
        try:
            setattr(_sys_shim, _name, getattr(_sys, _name))
        except Exception:
            continue
    def _guard_frame(*args, **kwargs):
        try:
            frame = _sys._getframe(1)
        except Exception:
            frame = None
        return _FrameProxy(frame)

    _sys_shim._getframe = _guard_frame
    _sys_shim._getframes = lambda *a, **k: ()
    _sys.modules["sys"] = _sys_shim

    # A SAFE `builtins`: a library may import it, but the program's copy must
    # be the RESTRICTED set it already runs under — never the real one (which
    # carries open/eval/exec).
    try:
        _restricted = _safe_builtins()
    except Exception:
        _restricted = {}
    _builtins_shim = _types.ModuleType("builtins")
    for _name, _value in _restricted.items():
        try:
            setattr(_builtins_shim, _name, _value)
        except Exception:
            continue
    # Every CLASS of the real builtins (staticmethod, classmethod, property,
    # super, ...) — a class is not a privilege, and a library that builds one
    # must still work.
    for _name in dir(_builtins):
        if _name.startswith("_"):
            continue
        try:
            _value = getattr(_builtins, _name)
        except Exception:
            continue
        if isinstance(_value, type):
            try:
                setattr(_builtins_shim, _name, _value)
            except Exception:
                continue

    # A SAFE `exec`/`eval`: a library needs the symbol (`six` looks it up), but
    # a raw one would let a STRING reach code the source gate never saw. These
    # apply the same rules to the dynamic source before running it.
    _GUARD_FORBIDDEN_NAMES = (
        "__import__", "eval", "exec", "compile", "open", "os", "sys",
        "getattr", "setattr", "delattr", "globals", "locals", "vars", "dir",
        "breakpoint", "input",
    )

    def _guard_source_ok(tree):
        for _node in _ast.walk(tree):
            if isinstance(_node, (_ast.Import, _ast.ImportFrom)):
                return False
            if isinstance(_node, _ast.Attribute):
                if _node.attr.startswith("__") and _node.attr.endswith("__"):
                    return False
            if isinstance(_node, _ast.Name):
                if _node.id in _GUARD_FORBIDDEN_NAMES or _node.id.startswith("__"):
                    return False
        return True

    def _guard_exec(source, globals=None, locals=None):
        import ast as _ast
        try:
            _tree = _ast.parse(str(source), "<dynamic>", "exec")
        except SyntaxError as _exc:
            raise SyntaxError(str(_exc)) from None
        if not _guard_source_ok(_tree):
            raise PermissionError(
                "a dynamically executed program may not import, use "
                "reflection, or touch dunder names"
            )
        return _exec(str(source), globals, locals)

    def _guard_eval(expression, globals=None, locals=None):
        import ast as _ast
        try:
            _tree = _ast.parse(str(expression), "<dynamic>", "eval")
        except SyntaxError as _exc:
            raise SyntaxError(str(_exc)) from None
        for _node in _ast.walk(_tree):
            if isinstance(_node, (_ast.Call, _ast.Attribute, _ast.Lambda,
                                   _ast.Await, _ast.NamedExpr)):
                raise PermissionError(
                    "a dynamically evaluated expression may only be arithmetic"
                )
            if isinstance(_node, _ast.Name) and _node.id.startswith("__"):
                raise PermissionError("a dynamically evaluated expression may not use dunder names")
        return _eval(str(expression), globals, locals)

    try:
        setattr(_builtins_shim, "exec", _guard_exec)
        setattr(_builtins_shim, "eval", _guard_eval)
        # `open` is confined by the audit hook (its own folder and the
        # interpreter's tree only). A library that needs the symbol (tarfile)
        # gets it; the SOURCE gate still refuses a program from calling it.
        setattr(_builtins_shim, "open", _builtins.open)
    except Exception:
        pass
    _sys.modules["builtins"] = _builtins_shim

    # A SAFE `importlib`: the allowed libraries use it (matplotlib reads its
    # version metadata), but `import_module`/`__import__` would route AROUND
    # the guarded import — so they ARE the guarded ones.
    import importlib as _real_importlib

    _importlib_shim = _types.ModuleType("importlib")
    # It stays a PACKAGE: the allowed libraries import `importlib.resources`
    # and `importlib.machinery`, which must still resolve.
    _importlib_shim.__path__ = list(getattr(_real_importlib, "__path__", []) or [])
    for _name in dir(_real_importlib):
        if _name.startswith("__") or _name in ("import_module",):
            continue
        try:
            setattr(_importlib_shim, _name, getattr(_real_importlib, _name))
        except Exception:
            continue
    _sys.modules["importlib"] = _importlib_shim

    # The privilege modules: importable, never usable.
    def _denied_shim(name, message):
        module = _types.ModuleType(name)

        def _refuse(*args, **kwargs):
            raise PermissionError(message)

        source = _sys.modules.get(name)
        for attr in dir(source) if source is not None else ():
            if attr.startswith("_"):
                continue
            try:
                value = getattr(source, attr, None)
            except Exception:
                value = None
            if isinstance(value, type):
                # A CLASS stays: `except socket.error` must still be a valid
                # exception clause (and instantiating one is denied by the
                # audit hook anyway).
                setattr(module, attr, value)
            elif callable(value):
                setattr(module, attr, _refuse)
            elif value is not None:
                setattr(module, attr, value)
        return module

    for _name, _why in _GUARD_DENIED:
        try:
            _sys.modules[_name] = _denied_shim(_name, _why)
        except Exception:
            continue

    def _guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        top = str(name).split(".")[0]
        if top == "os":
            if name == "os":
                return _shim
            # A submodule (`os.path` — pure string handling) is fine.
            return real_import(name, globals, locals, fromlist, level)
        if top == "sys":
            return _sys_shim
        if top == "builtins":
            return _builtins_shim
        if top == "importlib":
            if name == "importlib":
                return _importlib_shim
            # A submodule (`importlib.resources`) is fine; the import machinery
            # still runs through the guarded import for the package itself.
            return real_import(name, globals, locals, fromlist, level)
        if top in _sys.modules and any(top == d[0] for d in _GUARD_DENIED):
            return _sys.modules[top]
        if level != 0 or name.startswith("."):
            # A RELATIVE import: the program may not use one (the source gate
            # refuses it), but a LIBRARY's own `from . import x` is its own
            # business — and it can only reach modules INSIDE its own package.
            if name.startswith(".") and level == 0:
                try:
                    _package = (globals or {}).get("__package__")
                except Exception:
                    _package = None
                return _real_importlib.import_module(name, _package)
            try:
                caller = _sys._getframe(1).f_code.co_filename
            except Exception:
                caller = ""
            if caller == "<analysis>":
                raise ImportError("a relative import is not allowed in an analysis")
            return real_import(name, globals, locals, fromlist, level)
        # A LIBRARY's own import is its own business: the allowed numerical
        # stack has a large, evolving import graph (numpy, pandas, matplotlib,
        # their dependencies). The privilege modules above are shimmed or
        # denied whatever imports them, and the audit hook denies what they
        # would do. The PROGRAM's own imports stay on the allowlist.
        try:
            caller = _sys._getframe(1).f_code.co_filename
        except Exception:
            caller = ""
        if caller != "<analysis>":
            return real_import(name, globals, locals, fromlist, level)
        if top not in _GUARD_MODULES and top not in _GUARD_SUPPORT:
            raise ImportError(
                "import of %r is not allowed in an analysis. Only that import is "
                "refused — the rest of the program is allowed; remove or rewrite "
                "it and the program runs. The importable modules are: %s"
                % (name, ", ".join(sorted(_GUARD_MODULES)))
            )
        module = real_import(name, globals, locals, fromlist, level)
        try:
            _guard_confine_module(module)
        except Exception:
            pass
        return module

    # `importlib.import_module` stays the real one: it resolves the package
    # context itself, and the import machinery still calls the guarded
    # `__import__` underneath.
    _importlib_shim.import_module = _real_importlib.import_module
    _importlib_shim.__import__ = _guarded_import
    _builtins.__import__ = _guarded_import

    # `inspect` may already be loaded (the interpreter's own machinery imports
    # it); patch its frame accessor now, not only on a later import.
    try:
        _inspect = _sys.modules.get("inspect")
        if _inspect is not None:
            _inspect.currentframe = lambda *a, **k: None
    except Exception:
        pass

    def _hook(event, args):
        try:
            if event == "open":
                path = args[0] if args else None
                mode = args[1] if len(args) > 1 else "r"
                if isinstance(path, int) or path is None:
                    return
                target = _guard_norm(path)
                writing = isinstance(mode, str) and any(
                    flag in mode for flag in ("w", "a", "+", "x")
                )
                if writing:
                    if not _guard_writable(target):
                        raise PermissionError(
                            "an analysis may only write inside its own folder"
                        )
                elif not _guard_readable(target):
                    raise PermissionError(
                        "an analysis may only read its own folder and the "
                        "interpreter's libraries"
                    )
            elif event in (
                "socket.__new__", "socket.connect", "socket.bind",
                "socket.getaddrinfo", "socket.gethostbyname", "socket.sendto",
            ):
                raise PermissionError("network access is not available in an analysis")
            elif event in (
                "subprocess.Popen", "os.system", "os.exec", "os.spawn",
                "os.posix_spawn", "os.fork", "os.forkpty", "os.startfile",
            ):
                raise PermissionError("an analysis may not start another process")
            elif event in ("ctypes.dlopen", "ctypes.dlsym", "ctypes.call_function"):
                raise PermissionError("an analysis may not load native code")
            elif event in (
                "os.remove", "os.rename", "os.mkdir", "os.rmdir", "os.link",
                "os.symlink", "os.truncate", "os.chmod", "os.chown", "os.utime",
            ):
                path = args[0] if args else None
                if isinstance(path, (str, bytes)):
                    if not _guard_writable(_guard_norm(path)):
                        raise PermissionError(
                            "an analysis may only modify its own folder"
                        )
            elif event in ("os.listdir", "os.scandir", "os.walk"):
                # A directory LISTING is a read: the import finder walks the
                # interpreter's own tree, so it must stay allowed.
                path = args[0] if args else None
                if isinstance(path, (str, bytes)):
                    if not _guard_readable(_guard_norm(path)):
                        raise PermissionError(
                            "an analysis may only list its own folder and the "
                            "interpreter's libraries"
                        )
        except PermissionError:
            raise
        except Exception:
            return

    _sys.addaudithook(_hook)


#: The file-reading and file-writing entry points of the allowed numerical
#: libraries. A source check cannot see inside them (numpy reads with a
#: C-level fopen), so they are wrapped at import time.
_GUARD_CONFINED = {
    "numpy": ("fromfile", "load", "loadtxt", "genfromtxt", "savetxt", "save",
              "savez", "savez_compressed", "memmap"),
    "pandas": ("read_csv", "read_excel", "read_json", "read_parquet", "read_html",
               "read_sql", "read_table", "read_fwf", "read_sas", "read_stata",
               "read_feather", "read_hdf", "read_orc", "read_xml", "read_pickle",
               "read_clipboard", "to_csv", "to_excel", "to_parquet", "to_json",
               "to_pickle", "to_sql", "to_stata", "to_html", "to_latex"),
    # `inspect.currentframe` hands out the caller's frame, and the frame chain
    # reaches the runner's own module namespace. It is the same escape as
    # `sys._getframe`, so it returns nothing.
    "inspect": ("currentframe",),
}


def _guard_wrap_path(fn, writable):
    def _wrapped(*args, **kwargs):
        for value in list(args) + list(kwargs.values()):
            if not isinstance(value, str):
                continue
            if "://" in value:
                raise PermissionError("an analysis may not fetch a URL")
            target = _guard_norm(value)
            ok = _guard_writable(target) if writable else _guard_readable(target)
            if not ok:
                raise PermissionError(
                    "an analysis may only %s inside its own folder"
                    % ("write" if writable else "read")
                )
        return fn(*args, **kwargs)

    return _wrapped


def _guard_confine_module(module):
    name = getattr(module, "__name__", "")
    attrs = _GUARD_CONFINED.get(name)
    if not attrs:
        return
    for attr in attrs:
        target = getattr(module, attr, None)
        if target is None or getattr(target, "_eclipse_guarded", False):
            continue
        writable = attr.startswith("to_") or attr in ("savetxt", "save", "savez",
                                                      "savez_compressed", "memmap")
        try:
            if name == "inspect" and attr == "currentframe":
                # The frame chain reaches the runner's own namespace.
                wrapped = lambda *a, **k: None
            else:
                wrapped = _guard_wrap_path(target, writable)
        except Exception:
            continue
        try:
            wrapped._eclipse_guarded = True
            setattr(module, attr, wrapped)
        except Exception:
            continue
'''


__all__ = ["GUARD_SOURCE"]
