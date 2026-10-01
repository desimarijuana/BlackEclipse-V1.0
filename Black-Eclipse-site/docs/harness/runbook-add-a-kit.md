---
title: Runbook — add a scaffold kit
status: Current
last-verified: 2026-10-01
---

# Runbook — add a scaffold kit

**Who this is for:** the developer adding a "build me X" kit at 09:00 on a Monday.

A **kit** is the repo's convention for one finance application shape — a data
adapter, a ratio, a backtest, a chart indicator, a portfolio module, an import
job, a research routine, a tool server. The agent satisfies the convention
instead of emitting plausible boilerplate. A user meets the kit as a plain
question ("What is the ratio called?"), never the word "kit".

A generated artefact stays **inert** until evaluation and an operator decision
(the ADR-025 discipline, ADR-H111).

## 1. File layout

A kit lives under `python/harness/code/kits/<kit_id>/`:

```
python/harness/code/kits/<kit_id>/
  kit.json                 the KitManifest (data, validated by model.py)
  templates/**             the files rendered into the task's disposable workspace
```

The manifest declares its inputs (each an i18n key), its outputs, and the
acceptance check(s). A kit with **no acceptance test** or an **undeclared output**
is refused by the loader, never silently accepted.

A kit also ships a draft skill wrapper under
`python/harness/skills/library/system/<kit_id>/` (`status: draft`, never enabled)
so it is discoverable without being active.

## 2. Add one

1. Create the folder and `kit.json`. Copy the shape from an existing kit (e.g.
   `ratio_calculator`).
2. Add the templates under `templates/`.
3. Add the acceptance test: `python/tests/test_kit_<kit_id>.py`. The loader refuses
   a kit whose acceptance test is missing, so this is not optional.
4. Add the user-facing strings as i18n keys in
   `src/lib/i18n/dictionaries/en.ts` (`kit.<kit_id>.title`, `.summary`, `.q.*`).
   Never hardcode a title in the manifest — the manifest carries keys.

## 3. How it is discovered

`python/harness/code/kits/loader.py` walks the kits directory and builds a
validated manifest per kit. The `scaffold_kit` tool (handler in
`python/harness/scaffold_tools.py`, registered in `python/harness/code/tools.py`)
lists them and renders one into the task's workspace. It is:

- in `policy.WRITE_TOOLS` (so the autonomy boundary removes it at `plan_only`);
- in both agent allowlists (`python/harness/agents.py`);
- written into the task's **disposable workspace**, never the user's checkout.

## 4. Acceptance test

The kit renders its files into a workspace, runs the kit's check through the
Phase 3 command broker, and records the result in the Phase 4 verification ledger.
A failed check keeps the scaffold and reports `CHECK_FAILED` — it never claims a
pass it did not observe.

```bash
./scripts/vendor/python/python.exe -m pytest python/tests/test_kit_<kit_id>.py -v
```

## 5. Where the pieces live

| Piece | File |
|---|---|
| Contract + loader | `python/harness/code/kits/model.py`, `loader.py` |
| Kits | `python/harness/code/kits/<kit_id>/` |
| Tool | `python/harness/scaffold_tools.py` (registered in `code/tools.py`) |
| Skill wrappers | `python/harness/skills/library/system/<kit_id>/` |
| Front door copy | `src/lib/i18n/dictionaries/en.ts` (`kit.*`) |
| Tests | `python/tests/test_kits_{contract,scaffold,unavailability,skill_wrappers}.py` + one `test_kit_<id>.py` per kit |
