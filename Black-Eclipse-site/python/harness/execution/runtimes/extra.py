"""Additional language runtimes: Go, Rust, Java, C#, C, C++, PHP, Ruby.

Each adapter reports `UNAVAILABLE` honestly when its toolchain is not installed —
it never falls back to running the source through a different interpreter. Where a
language has a single-file run mode (Go `go run`, Java's single-file source mode,
PHP, Ruby) inline code is supported; where compilation is mandatory (Rust, C,
C++) inline code is refused with a plain sentence pointing at file/project
execution, and `build`/`test` operate on the project.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

from ..projects import ProjectInfo
from .base import BaseRuntime, PreparedCommand, RuntimeUnavailable


class _NoInline:
    """Mixin: a compile-required language with no single-file run mode."""

    def _refuse_inline(self) -> None:
        raise RuntimeUnavailable(
            f"{self.language} has to be built before it runs; give me a project or a file to build.",
            code="INLINE_NOT_SUPPORTED",
        )


class GoRuntime(BaseRuntime):
    language = "go"
    name = "GoRuntime"
    aliases = ("golang",)

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return self._resolve_on_path("go", "go.exe")

    def available(self) -> bool:
        return bool(self.resolve(None))

    def _env(self, root: Path) -> dict[str, str]:
        cache = self._tool_cache("go")
        # Go creates GOCACHE/GOMODCACHE/GOPATH itself, but GOTMPDIR must exist
        # (Windows `go` fails with "creating work dir" otherwise).
        (cache / "tmp").mkdir(parents=True, exist_ok=True)
        return {
            "GOFLAGS": "-mod=mod",
            "GOCACHE": str(cache / "build"),
            "GOMODCACHE": str(cache / "mod"),
            "GOTMPDIR": str(cache / "tmp"),
            "GOPATH": str(cache / "path"),
        }

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        go = self.resolve(None)
        if not go:
            raise RuntimeUnavailable("Go isn't installed on this computer.")
        if getattr(request, "code", ""):
            staged = self._stage(workdir, "main.go", request.code)
            return PreparedCommand(argv=[go, "run", str(staged), *list(getattr(request, "args", []) or [])],
                                   cwd=workdir, env=self._env(workdir), description="go run inline", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "") or "main.go"
        target = (root / entrypoint).resolve()
        return PreparedCommand(argv=[go, "run", str(target), *list(getattr(request, "args", []) or [])],
                               cwd=root, env=self._env(root), description=f"go run {entrypoint}")

    def build(self, root, project, workdir):
        go = self.resolve(project)
        if not go:
            return None
        return PreparedCommand(argv=[go, "build", "./..."], cwd=root, env=self._env(root), description="go build")

    def test(self, root, project, test_policy, workdir):
        go = self.resolve(project)
        if not go:
            return None
        return PreparedCommand(argv=[go, "test", "./..."], cwd=root, env=self._env(root), description="go test")

    def discover_tests(self, root, project):
        return [rel for rel in self._iter_files(root, (".go",), limit=3000) if rel.endswith("_test.go")][:500]


class RustRuntime(_NoInline, BaseRuntime):
    language = "rust"
    name = "RustRuntime"
    aliases = ("rs",)

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        import os

        # Prefer the REAL cargo binary. `cargo` on PATH under rustup is a proxy
        # that fails ("no default is configured") when RUSTUP_HOME/CARGO_HOME are
        # scrubbed — so resolve the toolchain's own bin/cargo when we can find it.
        home = os.environ.get("CARGO_HOME", "")
        if home:
            candidate = Path(home) / "bin" / ("cargo.exe" if os.name == "nt" else "cargo")
            if candidate.is_file():
                return str(candidate)
        rustup = os.environ.get("RUSTUP_HOME", "")
        if rustup:
            toolchains = Path(rustup) / "toolchains"
            if toolchains.is_dir():
                for toolchain in toolchains.iterdir():
                    candidate = toolchain / "bin" / ("cargo.exe" if os.name == "nt" else "cargo")
                    if candidate.is_file():
                        return str(candidate)
        return self._resolve_on_path("cargo", "cargo.exe")

    def available(self) -> bool:
        return bool(self.resolve(None))

    def _env(self, root: Path) -> dict[str, str]:
        import os

        env: dict[str, str] = {}
        for key in ("RUSTUP_HOME", "CARGO_HOME"):
            if os.environ.get(key):
                env[key] = os.environ[key]
        # A toolchain cache so cargo never writes into the repo.
        env.setdefault("CARGO_TARGET_DIR", str(self._tool_cache("rust") / "target"))
        return env

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        if getattr(request, "code", ""):
            self._refuse_inline()
        cargo = self.resolve(None)
        if not cargo:
            raise RuntimeUnavailable("Rust isn't installed on this computer.")
        if not (root / "Cargo.toml").is_file():
            raise RuntimeUnavailable("There's no Cargo project here to run.", code="PROJECT_NOT_FOUND")
        return PreparedCommand(argv=[cargo, "run", "--quiet"], cwd=root, env=self._env(root), description="cargo run")

    def build(self, root, project, workdir):
        cargo = self.resolve(project)
        if not cargo or not (root / "Cargo.toml").is_file():
            return None
        return PreparedCommand(argv=[cargo, "build", "--quiet"], cwd=root, env=self._env(root), description="cargo build")

    def test(self, root, project, test_policy, workdir):
        cargo = self.resolve(project)
        if not cargo or not (root / "Cargo.toml").is_file():
            return None
        return PreparedCommand(argv=[cargo, "test", "--quiet"], cwd=root, env=self._env(root), description="cargo test")


class JavaRuntime(BaseRuntime):
    language = "java"
    name = "JavaRuntime"
    aliases = ("jvm",)

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return self._resolve_on_path("java", "java.exe")

    def available(self) -> bool:
        return bool(self.resolve(None))

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        java = self.resolve(None)
        if not java:
            raise RuntimeUnavailable("Java isn't installed on this computer.")
        if getattr(request, "code", ""):
            # Java 11+ single-file source mode: `java Main.java`.
            staged = self._stage(workdir, "Main.java", request.code)
            return PreparedCommand(argv=[java, str(staged), *list(getattr(request, "args", []) or [])],
                                   cwd=workdir, env={}, description="java single-file", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "") or "Main.java"
        target = (root / entrypoint).resolve()
        return PreparedCommand(argv=[java, str(target), *list(getattr(request, "args", []) or [])],
                               cwd=root, env={}, description=f"java {entrypoint}")

    def build(self, root, project, workdir):
        if (root / "pom.xml").is_file() and (mvn := self._resolve_on_path("mvn", "mvn.cmd")):
            return PreparedCommand(argv=[mvn, "-q", "-DskipTests", "package"], cwd=root, env={}, description="maven package")
        if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
            gradle = self._resolve_on_path("gradle", "gradle.bat")
            if gradle:
                return PreparedCommand(argv=[gradle, "-q", "assemble"], cwd=root, env={}, description="gradle assemble")
        javac = self._resolve_on_path("javac", "javac.exe")
        sources = list(self._iter_files(root, (".java",), limit=200))
        if javac and sources:
            return PreparedCommand(argv=[javac, "-d", str(workdir / "classes"), *sources[:50]],
                                   cwd=root, env={}, description="javac")
        return None

    def test(self, root, project, test_policy, workdir):
        if (root / "pom.xml").is_file() and (mvn := self._resolve_on_path("mvn", "mvn.cmd")):
            return PreparedCommand(argv=[mvn, "-q", "test"], cwd=root, env={}, description="maven test")
        if (root / "build.gradle").is_file() or (root / "build.gradle.kts").is_file():
            gradle = self._resolve_on_path("gradle", "gradle.bat")
            if gradle:
                return PreparedCommand(argv=[gradle, "-q", "test"], cwd=root, env={}, description="gradle test")
        return None


class CSharpRuntime(_NoInline, BaseRuntime):
    language = "csharp"
    name = "CSharpRuntime"
    aliases = ("cs", "dotnet", "c#")

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return self._resolve_on_path("dotnet", "dotnet.exe")

    def available(self) -> bool:
        return bool(self.resolve(None))

    def _has_project(self, root: Path) -> bool:
        return any(root.glob("*.csproj")) or any(root.glob("*.sln"))

    def _env(self, root: Path) -> dict[str, str]:
        home = self._tool_cache("dotnet")
        (home / "packages").mkdir(parents=True, exist_ok=True)
        dotnet = self.resolve(None)
        env = self._platform_env()
        env.update({
            "DOTNET_CLI_TELEMETRY_OPTOUT": "1",
            "DOTNET_NOLOGO": "1",
            "DOTNET_SKIP_FIRST_TIME_EXPERIENCE": "1",
            "DOTNET_CLI_HOME": str(home),
            "NUGET_PACKAGES": str(home / "packages"),
            "DOTNET_ROOT": str(Path(dotnet).parent) if dotnet else "",
        })
        return env

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        if getattr(request, "code", ""):
            self._refuse_inline()
        dotnet = self.resolve(None)
        if not dotnet:
            raise RuntimeUnavailable("The .NET SDK isn't installed on this computer.")
        if not self._has_project(root):
            raise RuntimeUnavailable("There's no .NET project here to run.", code="PROJECT_NOT_FOUND")
        return PreparedCommand(argv=[dotnet, "run", "--project", str(root)], cwd=root,
                               env=self._env(root), description="dotnet run")

    def build(self, root, project, workdir):
        dotnet = self.resolve(project)
        if not dotnet or not self._has_project(root):
            return None
        return PreparedCommand(argv=[dotnet, "build", "--nologo", "-v", "quiet"], cwd=root,
                               env=self._env(root), description="dotnet build")

    def test(self, root, project, test_policy, workdir):
        dotnet = self.resolve(project)
        if not dotnet or not self._has_project(root):
            return None
        return PreparedCommand(argv=[dotnet, "test", "--nologo", "-v", "quiet"], cwd=root,
                               env=self._env(root), description="dotnet test")


class _CFamilyRuntime(_NoInline, BaseRuntime):
    """Shared shape for C and C++ (a real compiler is required)."""

    compiler_candidates: tuple[str, ...] = ()
    source_suffixes: tuple[str, ...] = ()

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return self._resolve_on_path(*self.compiler_candidates)

    def available(self) -> bool:
        return bool(self.resolve(None))

    def _sources(self, root: Path) -> list[str]:
        return list(self._iter_files(root, self.source_suffixes, limit=200))

    def _primary_source(self, root: Path, entrypoint: str) -> str:
        if entrypoint and Path(entrypoint).suffix.casefold() in self.source_suffixes:
            return entrypoint
        for candidate in self._sources(root):
            if Path(candidate).name.casefold() in ("main.c", "main.cpp", "main.cc", "main.cxx"):
                return candidate
        sources = self._sources(root)
        return sources[0] if sources else ""

    def _binary_name(self, source: str) -> str:
        stem = Path(source).stem
        return f"{stem}.exe" if os.name == "nt" else stem

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        if getattr(request, "code", ""):
            self._refuse_inline()
        entrypoint = getattr(request, "entrypoint", "")
        if entrypoint and Path(entrypoint).suffix.casefold() in self.source_suffixes:
            entrypoint = self._binary_name(entrypoint)  # a source name means its built binary
        if not entrypoint:
            source = self._primary_source(root, "")
            if source:
                entrypoint = self._binary_name(source)
        if not entrypoint:
            raise RuntimeUnavailable("There's no compiled program here to run.", code="PROJECT_NOT_FOUND")
        target = (root / entrypoint).resolve()
        if not target.is_file():
            raise RuntimeUnavailable(
                f"{entrypoint} hasn't been built yet; run a build first.",
                code="PROJECT_NOT_FOUND",
            )
        return PreparedCommand(argv=[str(target), *list(getattr(request, "args", []) or [])],
                               cwd=root, env={}, description=f"run {entrypoint}")

    def build(self, root: Path, project: Optional[ProjectInfo], workdir: Path):
        compiler = self.resolve(project)
        if (root / "CMakeLists.txt").is_file() and (cmake := self._resolve_on_path("cmake", "cmake.exe")):
            build_dir = workdir / "cmake-build"
            return PreparedCommand(
                argv=[cmake, "-S", str(root), "-B", str(build_dir)], cwd=root, env={},
                description="cmake configure",
            )
        make = self._resolve_on_path("make", "mingw32-make", "nmake")
        if make and ((root / "Makefile").is_file() or (root / "makefile").is_file()):
            return PreparedCommand(argv=[make], cwd=root, env={}, description="make")
        # No build system: compile the primary source into the workspace so a later
        # RUN can execute it. This is what makes a bare `.c`/`.cpp` usable.
        if not compiler:
            return None
        source = self._primary_source(root, "")
        if not source:
            return None
        output = (root / self._binary_name(source)).resolve()
        argv = [compiler, (root / source).resolve().as_posix(), "-O0", "-o", output.as_posix()]
        if self.language == "cpp":
            argv[2:2] = ["-std=c++17"]
        return PreparedCommand(argv=argv, cwd=root, env={}, description=f"compile {source}")

    def test(self, root, project, test_policy, workdir):
        make = self._resolve_on_path("make", "mingw32-make", "nmake")
        if make and ((root / "Makefile").is_file() or (root / "makefile").is_file()):
            return PreparedCommand(argv=[make, "test"], cwd=root, env={}, description="make test")
        return None


class CRuntime(_CFamilyRuntime):
    language = "c"
    name = "CRuntime"
    compiler_candidates = ("gcc", "clang", "cl", "gcc.exe", "clang.exe")
    source_suffixes = (".c", ".h")


class CppRuntime(_CFamilyRuntime):
    language = "cpp"
    name = "CppRuntime"
    aliases = ("c++", "cplusplus")
    compiler_candidates = ("g++", "clang++", "cl", "g++.exe", "clang++.exe")
    source_suffixes = (".cpp", ".cc", ".cxx", ".hpp", ".h")


class PhpRuntime(BaseRuntime):
    language = "php"
    name = "PhpRuntime"

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return self._resolve_on_path("php", "php.exe")

    def available(self) -> bool:
        return bool(self.resolve(None))

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        php = self.resolve(None)
        if not php:
            raise RuntimeUnavailable("PHP isn't installed on this computer.")
        if getattr(request, "code", ""):
            code = str(request.code)
            staged = self._stage(workdir, "main.php", code if code.lstrip().startswith("<?php") else "<?php\n" + code)
            return PreparedCommand(argv=[php, str(staged), *list(getattr(request, "args", []) or [])],
                                   cwd=workdir, env={}, description="php inline", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "") or "index.php"
        target = (root / entrypoint).resolve()
        return PreparedCommand(argv=[php, str(target), *list(getattr(request, "args", []) or [])],
                               cwd=root, env={}, description=f"php {entrypoint}")

    def test(self, root, project, test_policy, workdir):
        phpunit = root / "vendor" / "bin" / "phpunit"
        if phpunit.is_file() and (php := self.resolve(project)):
            return PreparedCommand(argv=[php, str(phpunit)], cwd=root, env={}, description="phpunit")
        return None


class RubyRuntime(BaseRuntime):
    language = "ruby"
    name = "RubyRuntime"
    aliases = ("rb",)

    def resolve(self, project: Optional[ProjectInfo]) -> str:
        return self._resolve_on_path("ruby", "ruby.exe")

    def available(self) -> bool:
        return bool(self.resolve(None))

    def prepare_run(self, request: Any, root: Path, workdir: Path) -> PreparedCommand:
        ruby = self.resolve(None)
        if not ruby:
            raise RuntimeUnavailable("Ruby isn't installed on this computer.")
        if getattr(request, "code", ""):
            staged = self._stage(workdir, "main.rb", request.code)
            return PreparedCommand(argv=[ruby, str(staged), *list(getattr(request, "args", []) or [])],
                                   cwd=workdir, env={}, description="ruby inline", cleanup=[workdir])
        entrypoint = getattr(request, "entrypoint", "") or "main.rb"
        target = (root / entrypoint).resolve()
        return PreparedCommand(argv=[ruby, str(target), *list(getattr(request, "args", []) or [])],
                               cwd=root, env={}, description=f"ruby {entrypoint}")

    def test(self, root, project, test_policy, workdir):
        rspec = self._resolve_on_path("rspec", "rspec.bat")
        if rspec and (root / "spec").is_dir():
            return PreparedCommand(argv=[rspec], cwd=root, env={}, description="rspec")
        ruby = self.resolve(project)
        if ruby and (root / "test").is_dir():
            return PreparedCommand(argv=[ruby, "-Itest", "-e", "Dir.glob('test/**/*_test.rb').each { |f| require File.expand_path(f) }"],
                                   cwd=root, env={}, description="ruby test")
        return None


__all__ = [
    "CRuntime",
    "CSharpRuntime",
    "CppRuntime",
    "GoRuntime",
    "JavaRuntime",
    "PhpRuntime",
    "RubyRuntime",
    "RustRuntime",
]
