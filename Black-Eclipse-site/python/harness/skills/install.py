"""Install skills from a GitHub repository (the Hermes-class acquire loop).

A user can point Eclipse at a GitHub repo — "load this skill" — and the agent
fetches, validates, content-scans, installs and activates the skills it carries.
This module is the ONE implementation of that loop; the agent tool
(`skills/install_tools.py`), the trust model and the registry all reuse it.

Design (mirrors the project-skills trust model, `skills/project_skills.py`):

  * **GitHub only, https only.** `parse_source` accepts `github.com` URLs (and
    the `owner/repo` shorthand); anything else is refused before a byte is
    fetched. The archive is fetched from `codeload.github.com` over https with a
    hard size cap and timeout — no shell, no git binary, no dependency.
  * **Untrusted until installed.** A fetched repo is extracted to a staging dir
    with zip-slip / absolute-path / symlink / size / count guards, normalized
    into the app's skill-folder layout under `<root>/.black-eclipse/skills/`,
    validated by the pydantic manifest, and content-scanned. A skill tripping a
    quarantine-severity scan rule is refused, never installed.
  * **Operator approval is the install decision.** The agent tool's authorizer
    requires a single-use approval bound to the source URL; on approval, the
    install commits and the root is recorded in the SAME project-trust store
    (per-skill content hashes), so drift after `git pull`/re-install quarantines
    only the changed skills until re-approved. There is no second trust system.
  * **Two input formats.** This app's `skill.json` (+ `SKILL.md`) folders and
    the cross-tool `SKILL.md`-with-frontmatter convention (`.agents/skills/`,
    `.opencode/skills/`, `skills/`) are both accepted; the latter is converted to
    a manifest. Instructions are untrusted data under the existing skill-safety
    rule — installing a skill can never widen a permission or tool allowlist.
  * **Uninstall is symmetric.** Removing a skill drops its folder and re-baselines
    the root's per-skill trust; removing the last skill removes the root and its
    trust row.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import urllib.parse
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from .loader import LoadedSkill, SkillLoadError, load_skill_folder
from .manifest import FORBIDDEN_PERMISSIONS, SkillManifest

# ── Bounds (a hostile repo must not exhaust memory, disk or the prompt) ──────
MAX_ARCHIVE_BYTES = 64 * 1024 * 1024        # repo zipball download cap
MAX_EXTRACTED_BYTES = 256 * 1024 * 1024     # total uncompressed cap
MAX_ARCHIVE_FILES = 4000                    # entries in the zip
MAX_SKILLS_PER_INSTALL = 25                 # installed from ONE repo
MAX_SKILL_FILE_BYTES = 4 * 1024 * 1024      # per-file copy cap
FETCH_TIMEOUT_S = 90.0

# Directories (relative to the repo root or the requested subpath) scanned for
# skill folders, in deterministic order. `.black-eclipse` and `.agents` carry
# folder-per-skill manifests; `.opencode` carries the SKILL.md convention.
_SCAN_SUBDIRS: tuple[str, ...] = (
    "",
    "skills",
    os.path.join(".black-eclipse", "skills"),
    os.path.join(".agents", "skills"),
    os.path.join(".opencode", "skills"),
    os.path.join(".opencode", "skill"),
)

_ROOT_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?github\.com/(?P<owner>[A-Za-z0-9_.-]+)/"
    r"(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?"
    r"(?:/tree/(?P<ref>[^/]+)(?:/(?P<subpath>.+?))?)?/?$",
    re.IGNORECASE,
)
_SHORTHAND_RE = re.compile(
    r"^(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)
_FRONTMATTER_RE = re.compile(r"^\ufeff?---\s*\n(.*?)\n---\s*\n?(.*)$", re.DOTALL)
_SLUG_RE = re.compile(r"[^a-z0-9]+")


class InstallError(Exception):
    """The source could not be parsed, fetched, validated or installed."""


@dataclass(frozen=True)
class GitHubSource:
    """A parsed, canonical GitHub source. `slug` is the on-disk install name."""

    owner: str
    repo: str
    ref: Optional[str] = None
    subpath: Optional[str] = None

    @property
    def slug(self) -> str:
        base = f"{self.owner}__{self.repo}".lower()
        return _SLUG_RE.sub("-", base).strip("-") or "repo"

    @property
    def canonical(self) -> str:
        base = f"https://github.com/{self.owner}/{self.repo}"
        if self.ref:
            base += f"@{self.ref}"
        if self.subpath:
            base += f"#{self.subpath}"
        return base

    @property
    def display(self) -> str:
        base = f"{self.owner}/{self.repo}"
        if self.ref:
            base += f" @ {self.ref}"
        if self.subpath:
            base += f" ({self.subpath})"
        return base

    @property
    def archive_url(self) -> str:
        ref = urllib.request.quote(self.ref or "HEAD", safe="")
        return f"https://codeload.github.com/{self.owner}/{self.repo}/zip/{ref}"


def parse_source(
    raw: str, *, ref: Optional[str] = None, subpath: Optional[str] = None,
) -> GitHubSource:
    """Parse a GitHub URL (or `owner/repo` shorthand) into a `GitHubSource`.

    Accepts `https://github.com/owner/repo`, `.../repo.git`,
    `.../repo/tree/<ref>/<subpath>` and the bare `owner/repo` shorthand. An
    explicit `ref`/`subpath` argument overrides the URL's (a branch name with a
    slash cannot be parsed unambiguously from a URL — pass it explicitly).
    Raises `InstallError` for anything that is not a public https GitHub repo.
    """
    text = (raw or "").strip()
    if not text:
        raise InstallError("a GitHub repository URL is required")
    if "://" in text:
        scheme = text.split("://", 1)[0].lower()
        if scheme != "https":
            raise InstallError(f"only https sources are accepted (got {scheme!r})")
    match = _ROOT_URL_RE.match(text) if ("github" in text.lower() or "://" in text) else None
    if match is None and "://" in text:
        raise InstallError("only github.com repositories are supported")
    if match is None:
        shorthand = _SHORTHAND_RE.match(text)
        if shorthand is None:
            raise InstallError(
                "not a GitHub repository URL — expected "
                "https://github.com/<owner>/<repo>[/tree/<ref>/<path>] or <owner>/<repo>"
            )
        match = shorthand
    owner = match.group("owner")
    repo = match.group("repo")
    if repo in (".", "..") or owner in (".", ".."):
        raise InstallError("invalid repository name")
    parsed_ref = match.groupdict().get("ref")
    parsed_sub = match.groupdict().get("subpath")
    clean_sub = None
    for candidate in (subpath or parsed_sub,):
        if candidate:
            normalized = str(candidate).replace("\\", "/").strip("/")
            if ".." in normalized.split("/"):
                raise InstallError("subpath may not contain '..'")
            clean_sub = normalized or None
    return GitHubSource(
        owner=owner, repo=repo,
        ref=(ref.strip() if isinstance(ref, str) and ref.strip() else parsed_ref),
        subpath=clean_sub,
    )


def source_digest(source: GitHubSource) -> str:
    """The stable digest an approval is bound to (one approval = this exact source)."""
    return hashlib.sha256(source.canonical.encode("utf-8")).hexdigest()


# ── Install locations ────────────────────────────────────────────────────────


def installed_skills_home() -> str:
    """The managed home for GitHub-installed skill roots.

    `BLACK_ECLIPSE_SKILLS_DIR` overrides it (tests / a custom workspace); the
    default is `<repo>/installed-skills`, a sibling of the app's databases, so a
    local-first install keeps its skills beside its data and never inside the
    shipped library.
    """
    override = os.environ.get("BLACK_ECLIPSE_SKILLS_DIR")
    if override:
        return os.path.abspath(override)
    from ..eclipse_memory.config import repo_root  # noqa: PLC0415

    return os.path.join(repo_root(), "installed-skills")


def list_installed_roots(home: Optional[str] = None) -> list[str]:
    """Every installed skill root (a direct child of the home), sorted."""
    base = os.path.abspath(home or installed_skills_home())
    if not os.path.isdir(base):
        return []
    return sorted(
        os.path.join(base, name)
        for name in os.listdir(base)
        if os.path.isdir(os.path.join(base, name)) and not name.startswith(".")
    )


# ── Fetch + extraction ───────────────────────────────────────────────────────


def fetch_archive(source: GitHubSource, dest_zip: str, *, timeout_s: float = FETCH_TIMEOUT_S) -> int:
    """Download the repo zipball over https to `dest_zip`. Returns bytes written.

    Streams with a hard cap (`MAX_ARCHIVE_BYTES`) so a hostile source cannot fill
    the disk; no shell, no git, no redirect to another host is followed.
    """
    request = urllib.request.Request(
        source.archive_url,
        headers={"User-Agent": "black-eclipse-skill-install/1.0", "Accept": "application/zip"},
    )
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:  # noqa: S310 - https enforced by parse_source
            final = urllib.parse.urlparse(response.geturl()) if hasattr(response, "geturl") else None
            if final is not None and final.netloc.lower() not in ("codeload.github.com", "github.com"):
                raise InstallError(f"refusing a redirect to {final.netloc}")
            with open(dest_zip, "wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > MAX_ARCHIVE_BYTES:
                        raise InstallError(
                            f"repository archive exceeds the {MAX_ARCHIVE_BYTES // (1024 * 1024)} MB limit"
                        )
                    handle.write(chunk)
    except InstallError:
        raise
    except Exception as exc:  # noqa: BLE001 - any transport failure is an install failure
        raise InstallError(f"could not fetch {source.display}: {exc}") from exc
    if written == 0:
        raise InstallError(f"the archive for {source.display} was empty")
    return written


def _safe_member_path(name: str) -> Optional[str]:
    """A zip member's normalized relative path, or None when unsafe."""
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        return None
    parts = [part for part in normalized.split("/") if part not in ("", ".")]
    if any(part == ".." for part in parts):
        return None
    return "/".join(parts) or None


def extract_archive(zip_path: str, dest: str) -> str:
    """Extract a zipball into `dest` with traversal/size/count guards.

    Returns the (single) top-level directory the archive unpacked into — the
    codeload convention — or `dest` when the archive has no wrapper folder.
    """
    total = 0
    count = 0
    tops: set[str] = set()
    os.makedirs(dest, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as archive:
            for info in archive.infolist():
                rel = _safe_member_path(info.filename)
                if rel is None:
                    continue
                count += 1
                if count > MAX_ARCHIVE_FILES:
                    raise InstallError(f"archive exceeds the {MAX_ARCHIVE_FILES}-file limit")
                tops.add(rel.split("/", 1)[0])
                if info.is_dir():
                    continue
                # A symlink entry is refused, never materialized: the zip format
                # can encode them and following one could escape the staging dir.
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise InstallError(f"archive contains a symlink ({info.filename!r}) — refused")
                total += info.file_size
                if total > MAX_EXTRACTED_BYTES:
                    raise InstallError(
                        f"archive expands beyond the {MAX_EXTRACTED_BYTES // (1024 * 1024)} MB limit"
                    )
                target = os.path.join(dest, *rel.split("/"))
                resolved = os.path.abspath(target)
                if not resolved.startswith(os.path.abspath(dest) + os.sep):
                    raise InstallError(f"archive member escapes the staging directory ({info.filename!r})")
                os.makedirs(os.path.dirname(resolved), exist_ok=True)
                with archive.open(info) as source_handle, open(resolved, "wb") as target_handle:
                    shutil.copyfileobj(source_handle, target_handle, length=256 * 1024)
    except zipfile.BadZipFile as exc:
        raise InstallError("the downloaded archive is not a valid zip") from exc
    if len(tops) == 1:
        only = os.path.join(dest, tops.pop())
        if os.path.isdir(only):
            return only
    return dest


# ── Candidate discovery + normalization ──────────────────────────────────────


@dataclass
class _Candidate:
    """One skill folder found in the archive, before normalization."""

    folder: str
    kind: str  # "app" (skill.json) | "md" (SKILL.md frontmatter)
    name: str
    description: str
    skill_id: Optional[str] = None


def _parse_frontmatter(text: str) -> tuple[dict[str, str], str]:
    """Parse the minimal YAML frontmatter of a SKILL.md (name/description/tags).

    Deliberately tiny and dependency-free: scalar `key: value` pairs only. A
    document without frontmatter returns ({}, full text).
    """
    match = _FRONTMATTER_RE.match(text or "")
    if not match:
        return {}, text or ""
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        value = value.strip().strip("'\"")
        meta[key.strip().lower()] = value
    return meta, match.group(2)


def _slugify(name: str) -> str:
    slug = _SLUG_RE.sub("-", (name or "").lower()).strip("-")
    return (slug or "skill")[:96]


def _first_meaningful_line(body: str) -> str:
    for line in (body or "").splitlines():
        stripped = line.strip().lstrip("#").strip()
        if stripped:
            return stripped[:300]
    return ""


def discover_candidates(root: str, subpath: Optional[str] = None) -> list[_Candidate]:
    """Find skill folders under `root` (optionally narrowed by `subpath`).

    Scans the documented conventions in `_SCAN_SUBDIRS` plus the base directory
    itself (a single-skill repo). Returns candidates in deterministic order;
    a folder with a valid `skill.json` wins over a bare `SKILL.md` in the same
    folder.
    """
    base = os.path.abspath(root)
    if subpath:
        base = os.path.abspath(os.path.join(base, *subpath.split("/")))
        if not (base == os.path.abspath(root) or base.startswith(os.path.abspath(root) + os.sep)):
            raise InstallError("subpath escapes the repository root")
    if not os.path.isdir(base):
        raise InstallError(f"no directory at {subpath!r} in the repository")

    candidates: list[_Candidate] = []
    seen_folders: set[str] = set()

    def _inspect(folder: str) -> None:
        folder = os.path.abspath(folder)
        if folder in seen_folders or not os.path.isdir(folder):
            return
        seen_folders.add(folder)
        manifest_path = os.path.join(folder, "skill.json")
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as handle:
                    raw = json.load(handle)
            except (OSError, ValueError):
                raw = None
            if isinstance(raw, dict):
                candidates.append(_Candidate(
                    folder=folder, kind="app",
                    name=str(raw.get("name") or os.path.basename(folder)),
                    description=str(raw.get("description") or ""),
                    skill_id=str(raw.get("id") or "") or None,
                ))
                return
        md_path = os.path.join(folder, "SKILL.md")
        if os.path.isfile(md_path):
            try:
                with open(md_path, "r", encoding="utf-8", errors="replace") as handle:
                    text = handle.read(400_000)
            except OSError:
                return
            meta, body = _parse_frontmatter(text)
            name = meta.get("name") or os.path.basename(folder)
            description = meta.get("description") or _first_meaningful_line(body)
            candidates.append(_Candidate(
                folder=folder, kind="md", name=name,
                description=description or f"Installed skill {name}",
                skill_id=meta.get("name") and _slugify(meta["name"]) or None,
            ))

    # The base itself first (a single-skill repo), then each convention subdir.
    if os.path.isfile(os.path.join(base, "skill.json")) or os.path.isfile(os.path.join(base, "SKILL.md")):
        _inspect(base)
    for sub in _SCAN_SUBDIRS:
        scan_dir = os.path.join(base, sub) if sub else base
        if not os.path.isdir(scan_dir):
            continue
        try:
            entries = sorted(os.listdir(scan_dir))
        except OSError:
            continue
        for entry in entries:
            _inspect(os.path.join(scan_dir, entry))
    return candidates


def _copy_skill_tree(source_folder: str, dest_folder: str, notices: list[str]) -> None:
    """Copy a skill folder into staging, bounded and without junk.

    Enforces the per-file cap (oversized files are skipped and reported, never
    silently dropped) and skips VCS/pycache noise so an install is reproducible.
    """
    os.makedirs(dest_folder, exist_ok=True)
    for current, dirs, files in os.walk(source_folder):
        dirs[:] = sorted(
            d for d in dirs if d not in (".git", "__pycache__", "node_modules", ".venv")
        )
        rel = os.path.relpath(current, source_folder)
        target_dir = dest_folder if rel == "." else os.path.join(dest_folder, rel)
        os.makedirs(target_dir, exist_ok=True)
        for name in sorted(files):
            source_file = os.path.join(current, name)
            try:
                size = os.path.getsize(source_file)
            except OSError:
                continue
            if size > MAX_SKILL_FILE_BYTES:
                notices.append(
                    f"skipped oversized file {name!r} ({size} bytes) in {os.path.basename(source_folder)}"
                )
                continue
            try:
                shutil.copyfile(source_file, os.path.join(target_dir, name))
            except OSError as exc:
                notices.append(f"could not copy {name!r}: {exc}")


def _normalize_candidate(
    candidate: _Candidate, staging_root: str, source: GitHubSource, notices: list[str],
) -> tuple[Optional[str], Optional[str]]:
    """Materialize one candidate as `staging_root/.black-eclipse/skills/<id>/`.

    Returns `(skill_id, error)`. An app-format manifest is preserved (with
    install-time overrides); a SKILL.md candidate is converted to a manifest.
    """
    skills_dir = os.path.join(staging_root, ".black-eclipse", "skills")
    dest = os.path.join(skills_dir, _slugify(candidate.skill_id or candidate.name))
    try:
        _copy_skill_tree(candidate.folder, dest, notices)
    except OSError as exc:
        return None, f"{candidate.name}: {exc}"

    manifest_path = os.path.join(dest, "skill.json")
    if candidate.kind == "app":
        try:
            with open(manifest_path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except (OSError, ValueError) as exc:
            return None, f"{candidate.name}: invalid skill.json ({exc})"
    else:
        md_path = os.path.join(dest, "SKILL.md")
        try:
            with open(md_path, "r", encoding="utf-8", errors="replace") as handle:
                meta, _body = _parse_frontmatter(handle.read(400_000))
        except OSError as exc:
            return None, f"{candidate.name}: cannot read SKILL.md ({exc})"
        raw = {
            "id": _slugify(meta.get("name") or candidate.name),
            "name": meta.get("name") or candidate.name,
            "description": candidate.description,
            "category": "research",
            "instructions": "SKILL.md",
            "tags": [
                tag.strip().lower()
                for tag in re.split(r"[,\[\]]", meta.get("tags") or "")
                if tag.strip()
            ],
        }

    # Install-time overrides. The operator's approval of the source IS the
    # enable decision; the manifest's own status must not leave a freshly
    # installed skill inert, and a missing author/version must not fail the
    # install over cosmetic provenance.
    raw.setdefault("version", "1.0.0")
    raw.setdefault("category", "research")
    raw.setdefault("description", candidate.description or candidate.name)
    raw.setdefault("author", f"github:{source.owner}/{source.repo}")
    raw["status"] = "enabled"
    if raw.get("origin") not in ("builtin", "author", "learning"):
        raw["origin"] = "author"
    try:
        manifest = SkillManifest(**raw)
    except Exception as exc:  # noqa: BLE001 - a pydantic error is a per-skill skip
        return None, f"{candidate.name}: invalid manifest ({exc})"
    forbidden = manifest.forbidden_permissions
    if forbidden:
        return None, f"{manifest.id}: declares never-grantable permissions {forbidden}"
    with open(manifest_path, "w", encoding="utf-8") as handle:
        json.dump(manifest.model_dump(), handle, indent=2, sort_keys=True)
    return manifest.id, None


def _scan_staged(skills_dir: str) -> tuple[list[LoadedSkill], list[dict[str, Any]]]:
    """Load + content-scan every staged skill folder.

    Returns `(loadable, refused)`; a quarantine-severity finding refuses that
    skill (it must never reach the model with instruction-override prose).
    """
    loadable: list[LoadedSkill] = []
    refused: list[dict[str, Any]] = []
    if not os.path.isdir(skills_dir):
        return loadable, refused
    for name in sorted(os.listdir(skills_dir)):
        folder = os.path.join(skills_dir, name)
        if not os.path.isdir(folder) or not os.path.isfile(os.path.join(folder, "skill.json")):
            continue
        try:
            loaded = load_skill_folder(folder)
        except SkillLoadError as exc:
            refused.append({"folder": name, "reason": str(exc)})
            continue
        try:
            from .content_scan import scan_loaded_skill  # noqa: PLC0415

            scan = scan_loaded_skill(loaded)
        except Exception:  # noqa: BLE001 - a scan failure must fail closed
            refused.append({"folder": name, "reason": "content scan unavailable — refused"})
            continue
        if scan is not None and scan.should_quarantine:
            refused.append({
                "folder": name,
                "reason": "content scan quarantined this skill",
                "categories": list(scan.categories),
            })
            continue
        loadable.append(loaded)
    return loadable, refused


# ── Install / uninstall ──────────────────────────────────────────────────────


def _install_metadata(source: GitHubSource, skill_ids: list[str]) -> dict[str, Any]:
    from ..eclipse_memory.db import now_iso  # noqa: PLC0415

    return {
        "url": source.canonical,
        "owner": source.owner,
        "repo": source.repo,
        "ref": source.ref,
        "subpath": source.subpath,
        "skillIds": skill_ids,
        "installedAt": now_iso(),
        "installedBy": "agent",
    }


def install_from_github(
    store: Any,
    source: GitHubSource,
    *,
    available_tools: list[str] = (),
    home: Optional[str] = None,
    fetch: Optional[Callable[[GitHubSource, str], int]] = None,
) -> dict[str, Any]:
    """Fetch, validate, scan, install and trust the skills of one GitHub source.

    The whole loop is staged: nothing lands in the install home until every
    surviving skill has validated and passed the content scan. Per-skill failures
    are reported and skipped; an install with zero surviving skills is an error
    and leaves no trace. On success the root is trusted through the SAME
    project-trust store (per-skill content hashes), so later drift is quarantined
    pending re-approval.
    """
    from .project_skills import trust_root  # noqa: PLC0415

    base_home = os.path.abspath(home or installed_skills_home())
    os.makedirs(base_home, exist_ok=True)
    final_dir = os.path.join(base_home, source.slug)
    staging = os.path.join(base_home, f".staging-{uuid.uuid4().hex[:12]}")
    notices: list[str] = []
    refused: list[dict[str, Any]] = []
    try:
        os.makedirs(staging, exist_ok=True)
        archive_path = os.path.join(staging, "archive.zip")
        extract_dir = os.path.join(staging, "repo")
        fetcher = fetch or (lambda src, dest: fetch_archive(src, dest))
        fetcher(source, archive_path)
        repo_root = extract_archive(archive_path, extract_dir)
        candidates = discover_candidates(repo_root, source.subpath)
        if not candidates:
            raise InstallError(
                "no skills found in this repository — expected a skill folder with "
                "skill.json, or SKILL.md under skills/, .agents/skills/, "
                ".opencode/skills/ or .black-eclipse/skills/"
            )
        if len(candidates) > MAX_SKILLS_PER_INSTALL:
            refused.extend(
                {"folder": os.path.relpath(c.folder, repo_root), "reason": "over the per-install skill limit"}
                for c in candidates[MAX_SKILLS_PER_INSTALL:]
            )
            candidates = candidates[:MAX_SKILLS_PER_INSTALL]

        staging_root = os.path.join(staging, "normalized")
        requested: list[tuple[str, str]] = []  # (skill_id, source folder label)
        for candidate in candidates:
            skill_id, error = _normalize_candidate(candidate, staging_root, source, notices)
            if error:
                refused.append({"folder": os.path.relpath(candidate.folder, repo_root), "reason": error})
                continue
            requested.append((skill_id, os.path.relpath(candidate.folder, repo_root)))

        skills_dir = os.path.join(staging_root, ".black-eclipse", "skills")
        loadable, scan_refused = _scan_staged(skills_dir)
        refused.extend(scan_refused)
        by_id = {loaded.manifest.id: loaded for loaded in loadable}

        installed_ids: list[str] = []
        unknown_tools: dict[str, list[str]] = {}
        known = set(available_tools or [])
        for skill_id, label in requested:
            if skill_id not in by_id:
                refused.append({"folder": label, "reason": f"{skill_id} failed validation or scanning"})
                continue
            manifest = by_id[skill_id].manifest
            missing = [t for t in manifest.requiredTools if known and t not in known]
            if missing:
                unknown_tools[skill_id] = missing
            installed_ids.append(skill_id)
        if not installed_ids:
            raise InstallError(
                "no installable skills survived validation: "
                + "; ".join(f"{r['folder']}: {r['reason']}" for r in refused[:5])
            )

        # Commit: drop folders for refused skills, move staged → final, record
        # metadata, then trust the root (the approval already happened upstream).
        for name in list(os.listdir(skills_dir)):
            folder = os.path.join(skills_dir, name)
            if os.path.isdir(folder):
                try:
                    staged_id = load_skill_folder(folder).manifest.id
                except SkillLoadError:
                    staged_id = None
                if staged_id not in installed_ids:
                    shutil.rmtree(folder, ignore_errors=True)
        if os.path.isdir(final_dir):
            shutil.rmtree(final_dir, ignore_errors=True)
        os.replace(staging_root, final_dir)
        with open(os.path.join(final_dir, "install.json"), "w", encoding="utf-8") as handle:
            json.dump(_install_metadata(source, installed_ids), handle, indent=2, sort_keys=True)
        trust_root(
            store, final_dir,
            note=f"installed: {source.canonical}",
            actor="skill_install",
        )
        try:
            store.append_event(
                "skill.installed",
                data={"source": source.canonical, "skillIds": installed_ids},
            )
        except Exception:  # noqa: BLE001 - audit is best-effort
            pass
        return {
            "ok": True,
            "source": source.canonical,
            "installDir": final_dir,
            "installed": installed_ids,
            "skipped": refused,
            "unknownTools": unknown_tools,
            "notices": notices,
        }
    except InstallError:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    except Exception as exc:  # noqa: BLE001 - any failure is an honest install failure
        shutil.rmtree(staging, ignore_errors=True)
        raise InstallError(f"install failed: {exc}") from exc
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def _read_install_metadata(root: str) -> dict[str, Any]:
    path = os.path.join(root, "install.json")
    if not os.path.isfile(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def uninstall_skill(store: Any, skill_id: str, *, home: Optional[str] = None) -> dict[str, Any]:
    """Remove one installed skill (folder + trust re-baseline). Idempotent-honest.

    Removing a skill re-baselines the root's per-skill trust so the remaining
    skills stay loadable; removing the LAST skill removes the root and its trust
    row. A skill that is not installed is reported as not found — never guessed.
    """
    from .project_skills import per_skill_hashes, untrust_root  # noqa: PLC0415

    target = str(skill_id or "").strip()
    if not target:
        return {"ok": False, "error": "a skill id is required"}
    for root in list_installed_roots(home):
        hashes = per_skill_hashes(root)
        if target not in hashes:
            continue
        folder = None
        skills_dir = os.path.join(root, ".black-eclipse", "skills")
        if os.path.isdir(skills_dir):
            for name in sorted(os.listdir(skills_dir)):
                candidate = os.path.join(skills_dir, name)
                if not os.path.isdir(candidate):
                    continue
                try:
                    if load_skill_folder(candidate).manifest.id == target:
                        folder = candidate
                        break
                except SkillLoadError:
                    continue
        if folder is None:
            continue
        shutil.rmtree(folder, ignore_errors=True)
        remaining = sorted(set(per_skill_hashes(root).keys()))
        if remaining:
            from .project_skills import trust_root  # noqa: PLC0415

            trust_root(store, root, note=f"uninstalled: {target}", actor="skill_uninstall")
            root_removed = False
        else:
            untrust_root(store, root, actor="skill_uninstall")
            shutil.rmtree(root, ignore_errors=True)
            root_removed = True
        try:
            store.append_event("skill.uninstalled", skill_id=target, data={"root": root})
        except Exception:  # noqa: BLE001 - audit is best-effort
            pass
        return {
            "ok": True, "skillId": target, "root": root,
            "rootRemoved": root_removed, "remainingSkills": remaining,
        }
    return {"ok": False, "error": f"{target!r} is not an installed skill (skill_list shows installed ids)"}


def list_installed_sources(store: Any, *, home: Optional[str] = None) -> list[dict[str, Any]]:
    """The installed GitHub sources with their trust/drift status (read-only)."""
    from .project_skills import drift_status, per_skill_hashes  # noqa: PLC0415

    out: list[dict[str, Any]] = []
    for root in list_installed_roots(home):
        metadata = _read_install_metadata(root)
        try:
            drift = drift_status(store, root)
        except Exception:  # noqa: BLE001 - a status read must not fail the listing
            drift = {}
        out.append({
            "root": root,
            "url": metadata.get("url"),
            "ref": metadata.get("ref"),
            "subpath": metadata.get("subpath"),
            "installedAt": metadata.get("installedAt"),
            "skillIds": sorted(per_skill_hashes(root).keys()),
            "trusted": bool(drift.get("trusted")),
            "drift": bool(drift.get("drift")),
            "quarantinedSkillIds": drift.get("quarantinedSkillIds") or [],
        })
    return out


def discover_installed_skills(
    store: Any, home: Optional[str] = None,
) -> tuple[list[LoadedSkill], list[str], list[str], list[str]]:
    """Load every TRUSTED installed root for the registry.

    Returns `(skills, notices, changed_ids, quarantined_ids)`. Mirrors the
    project-skills discovery semantics: an untrusted root contributes a notice
    only (names, never contents); a changed skill is quarantined on its own while
    unchanged skills still load.
    """
    from .project_skills import load_root_skills, scan_root  # noqa: PLC0415

    skills: list[LoadedSkill] = []
    notices: list[str] = []
    changed: list[str] = []
    quarantined: list[str] = []
    for root in list_installed_roots(home):
        try:
            state = scan_root(store, root)
        except Exception:  # noqa: BLE001 - one bad root must not block the rest
            notices.append(f"installed skills in {root} could not be scanned")
            continue
        if not state.trusted:
            if state.skill_ids:
                notices.append(
                    f"{len(state.skill_ids)} installed skill(s) in {root} are not trusted "
                    "and were not loaded"
                )
            continue
        all_skills, _ids, errors = load_root_skills(state.skills_dir)
        held = set(state.quarantined_skill_ids)
        for loaded in all_skills:
            if loaded.manifest.id in held:
                continue
            skills.append(loaded)
        changed.extend(state.changed_skill_ids)
        quarantined.extend(state.quarantined_skill_ids)
        if state.drift:
            notices.append(
                "changed installed skill(s) are quarantined until re-approved: "
                + ", ".join(state.quarantined_skill_ids)
            )
        for error in [*state.errors, *errors]:
            if error not in notices:
                notices.append(error)
    skills.sort(key=lambda loaded: loaded.manifest.id)
    return skills, notices, sorted(set(changed)), sorted(set(quarantined))


__all__ = [
    "InstallError",
    "GitHubSource",
    "discover_candidates",
    "discover_installed_skills",
    "extract_archive",
    "fetch_archive",
    "install_from_github",
    "installed_skills_home",
    "list_installed_roots",
    "list_installed_sources",
    "parse_source",
    "source_digest",
    "uninstall_skill",
]
