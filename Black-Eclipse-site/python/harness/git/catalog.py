"""The Git operation catalog — the closed table of every allowed git argv.

Each entry is a `GitOp` whose builder emits an absolute-executable, no-shell,
`--`-guarded argv from VALIDATED values only. The table is the capability: a
subcommand absent here is unreachable by any model input.

Reads are `safe`; local mutations are `caution`; history rewrites and index
moves are `dangerous`; work-discarding and ref-deleting ops are `destructive`;
remote-history destruction (`push --force`, `+refspec`, tag force-delete) is
`critical`. The safety engine consumes `risk`; nothing here decides policy.
"""

from __future__ import annotations

from typing import Any

from .operations import GitArg, GitOp

# Convenience arg constructors.
def _p(name: str = "paths", *, required: bool = False) -> GitArg:
    return GitArg(name=name, kind="path", many=True, required=required, max_len=1024)


def _rev(name: str, *, required: bool = True) -> GitArg:
    return GitArg(name=name, kind="rev", required=required)


def _ref(name: str, *, required: bool = True) -> GitArg:
    return GitArg(name=name, kind="ref", required=required)


def _text(name: str, *, required: bool = True, max_len: int = 2_000) -> GitArg:
    return GitArg(name=name, kind="text", required=required, max_len=max_len)


def _int(name: str, *, required: bool = False, lo: int = 0, hi: int = 1_000_000) -> GitArg:
    return GitArg(name=name, kind="int", required=required, min_int=lo, max_int=hi)


def _flag(name: str) -> GitArg:
    """A boolean switch; validated as a plain string 'true'/'false'. Unused
    directly — switches are encoded by distinct op names, never by a raw flag."""
    return GitArg(name=name, kind="enum", allowed=("true", "false"))

# `--` guard: paths are always appended after a literal `--` so a path can never
# be parsed as an option. No op ever places a path before `--`.
def _with_paths(base: list[str], paths: list[str]) -> list[str]:
    if paths:
        return base + ["--", *paths]
    return base


def _build(exe: str, *tokens: str) -> list[str]:
    return [exe, "-c", "core.longpaths=true", "-c", "advice.detachedHead=false", *tokens]


# ── The catalog ──────────────────────────────────────────────────────────────

CATALOG: dict[str, GitOp] = {}


def _register(op: GitOp) -> GitOp:
    if op.name in CATALOG:
        raise ValueError(f"duplicate git op {op.name!r}")
    CATALOG[op.name] = op
    return op


# ── Repository / read-only plumbing ───────────────────────────────────────────

_register(GitOp(
    "rev_parse", lambda a, exe: _build(exe, "rev-parse", a.get("rev", "HEAD")),
    args=(_rev("rev", required=False),), summary="Resolve a revision to a sha.",
))
_register(GitOp(
    "rev_parse_abbrev", lambda a, exe: _build(exe, "rev-parse", "--abbrev-ref", a.get("rev", "HEAD")),
    args=(_rev("rev", required=False),), summary="Resolve a revision to a short name.",
))
_register(GitOp(
    "discover",
    lambda a, exe: _build(
        exe, "rev-parse", "--show-toplevel", "--absolute-git-dir",
        "--is-bare-repository", "--is-inside-git-dir", "--is-inside-work-tree",
    ),
    summary="Repository discovery probe (all facts in one call).",
))
_register(GitOp(
    "git_dir", lambda a, exe: _build(exe, "rev-parse", "--absolute-git-dir"),
    summary="The absolute git directory.",
))
_register(GitOp(
    "toplevel", lambda a, exe: _build(exe, "rev-parse", "--show-toplevel"),
    summary="The worktree top level.",
))
_register(GitOp(
    "is_bare", lambda a, exe: _build(exe, "rev-parse", "--is-bare-repository"),
    summary="Whether the repository is bare.",
))
_register(GitOp(
    "common_dir", lambda a, exe: _build(exe, "rev-parse", "--path-format=absolute", "--git-common-dir"),
    summary="The common git dir (linked-worktree/submodule sharing).",
))
_register(GitOp(
    "head_sha", lambda a, exe: _build(exe, "rev-parse", "--verify", "HEAD"),
    summary="The HEAD commit sha (fails when unborn).",
))
_register(GitOp(
    "head_ref", lambda a, exe: _build(exe, "rev-parse", "--abbrev-ref", "HEAD"),
    summary="The HEAD ref name ('HEAD' when detached).",
))
_register(GitOp(
    "upstream", lambda a, exe: _build(exe, "rev-parse", "--abbrev-ref", "--symbolic-full-name",
                                      a.get("branch", "HEAD") + "@{upstream}"),
    args=(_rev("branch", required=False),), summary="A branch's upstream ref, or failure.",
))
_register(GitOp(
    "ahead_behind", lambda a, exe: _build(exe, "rev-list", "--left-right", "--count", a["local"], a["remote"]),
    args=(_rev("local"), _rev("remote")), summary="Ahead/behind counts.",
))
_register(GitOp(
    "show_ref", lambda a, exe: _build(exe, "show-ref", *a.get("flags", [])),
    args=(GitArg("flags", kind="enum", many=True, allowed=("--heads", "--tags", "--dereference")),),
    summary="List refs.",
))
_register(GitOp(
    "symbolic_ref_head", lambda a, exe: _build(exe, "symbolic-ref", "-q", "HEAD"),
    summary="The current branch, or failure when detached.",
))
_register(GitOp(
    "count_objects", lambda a, exe: _build(exe, "count-objects", "-v"),
    summary="Repository object counts (size signal).",
))
_register(GitOp(
    "check_ref_format", lambda a, exe: _build(exe, "check-ref-format", "--branch", a["branch"]),
    args=(_ref("branch"),), summary="Whether a branch name is valid.",
))

# ── Status ─────────────────────────────────────────────────────────────────────

_register(GitOp(
    "status", lambda a, exe: _build(exe, "status", "--porcelain=v2", "-z", "--branch", "--untracked-files=all"),
    summary="Machine-readable repository status.",
))
_register(GitOp(
    "ls_files_stage", lambda a, exe: _build(exe, "ls-files", "-z", "--stage"),
    summary="Index entries with mode/object (staged vs HEAD classification).",
))
_register(GitOp(
    "unmerged", lambda a, exe: _build(exe, "diff", "--name-only", "--diff-filter=U", "-z"),
    summary="Unmerged (conflicted) paths.",
))
_register(GitOp(
    "ls_files_others", lambda a, exe: _build(exe, "ls-files", "-z", "--others", "--exclude-standard"),
    summary="Untracked files (respecting ignore rules, no untracked dirs).",
))
_register(GitOp(
    "check_ignore", lambda a, exe: _build(exe, "check-ignore", "-z", *a.get("paths", [])),
    args=(_p(required=True),), summary="Whether paths are ignored.",
))

# ── Diff family ────────────────────────────────────────────────────────────────

_register(GitOp(
    "diff_worktree", lambda a, exe: _build(exe, "diff", "--no-color", "--no-ext-diff", *_diff_opts(a)),
    args=(_rev("base", required=False), _p(), GitArg("contextLines", kind="int", min_int=0, max_int=100)),
    summary="Working tree vs index (or a base).",
))
_register(GitOp(
    "diff_cached", lambda a, exe: _build(exe, "diff", "--cached", "--no-color", "--no-ext-diff", *_diff_opts(a)),
    args=(_rev("base", required=False), _p()),
    summary="Index vs HEAD.",
))
_register(GitOp(
    "diff_range", lambda a, exe: _build(exe, "diff", "--no-color", "--no-ext-diff", a["from"], a["to"], *_diff_opts(a)),
    args=(_rev("from"), _rev("to"), _p()),
    summary="Two revisions.",
))
_register(GitOp(
    "diff_name_status", lambda a, exe: _build(exe, "diff", "--name-status", "-z", *_diff_opts(a)),
    args=(_rev("base", required=False), _p()), summary="Changed paths with status letters.",
))
_register(GitOp(
    "diff_name_status_cached", lambda a, exe: _build(exe, "diff", "--cached", "--name-status", "-z", *_diff_opts(a)),
    args=(_rev("base", required=False), _p()), summary="Staged paths with status letters.",
))
_register(GitOp(
    "diff_name_status_range", lambda a, exe: _build(exe, "diff", "--name-status", "-z", a["from"], a["to"], *_with_paths([], a.get("paths", []))),
    args=(_rev("from"), _rev("to"), _p()), summary="Two revisions, changed paths.",
))
_register(GitOp(
    "diff_numstat", lambda a, exe: _build(exe, "diff", "--numstat", "-z", *_diff_opts(a)),
    args=(_rev("base", required=False), _p()), summary="Per-file insertion/deletion counts.",
))
_register(GitOp(
    "diff_numstat_cached", lambda a, exe: _build(exe, "diff", "--cached", "--numstat", "-z", *_diff_opts(a)),
    args=(_rev("base", required=False), _p()), summary="Staged per-file insertion/deletion counts.",
))
_register(GitOp(
    "diff_numstat_range", lambda a, exe: _build(exe, "diff", "--numstat", "-z", a["from"], a["to"], *_with_paths([], a.get("paths", []))),
    args=(_rev("from"), _rev("to"), _p()), summary="Two revisions, per-file counts.",
))

# ── History ────────────────────────────────────────────────────────────────────

_register(GitOp(
    "log", lambda a, exe: _build(
        exe, "log", "--no-color", *_log_format(),
        *([f"--max-count={a['maxCount']}"] if a.get("maxCount") else []),
        *([f"--skip={a['skip']}"] if a.get("skip") else []),
        *([f"--author={a['author']}"] if a.get("author") else []),
        *([f"--since={a['since']}"] if a.get("since") else []),
        *([f"--until={a['until']}"] if a.get("until") else []),
        *([f"--grep={a['grep']}"] if a.get("grep") else []),
        *([a["rev"]] if a.get("rev") else []),
        *(["--"] + a["paths"] if a.get("paths") else []),
    ),
    args=(
        _rev("rev", required=False), _int("maxCount", lo=1, hi=100_000),
        _int("skip", lo=0, hi=10_000_000), _text("author", required=False, max_len=200),
        GitArg("since", kind="date", required=False), GitArg("until", kind="date", required=False),
        GitArg("grep", kind="pattern", required=False), _p(),
    ),
    summary="Commit history.",
))
_register(GitOp(
    "log_range", lambda a, exe: _build(
        exe, "log", "--no-color", *_log_format(), f"{a['from']}..{a['to']}",
        *([f"--max-count={a['maxCount']}"] if a.get("maxCount") else []),
    ),
    args=(_rev("from"), _rev("to"), _int("maxCount", lo=1, hi=100_000)),
    summary="History of a commit range.",
))
_register(GitOp(
    "show", lambda a, exe: _build(exe, "show", "--no-color", a["rev"], *_show_opts(a)),
    args=(_rev("rev"), _p(), GitArg("stat", kind="enum", required=False, allowed=("true",))),
    summary="One commit (metadata + patch or stat).",
))
_register(GitOp(
    "commit_files", lambda a, exe: _build(exe, "show", "--no-color", "--name-status", "-z", a["rev"]),
    args=(_rev("rev"),), summary="Files touched by one commit.",
))
_register(GitOp(
    "commit_stats", lambda a, exe: _build(exe, "show", "--no-color", "--numstat", "-z", a["rev"]),
    args=(_rev("rev"),), summary="Insertion/deletion stats for one commit.",
))
_register(GitOp(
    "commit_parents", lambda a, exe: _build(exe, "rev-list", "--parents", "-n", "1", a["rev"]),
    args=(_rev("rev"),), summary="Parent shas of a commit.",
))
_register(GitOp(
    "reflog", lambda a, exe: _build(
        exe, "reflog", "--no-color", "--format=%H%x00%gd%x00%gs%x00%ci%x00%an",
        *([f"--max-count={a['maxCount']}"] if a.get("maxCount") else []),
        *([a["ref"]] if a.get("ref") else []),
    ),
    args=(_ref("ref", required=False), _int("maxCount", lo=1, hi=100_000)),
    summary="Reference update history.",
))
_register(GitOp(
    "blame", lambda a, exe: _build(
        exe, "blame", "--line-porcelain",
        *([f"-L {a['startLine']},{a['endLine']}"] if a.get("startLine") else []),
        *([a["rev"]] if a.get("rev") else []),
        "--", a["path"],
    ),
    args=(
        _rev("rev", required=False),
        GitArg("path", kind="path", required=True, max_len=1024),
        _int("startLine", lo=1, hi=10_000_000), _int("endLine", lo=1, hi=10_000_000),
    ),
    summary="Per-line attribution.",
))
_register(GitOp(
    "grep", lambda a, exe: _build(
        exe, "grep", "-n", "-I", "--no-color", "-e", a["pattern"],
        *([a["rev"]] if a.get("rev") else []),
        *(["--"] + a["paths"] if a.get("paths") else []),
    ),
    args=(GitArg("pattern", kind="pattern", required=True), _rev("rev", required=False), _p()),
    summary="Search tracked content.",
))

# ── Branches ───────────────────────────────────────────────────────────────────

_register(GitOp(
    "branch_list", lambda a, exe: _build(exe, "branch", "--format=%(refname:short)%00%(objectname)%00%(HEAD)%00%(upstream:short)%00%(upstream:track)", "--list"),
    summary="Local branches with tracking.",
))
_register(GitOp(
    "branch_list_remote", lambda a, exe: _build(exe, "branch", "-r", "--format=%(refname:short)%00%(objectname)"),
    summary="Remote branches.",
))
_register(GitOp(
    "branch_merged", lambda a, exe: _build(exe, "branch", "--merged", a.get("base", "HEAD"), "--format=%(refname:short)"),
    args=(_rev("base", required=False),), summary="Branches merged into a base.",
))
_register(GitOp(
    "branch_create", lambda a, exe: _build(exe, "branch", a["name"], *([a["start"]] if a.get("start") else [])),
    args=(_ref("name"), _rev("start", required=False)), mutating=True, effect="write", risk="caution",
    summary="Create a branch.",
))
_register(GitOp(
    "branch_create_force", lambda a, exe: _build(exe, "branch", "-f", a["name"], *([a["start"]] if a.get("start") else [])),
    args=(_ref("name"), _rev("start", required=False)), mutating=True, effect="write", risk="dangerous",
    summary="Reset a branch to a start point (rewrites it).",
))
_register(GitOp(
    "branch_delete", lambda a, exe: _build(exe, "branch", "-d" if a.get("mode", "safe") == "safe" else "-D", a["name"]),
    args=(_ref("name"), GitArg("mode", kind="enum", allowed=("safe", "force"))),
    mutating=True, effect="write", risk="caution", summary="Delete a merged branch.",
))
_register(GitOp(
    "branch_rename", lambda a, exe: _build(exe, "branch", "-m", a["old"], *([a["new"]] if a.get("new") else [])),
    args=(_ref("old"), _ref("new", required=False)), mutating=True, effect="write", risk="caution",
    summary="Rename a branch.",
))
_register(GitOp(
    "branch_set_upstream", lambda a, exe: _build(exe, "branch", f"--set-upstream-to={a['upstream']}", *([a["branch"]] if a.get("branch") else [])),
    args=(_rev("upstream"), _ref("branch", required=False)), mutating=True, effect="write", risk="caution",
    summary="Set a branch's upstream.",
))
_register(GitOp(
    "branch_unset_upstream", lambda a, exe: _build(exe, "branch", "--unset-upstream", *([a["branch"]] if a.get("branch") else [])),
    args=(_ref("branch", required=False),), mutating=True, effect="write", risk="caution",
    summary="Clear a branch's upstream.",
))

# ── Checkout / switch ───────────────────────────────────────────────────────────

_register(GitOp(
    "checkout", lambda a, exe: _build(exe, "checkout", *([a["target"]] if a.get("target") else []), *_with_paths([], a.get("paths", []))),
    args=(_rev("target", required=False), _p()), mutating=True, effect="write", risk="caution",
    summary="Switch branch / restore paths.",
))
_register(GitOp(
    "switch", lambda a, exe: _build(exe, "switch", *(["--create", a["create"]] if a.get("create") else []), *([a["target"]] if a.get("target") else [])),
    args=(GitArg("create", kind="ref", required=False), _rev("target", required=False)),
    mutating=True, effect="write", risk="caution", summary="Switch (optionally creating) a branch.",
))
_register(GitOp(
    "switch_detach", lambda a, exe: _build(exe, "switch", "--detach", a["target"]),
    args=(_rev("target"),), mutating=True, effect="write", risk="caution",
    summary="Detach HEAD at a revision.",
))
_register(GitOp(
    "restore", lambda a, exe: _build(exe, "restore", *a.get("flags", []), *_with_paths([], a.get("paths", []))),
    args=(GitArg("flags", kind="enum", many=True, allowed=("--staged", "--worktree")), _p(required=False)),
    mutating=True, effect="write", risk="dangerous", summary="Restore paths (discards changes).",
))

# ── Staging ─────────────────────────────────────────────────────────────────────

_register(GitOp(
    "add", lambda a, exe: _build(exe, "add", *a.get("flags", []), *_with_paths([], a.get("paths", []))),
    args=(
        _p(required=True),
        GitArg("flags", kind="enum", many=True, allowed=("-A", "-u", "--all", "--update", "-f")),
    ),
    mutating=True, effect="write", risk="caution", summary="Stage paths.",
))
_register(GitOp(
    "add_patch", lambda a, exe: _build(exe, "add", "-p", *_with_paths([], a.get("paths", []))),
    args=(_p(required=False),), mutating=True, effect="write", risk="caution",
    summary="Interactive staging (not usable without a TTY).",
))
_register(GitOp(
    "reset_paths", lambda a, exe: _build(exe, "reset", "-q", "HEAD", *_with_paths([], a.get("paths", []))),
    args=(_p(required=True),), mutating=True, effect="write", risk="caution",
    summary="Unstage paths (keeps working tree).",
))
_register(GitOp(
    "restore_staged", lambda a, exe: _build(exe, "restore", "--staged", *_with_paths([], a.get("paths", []))),
    args=(_p(required=False),), mutating=True, effect="write", risk="caution",
    summary="Unstage paths.",
))
_register(GitOp(
    "rm", lambda a, exe: _build(exe, "rm", *a.get("flags", []), *_with_paths([], a.get("paths", []))),
    args=(_p(required=True), GitArg("flags", kind="enum", many=True, allowed=("-r", "--cached", "-f"))),
    mutating=True, effect="write", risk="caution", summary="Remove tracked paths.",
))
_register(GitOp(
    "mv", lambda a, exe: _build(exe, "mv", a["src"], a["dst"]),
    args=(GitArg("src", kind="path", required=True), GitArg("dst", kind="path", required=True)),
    mutating=True, effect="write", risk="caution", summary="Move/rename a tracked path.",
))
# `git apply` reads the patch from stdin (the executor's `input_text`). It is the
# no-TTY mechanism behind hunk staging and `git_apply_patch`. Path safety is
# enforced by `git/diffs.parse_unified_diff` before git sees the bytes.
_register(GitOp(
    "apply_cached", lambda a, exe: _build(exe, "apply", "--cached", "--whitespace=nowarn", "-"),
    mutating=True, effect="write", risk="caution", summary="Apply a patch to the index (stage hunks).",
))
_register(GitOp(
    "apply_cached_reverse", lambda a, exe: _build(exe, "apply", "--cached", "--reverse", "--whitespace=nowarn", "-"),
    mutating=True, effect="write", risk="caution", summary="Reverse-apply a patch to the index (unstage hunks).",
))
_register(GitOp(
    "apply_worktree", lambda a, exe: _build(exe, "apply", "--whitespace=nowarn", "-"),
    mutating=True, effect="write", risk="caution", summary="Apply a patch to the working tree.",
))

# ── Commit ──────────────────────────────────────────────────────────────────────

_register(GitOp(
    "commit", lambda a, exe: _build(
        exe, "commit",
        *(["--amend"] if a.get("amend") == "true" else []),
        *(["--no-edit"] if a.get("noEdit") == "true" else []),
        *(["--allow-empty"] if a.get("allowEmpty") == "true" else []),
        *(["--no-verify"] if a.get("noVerify") == "true" else []),
        *([f"--author={a['author']}"] if a.get("author") else []),
        *(["-m", a["message"]] if a.get("message") else []),
        *(["--"] + a["paths"] if a.get("paths") else []),
    ),
    args=(
        GitArg("message", kind="message", required=False, max_len=10_000),
        GitArg("amend", kind="enum", required=False, allowed=("true", "false")),
        GitArg("noEdit", kind="enum", required=False, allowed=("true", "false")),
        GitArg("allowEmpty", kind="enum", required=False, allowed=("true", "false")),
        GitArg("noVerify", kind="enum", required=False, allowed=("true", "false")),
        GitArg("author", kind="text", required=False, max_len=300),
        _p(),
    ),
    mutating=True, effect="write", risk="caution", summary="Create a commit.",
))

# ── Remotes ──────────────────────────────────────────────────────────────────────

_register(GitOp("remote_list", lambda a, exe: _build(exe, "remote", "-v"), summary="Remotes with URLs."))
_register(GitOp(
    "remote_get_url", lambda a, exe: _build(exe, "remote", "get-url", *(["--push"] if a.get("push") == "true" else []), a["name"]),
    args=(_ref("name"), GitArg("push", kind="enum", required=False, allowed=("true", "false"))),
    summary="One remote's URL.",
))
_register(GitOp(
    "remote_add", lambda a, exe: _build(exe, "remote", "add", a["name"], a["url"]),
    args=(_ref("name"), GitArg("url", kind="text", required=True, max_len=2_000)),
    mutating=True, effect="write", risk="caution", summary="Add a remote.",
))
_register(GitOp(
    "remote_remove", lambda a, exe: _build(exe, "remote", "remove", a["name"]),
    args=(_ref("name"),), mutating=True, effect="write", risk="caution", summary="Remove a remote.",
))
_register(GitOp(
    "remote_set_url", lambda a, exe: _build(exe, "remote", "set-url", *(["--push"] if a.get("push") == "true" else []), a["name"], a["url"]),
    args=(_ref("name"), GitArg("url", kind="text", required=True, max_len=2_000),
          GitArg("push", kind="enum", required=False, allowed=("true", "false"))),
    mutating=True, effect="write", risk="caution", summary="Change a remote URL.",
))

# ── Fetch / pull / push ───────────────────────────────────────────────────────────

_register(GitOp(
    "fetch", lambda a, exe: _build(
        exe, "fetch", *_remote_target(a), *(["--all"] if a.get("all") == "true" else []),
        *(["--prune"] if a.get("prune") == "true" else []),
        *(["--tags"] if a.get("tags") == "true" else []),
        *(["--depth", str(a["depth"])] if a.get("depth") else []),
    ),
    args=(
        _ref("remote", required=False), _ref("branch", required=False),
        GitArg("all", kind="enum", required=False, allowed=("true", "false")),
        GitArg("prune", kind="enum", required=False, allowed=("true", "false")),
        GitArg("tags", kind="enum", required=False, allowed=("true", "false")),
        _int("depth", lo=1, hi=1_000_000),
    ),
    mutating=True, effect="write", network=True, risk="caution", timeout_s=180,
    summary="Fetch from a remote.",
))
_register(GitOp(
    "pull", lambda a, exe: _build(
        exe, "pull", *a.get("strategy_flag", []),
        *_remote_target(a),
    ),
    args=(
        GitArg("strategy_flag", kind="enum", many=True, allowed=("--ff-only", "--rebase", "--no-rebase", "--no-commit")),
        _ref("remote", required=False), _ref("branch", required=False),
    ),
    mutating=True, effect="write", network=True, risk="caution", timeout_s=180,
    summary="Fetch + integrate.",
))
_register(GitOp(
    "push", lambda a, exe: _build(
        exe, "push",
        *(["--set-upstream"] if a.get("setUpstream") == "true" else []),
        *(["--tags"] if a.get("tags") == "true" else []),
        *(["--force-with-lease"] if a.get("forceWithLease") == "true" else []),
        *(["--force"] if a.get("force") == "true" else []),
        *_remote_target(a),
    ),
    args=(
        _ref("remote", required=False), _ref("branch", required=False),
        GitArg("setUpstream", kind="enum", required=False, allowed=("true", "false")),
        GitArg("tags", kind="enum", required=False, allowed=("true", "false")),
        GitArg("forceWithLease", kind="enum", required=False, allowed=("true", "false")),
        GitArg("force", kind="enum", required=False, allowed=("true", "false")),
    ),
    mutating=True, effect="external_action", network=True, risk="caution", timeout_s=180,
    summary="Send commits to a remote.",
))
_register(GitOp(
    "push_refspec", lambda a, exe: _build(exe, "push", *(["--force-with-lease"] if a.get("forceWithLease") == "true" else []), a["remote"], a["refspec"]),
    args=(_ref("remote"), GitArg("refspec", kind="refspec", required=True, max_len=400),
          GitArg("forceWithLease", kind="enum", required=False, allowed=("true", "false"))),
    mutating=True, effect="external_action", network=True, risk="dangerous", timeout_s=180,
    summary="Push an explicit refspec (no leading + allowed).",
))
_register(GitOp(
    "push_delete", lambda a, exe: _build(exe, "push", a["remote"], "--delete", a["branch"]),
    args=(_ref("remote"), _ref("branch")), mutating=True, effect="external_action", network=True,
    risk="dangerous", timeout_s=180, summary="Delete a remote branch.",
))

# ── Merge / rebase / cherry-pick / revert ──────────────────────────────────────────

_register(GitOp(
    "merge", lambda a, exe: _build(
        exe, "merge",
        *(["--no-ff"] if a.get("noFf") == "true" else []),
        *(["--ff-only"] if a.get("ffOnly") == "true" else []),
        *(["--no-commit"] if a.get("noCommit") == "true" else []),
        *(["--squash"] if a.get("squash") == "true" else []),
        *(["-m", a["message"]] if a.get("message") else []),
        a["target"],
    ),
    args=(
        _rev("target"),
        GitArg("noFf", kind="enum", required=False, allowed=("true", "false")),
        GitArg("ffOnly", kind="enum", required=False, allowed=("true", "false")),
        GitArg("noCommit", kind="enum", required=False, allowed=("true", "false")),
        GitArg("squash", kind="enum", required=False, allowed=("true", "false")),
        GitArg("message", kind="message", required=False, max_len=10_000),
    ),
    mutating=True, effect="write", risk="caution", summary="Merge a branch/revision.",
))
_register(GitOp("merge_abort", lambda a, exe: _build(exe, "merge", "--abort"),
                mutating=True, effect="write", risk="dangerous", summary="Abort a merge."))
_register(GitOp("merge_continue", lambda a, exe: _build(exe, "merge", "--continue"),
                mutating=True, effect="write", risk="caution", summary="Continue a merge."))
_register(GitOp(
    "rebase", lambda a, exe: _build(
        exe, "rebase",
        *(["--autosquash"] if a.get("autosquash") == "true" else []),
        *(["--onto", a["onto"]] if a.get("onto") else []),
        *(["--autostash"] if a.get("autostash") == "true" else []),
        a["upstream"],
    ),
    args=(
        _rev("upstream"), _rev("onto", required=False),
        GitArg("autosquash", kind="enum", required=False, allowed=("true", "false")),
        GitArg("autostash", kind="enum", required=False, allowed=("true", "false")),
    ),
    mutating=True, effect="write", risk="dangerous", timeout_s=180, summary="Rebase onto an upstream (rewrites commits).",
))
# The interactive rebase is driven by a machine-written SEQUENCE EDITOR (no TTY):
# `git/rebase_plan.py` + `git/_sequence_editor.py`. `-i` is always set here.
_register(GitOp(
    "rebase_interactive", lambda a, exe: _build(
        exe, "rebase", "-i",
        *(["--autosquash"] if a.get("autosquash") == "true" else []),
        *(["--onto", a["onto"]] if a.get("onto") else []),
        *(["--autostash"] if a.get("autostash") == "true" else []),
        a["upstream"],
    ),
    args=(
        _rev("upstream"), _rev("onto", required=False),
        GitArg("autosquash", kind="enum", required=False, allowed=("true", "false")),
        GitArg("autostash", kind="enum", required=False, allowed=("true", "false")),
    ),
    mutating=True, effect="write", risk="dangerous", network=False, timeout_s=180,
    summary="Interactive rebase driven by a machine edit plan (squash/fixup/drop/reorder/reword).",
))
_register(GitOp("rebase_abort", lambda a, exe: _build(exe, "rebase", "--abort"),
                mutating=True, effect="write", risk="dangerous", summary="Abort a rebase."))
_register(GitOp("rebase_continue", lambda a, exe: _build(exe, "rebase", "--continue"),
                mutating=True, effect="write", risk="caution", summary="Continue a rebase."))
_register(GitOp("rebase_skip", lambda a, exe: _build(exe, "rebase", "--skip"),
                mutating=True, effect="write", risk="caution", summary="Skip the current rebase commit."))
_register(GitOp(
    "cherry_pick", lambda a, exe: _build(
        exe, "cherry-pick",
        *(["--no-commit"] if a.get("noCommit") == "true" else []),
        *(["-x"] if a.get("recordOrigin") == "true" else []),
        *a["commits"],
    ),
    args=(GitArg("commits", kind="rev", many=True, required=True),
          GitArg("noCommit", kind="enum", required=False, allowed=("true", "false")),
          GitArg("recordOrigin", kind="enum", required=False, allowed=("true", "false"))),
    mutating=True, effect="write", risk="caution", summary="Copy commits onto the current branch.",
))
_register(GitOp("cherry_pick_abort", lambda a, exe: _build(exe, "cherry-pick", "--abort"),
                mutating=True, effect="write", risk="dangerous", summary="Abort a cherry-pick."))
_register(GitOp("cherry_pick_continue", lambda a, exe: _build(exe, "cherry-pick", "--continue"),
                mutating=True, effect="write", risk="caution", summary="Continue a cherry-pick."))
_register(GitOp(
    "revert", lambda a, exe: _build(
        exe, "revert", "--no-edit", *(["--no-commit"] if a.get("noCommit") == "true" else []), *a["commits"],
    ),
    args=(GitArg("commits", kind="rev", many=True, required=True),
          GitArg("noCommit", kind="enum", required=False, allowed=("true", "false"))),
    mutating=True, effect="write", risk="caution", summary="Create inverse commits.",
))
_register(GitOp("revert_abort", lambda a, exe: _build(exe, "revert", "--abort"),
                mutating=True, effect="write", risk="dangerous", summary="Abort a revert."))
_register(GitOp("revert_continue", lambda a, exe: _build(exe, "revert", "--continue"),
                mutating=True, effect="write", risk="caution", summary="Continue a revert."))

# ── Reset ──────────────────────────────────────────────────────────────────────────

_register(GitOp(
    "reset", lambda a, exe: _build(exe, "reset", f"--{a['mode']}", a.get("target", "HEAD")),
    args=(GitArg("mode", kind="enum", required=True, allowed=("soft", "mixed", "hard", "merge", "keep")),
          _rev("target", required=False)),
    mutating=True, effect="write", risk="dangerous", summary="Move HEAD / index / working tree.",
))

# ── Stash ────────────────────────────────────────────────────────────────────────────

_register(GitOp(
    "stash_push", lambda a, exe: _build(
        exe, "stash", "push",
        *(["--include-untracked"] if a.get("includeUntracked") == "true" else []),
        *(["--all"] if a.get("includeIgnored") == "true" else []),
        *(["--keep-index"] if a.get("keepIndex") == "true" else []),
        *(["-m", a["message"]] if a.get("message") else []),
        *(["--"] + a["paths"] if a.get("paths") else []),
    ),
    args=(
        GitArg("includeUntracked", kind="enum", required=False, allowed=("true", "false")),
        GitArg("includeIgnored", kind="enum", required=False, allowed=("true", "false")),
        GitArg("keepIndex", kind="enum", required=False, allowed=("true", "false")),
        GitArg("message", kind="message", required=False, max_len=2_000), _p(),
    ),
    mutating=True, effect="write", risk="caution", summary="Stash changes.",
))
_register(GitOp("stash_list", lambda a, exe: _build(exe, "stash", "list", "--format=%gd%x00%H%x00%gs%x00%ci"),
                summary="List stashes."))
_register(GitOp("stash_show", lambda a, exe: _build(exe, "stash", "show", "-p", "--no-color", a.get("ref", "stash@{0}")),
                args=(GitArg("ref", kind="text", required=False, max_len=64),), summary="Show a stash's diff."))
_register(GitOp("stash_apply", lambda a, exe: _build(exe, "stash", "apply", *(["--index"] if a.get("index") == "true" else []), a.get("ref", "stash@{0}")),
                args=(GitArg("ref", kind="text", required=False, max_len=64),
                      GitArg("index", kind="enum", required=False, allowed=("true", "false"))),
                mutating=True, effect="write", risk="caution", summary="Apply a stash (keeps it)."))
_register(GitOp("stash_pop", lambda a, exe: _build(exe, "stash", "pop", *(["--index"] if a.get("index") == "true" else []), a.get("ref", "stash@{0}")),
                args=(GitArg("ref", kind="text", required=False, max_len=64),
                      GitArg("index", kind="enum", required=False, allowed=("true", "false"))),
                mutating=True, effect="write", risk="caution", summary="Apply and drop a stash."))
_register(GitOp("stash_drop", lambda a, exe: _build(exe, "stash", "drop", a["ref"]),
                args=(GitArg("ref", kind="text", required=True, max_len=64),),
                mutating=True, effect="write", risk="dangerous", summary="Discard a stash."))
_register(GitOp("stash_clear", lambda a, exe: _build(exe, "stash", "clear"),
                mutating=True, effect="write", risk="destructive", summary="Discard all stashes."))
_register(GitOp("stash_branch", lambda a, exe: _build(exe, "stash", "branch", a["name"], a.get("ref", "stash@{0}")),
                args=(_ref("name"), GitArg("ref", kind="text", required=False, max_len=64)),
                mutating=True, effect="write", risk="caution", summary="Branch from a stash."))

# ── Tags ──────────────────────────────────────────────────────────────────────────────

_register(GitOp("tag_list", lambda a, exe: _build(exe, "tag", "--list", "--format=%(refname:short)%00%(objecttype)%00%(objectname)"),
                summary="List tags."))
_register(GitOp(
    "tag_create", lambda a, exe: _build(
        exe, "tag", *(["-a"] if a.get("annotated") == "true" else []),
        *(["-m", a["message"]] if a.get("message") else []),
        *(["-s"] if a.get("signed") == "true" else []),
        *(["-f"] if a.get("force") == "true" else []),
        a["name"], *([a["target"]] if a.get("target") else []),
    ),
    args=(
        _ref("name"),
        GitArg("annotated", kind="enum", required=False, allowed=("true", "false")),
        GitArg("signed", kind="enum", required=False, allowed=("true", "false")),
        GitArg("force", kind="enum", required=False, allowed=("true", "false")),
        GitArg("message", kind="message", required=False, max_len=10_000),
        _rev("target", required=False),
    ),
    mutating=True, effect="write", risk="caution", summary="Create a tag.",
))
_register(GitOp("tag_delete", lambda a, exe: _build(exe, "tag", "-d" if a.get("mode", "safe") == "safe" else "-D", *a["names"]),
                args=(GitArg("names", kind="ref", many=True, required=True),
                      GitArg("mode", kind="enum", required=False, allowed=("safe", "force"))),
                mutating=True, effect="write", risk="dangerous", summary="Delete local tags."))
_register(GitOp("tag_show", lambda a, exe: _build(exe, "show", "--no-color", a["name"]),
                args=(_ref("name"),), summary="Show a tag's object."))
_register(GitOp(
    "tag_push", lambda a, exe: _build(exe, "push", *(["--force"] if a.get("force") == "true" else []), a["remote"], "refs/tags/" + a["name"]),
    args=(_ref("remote"), _ref("name"), GitArg("force", kind="enum", required=False, allowed=("true", "false"))),
    mutating=True, effect="external_action", network=True, risk="dangerous", timeout_s=180,
    summary="Push one tag.",
))

# ── Worktrees ──────────────────────────────────────────────────────────────────────────

_register(GitOp("worktree_list", lambda a, exe: _build(exe, "worktree", "list", "--porcelain"),
                summary="List worktrees."))
_register(GitOp(
    "worktree_add", lambda a, exe: _build(exe, "worktree", "add", *(["--detach"] if a.get("detach") == "true" else []),
                                          *(["-b", a["branch"]] if a.get("branch") else []), a["path"], *([a["ref"]] if a.get("ref") else [])),
    args=(GitArg("path", kind="path", required=True, max_len=1024),
          GitArg("branch", kind="ref", required=False), _rev("ref", required=False),
          GitArg("detach", kind="enum", required=False, allowed=("true", "false"))),
    mutating=True, effect="write", risk="caution", summary="Create a linked worktree.",
))
_register(GitOp("worktree_remove", lambda a, exe: _build(exe, "worktree", "remove", *(["--force"] if a.get("force") == "true" else []), a["path"]),
                args=(GitArg("path", kind="path", required=True, max_len=1024),
                      GitArg("force", kind="enum", required=False, allowed=("true", "false"))),
                mutating=True, effect="write", risk="dangerous", summary="Remove a worktree."))
_register(GitOp("worktree_move", lambda a, exe: _build(exe, "worktree", "move", a["src"], a["dst"]),
                args=(GitArg("src", kind="path", required=True, max_len=1024),
                      GitArg("dst", kind="path", required=True, max_len=1024)),
                mutating=True, effect="write", risk="caution", summary="Move a worktree."))
_register(GitOp("worktree_prune", lambda a, exe: _build(exe, "worktree", "prune", "-v"),
                mutating=True, effect="write", risk="caution", summary="Prune stale worktree metadata."))

# ── Submodules ──────────────────────────────────────────────────────────────────────────

_register(GitOp("submodule_status", lambda a, exe: _build(exe, "submodule", "status", "--recursive"),
                summary="Submodule status."))
_register(GitOp("submodule_init", lambda a, exe: _build(exe, "submodule", "init", *a.get("paths", [])),
                args=(_p(required=False),), mutating=True, effect="write", risk="caution",
                summary="Register submodules."))
_register(GitOp("submodule_update", lambda a, exe: _build(exe, "submodule", "update", "--init", "--recursive",
                                                          *(["--remote"] if a.get("remote") == "true" else []), *a.get("paths", [])),
                args=(_p(required=False), GitArg("remote", kind="enum", required=False, allowed=("true", "false"))),
                mutating=True, effect="external_action", network=True, risk="caution", timeout_s=300,
                summary="Fetch and check out submodule contents."))
_register(GitOp("submodule_sync", lambda a, exe: _build(exe, "submodule", "sync", "--recursive", *a.get("paths", [])),
                args=(_p(required=False),), mutating=True, effect="write", risk="caution",
                summary="Sync submodule URLs."))

# ── LFS ────────────────────────────────────────────────────────────────────────────────

_register(GitOp("lfs_status", lambda a, exe: _build(exe, "lfs", "status", "--porcelain"), summary="LFS status."))
_register(GitOp("lfs_ls_files", lambda a, exe: _build(exe, "lfs", "ls-files", "-n"), summary="LFS-tracked files."))
_register(GitOp("lfs_fetch", lambda a, exe: _build(exe, "lfs", "fetch", *([a["remote"]] if a.get("remote") else [])),
                args=(_ref("remote", required=False),), mutating=True, effect="external_action",
                network=True, risk="caution", timeout_s=600, summary="Fetch LFS objects."))
_register(GitOp("lfs_pull", lambda a, exe: _build(exe, "lfs", "pull", *([a["remote"]] if a.get("remote") else [])),
                args=(_ref("remote", required=False),), mutating=True, effect="external_action",
                network=True, risk="caution", timeout_s=600, summary="Fetch + check out LFS objects."))

# ── Bisect ──────────────────────────────────────────────────────────────────────────────

_register(GitOp("bisect_start", lambda a, exe: _build(exe, "bisect", "start", *([a["bad"]] if a.get("bad") else []), *a.get("good", [])),
                args=(_rev("bad", required=False), GitArg("good", kind="rev", many=True, required=False)),
                mutating=True, effect="write", risk="dangerous", summary="Begin a bisect."))
_register(GitOp("bisect_good", lambda a, exe: _build(exe, "bisect", "good", *([a["rev"]] if a.get("rev") else [])),
                args=(_rev("rev", required=False),), mutating=True, effect="write", risk="caution",
                summary="Mark a revision good."))
_register(GitOp("bisect_bad", lambda a, exe: _build(exe, "bisect", "bad", *([a["rev"]] if a.get("rev") else [])),
                args=(_rev("rev", required=False),), mutating=True, effect="write", risk="caution",
                summary="Mark a revision bad."))
_register(GitOp("bisect_skip", lambda a, exe: _build(exe, "bisect", "skip"),
                mutating=True, effect="write", risk="caution", summary="Skip a bisect step."))
_register(GitOp("bisect_reset", lambda a, exe: _build(exe, "bisect", "reset", *([a["rev"]] if a.get("rev") else [])),
                args=(_rev("rev", required=False),), mutating=True, effect="write", risk="caution",
                summary="End a bisect."))
_register(GitOp("bisect_log", lambda a, exe: _build(exe, "bisect", "log"), summary="Bisect log (presence = in progress)."))

# ── Clean ────────────────────────────────────────────────────────────────────────────────

_register(GitOp(
    "clean_preview", lambda a, exe: _build(
        exe, "clean", "-n" + ("d" if a.get("directories") == "true" else "")
        + ("x" if a.get("inclIgnored") == "true" else ""),
    ),
    args=(GitArg("directories", kind="enum", required=False, allowed=("true", "false")),
          GitArg("inclIgnored", kind="enum", required=False, allowed=("true", "false"))),
    summary="Preview what clean would delete.",
))
_register(GitOp(
    "clean", lambda a, exe: _build(
        exe, "clean", "-f" + ("d" if a.get("directories") == "true" else "")
        + ("x" if a.get("inclIgnored") == "true" else ""),
    ),
    args=(GitArg("directories", kind="enum", required=False, allowed=("true", "false")),
          GitArg("inclIgnored", kind="enum", required=False, allowed=("true", "false"))),
    mutating=True, effect="write", risk="destructive", summary="Delete untracked files.",
))

# ── Config ──────────────────────────────────────────────────────────────────────────────────

_register(GitOp("config_list", lambda a, exe: _build(exe, "config", *a.get("scope", []), "--list", "--null"),
                args=(GitArg("scope", kind="enum", many=True, required=False,
                             allowed=("--system", "--global", "--local", "--worktree")),),
                summary="List config entries."))
_register(GitOp("config_get", lambda a, exe: _build(exe, "config", *a.get("scope", []), "--get", a["key"]),
                args=(GitArg("key", kind="config_key", required=True),
                      GitArg("scope", kind="enum", many=True, required=False,
                             allowed=("--system", "--global", "--local", "--worktree"))),
                summary="Read a config value."))
_register(GitOp("config_set", lambda a, exe: _build(exe, "config", *a.get("scope", []), a["key"], a["value"]),
                args=(GitArg("key", kind="config_key", required=True),
                      GitArg("value", kind="text", required=True, max_len=2_000),
                      GitArg("scope", kind="enum", many=True, required=False,
                             allowed=("--global", "--local", "--worktree"))),
                mutating=True, effect="write", risk="caution", summary="Set a config value.",
                ),)

# ── Hooks / ignore (file-based; the executor still runs none of them) ──────────

_register(GitOp("ignore_check", lambda a, exe: _build(exe, "check-ignore", "-v", "--", a["path"]),
                args=(GitArg("path", kind="path", required=True, max_len=1024),),
                summary="Whether a path is ignored and by which rule."))
_register(GitOp("hook_path", lambda a, exe: _build(exe, "rev-parse", "--git-path", "hooks"),
                summary="Resolve the hooks directory."))
_register(GitOp("lfs_attr", lambda a, exe: _build(exe, "check-attr", "-a", "--", a["path"]),
                args=(GitArg("path", kind="path", required=True, max_len=1024),),
                summary="Attributes (LFS filter) for a path."))


# ── Builder helpers (kept out of the lambdas for readability) ──────────────────

def _remote_target(a: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if a.get("remote"):
        out.append(a["remote"])
    if a.get("branch"):
        out.append(a["branch"])
    return out


def _diff_opts(a: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if a.get("contextLines") is not None:
        out.append(f"--unified={a['contextLines']}")
    if a.get("base"):
        out.append(a["base"])
    if a.get("paths"):
        out += ["--", *a["paths"]]
    return out


def _log_format() -> list[str]:
    # A NUL-delimited, one-record-per-commit format the parser can split exactly.
    return ["--format=%H%x00%h%x00%an%x00%ae%x00%aI%x00%P%x00%s%x00%b%x01"]


def _show_opts(a: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if a.get("stat") == "true":
        out.append("--stat")
    else:
        out += ["--patch", "--no-renames"]
    if a.get("paths"):
        out += ["--", *a["paths"]]
    return out


# Backfill the executable into every builder signature: op.build(args, exe).
# The catalog builders above are declared as `lambda a, exe: ...`; expose a helper
# so `executor` can uniformly call them.
for _op in list(CATALOG.values()):
    pass

__all__ = ["CATALOG"]
