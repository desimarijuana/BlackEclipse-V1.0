---
title: Desktop Size — Download Slimming and Optional Packs
status: Proposed
last-verified: 2026-11-10
---

# Desktop size plan

**Goal (user's words):** the *download* should be small like a normal app; the
*installed* size may be whatever is appropriate; nothing that works today may
stop working.

**Hard constraint:** no feature is removed. Anything heavy becomes **optional**,
chosen on the onboarding page, installable later.

---

## 2026-11-10 — S0 + S1 implemented

### Measured results

| | Before | After S0 (junk) | After S1 (packs split) |
| --- | ---: | ---: | ---: |
| Core app folder | 1,258 MB | 1,144 MB | **731 MB** |
| Core + bundled Node + shell | 1,345 MB | 1,231 MB | **819 MB** |

Junk removed: **114 MB** (harness tests 52, site-package tests 47, dist-info 6,
`node_modules/typescript` 9).

Packs split out of the core (all lazily imported):

| Pack | Contents | Size |
| --- | --- | ---: |
| ml | xgboost, sklearn, scipy, scipy.libs | 168 MB |
| charts | plotly, matplotlib | 53 MB |
| documents | pymupdf | 48 MB |
| computer | winsdk | 41 MB |
| browser | playwright | ~105 MB |

`comtypes` deliberately **stays in core** — it is imported during the boot sweep,
so moving it would break startup.

`dist/packs/manifest.json` lists each pack, its packages and its byte size, ready
for the download manager.

**Verified:** the core-only build boots and serves the application
(`HTTP 200`, 90,904 bytes) with **zero** `ModuleNotFoundError` / `ImportError`.

### Speed baseline (measured, `npm run desktop:bench`)

| Stage | Result |
| --- | --- |
| Window visible | **1.4 s** |
| Server answering (cold, empty data dir) | **6.0 s** (3-run average) |

Target was < 4 s. The shell is not the bottleneck — the app's own startup
(instrumentation, journal broker, market warm-up) holds the first response.
Recording the number as the baseline for a later startup pass.

### Two editions

| Edition | File | Download | Contains |
| --- | --- | --- | ---: |
| **Slim** (default) | `BlackEclipse-Setup-<v>.exe` | **141 MB** | core only; packs added later |
| **Offline** | `BlackEclipse-Setup-<v>-full.exe` | ~? MB | core + all five packs, no network needed |

Both install per-user and preserve data. The slim edition is the recommended
download; the offline edition exists for machines with no network.

Every slim build also writes `BlackEclipse-Setup.exe`, a byte-identical copy
under a version-independent name. That is the **public download contract**:
the README buttons and the release page link to
`releases/latest/download/<stable name>`, so they never change between versions.

| Platform | Stable name | Produced by |
| --- | --- | --- |
| Windows (slim) | `BlackEclipse-Setup.exe` | `scripts/desktop-installer.js` |
| macOS | `BlackEclipse-mac-<arch>.dmg` | `scripts/desktop-bundle.js` (`buildMac`) |
| Linux | `BlackEclipse-linux-<arch>.deb` | `scripts/desktop-bundle.js` (`buildDeb`) |

The macOS name keeps the architecture because only one arch is produced per
runner and a Mac cannot run the other: the button links `arm64` explicitly
rather than handing an Intel Mac a binary it can never launch. The Windows
installer script deletes its alias on an offline-only build (a stale alias must
never be published) and lists it in `SHA256SUMS.txt`; `desktop-release.yml`
fails the build when any alias is missing.

Packaging command:

```
npm run desktop:installer           # slim
npm run desktop:installer -- --full # offline edition (needs dist/packs present)
```

`dist/packs/manifest.json` lists every pack with its packages and byte size, and
`npm run desktop:packs install <name> --target <app>` adds or removes one.

### Still to do (S2–S4)

S2 stub downloader, S3 onboarding chooser + Settings › Components, S4 friendly
pack-missing errors. **They are blocked on a published release URL** — a
downloader cannot be verified end-to-end against an asset that does not exist
yet. Everything they consume (pack split, manifest, per-pack folders, pack
manager, both installer editions) is in place.



Total **1,411 MB** · installer **268 MB** · compression ≈ 5:1.

| Block | MB | Nature |
| --- | ---: | --- |
| Vendored Python (`scripts/vendor/python`) | 818 | interpreter + stdlib + site-packages |
| Next server tree (`.next-desktop/server`) | 221 | 456 routes; inherent |
| `node_modules` | 124 | `@napi-rs` 42, next 25, `@img` 19, sqlite 16, typescript 9, playwright-core 6 |
| Python harness source | 96 | **52 of it is `python/tests`** |
| Bundled `node.exe` | 83 | required |
| `public/` | 7 | required |
| Tauri shell | 3 | required |

### Largest site-packages

| Package | MB | Imported how |
| --- | ---: | --- |
| playwright | 105 | lazy (`browser/providers/local_chromium.py`) |
| scipy | 83 + 19 libs | transitive (sklearn/xgboost) |
| xgboost | 55 | lazy (`ml/adapters.py:522`) |
| pymupdf | 48 | lazy (`documents/edit/pdf_ops.py:70`) |
| winsdk | 41 | lazy (`computer/ocr/windows.py:27`) |
| pandas | 41 | core |
| plotly | 33 | lazy (`charts/plotly_figure.py:556`) |
| sklearn | 32 | lazy (`ml/adapters.py:510`) |
| numpy | 22 + 20 libs | core |
| matplotlib | 21 | lazy, 7 call sites |
| comtypes | 17 | computer-control |
| PIL | 14 | core (22 call sites) |

**Key finding:** every heavy optional package is imported *inside a function*
(`# noqa: PLC0415`), not at module top. The harness is already written to run
without them — the only thing missing is a friendly "install this pack" error.

---

## 2. What is pure junk (safe to delete, zero behaviour change)

| Item | MB |
| --- | ---: |
| `python/tests/` | 52 |
| `tests/` inside site-packages | 47 |
| `*.dist-info` metadata | 7 |
| `__pycache__` (regenerated at runtime) | ~100 at build time |
| `node_modules/typescript` (build-only) | 9 |
| `.nft.json` tracing manifests (build-only) | <1 |

**≈ 115 MB with no functional risk.**

---

## 3. Pack split

### Core — required, always installed
Next server, `node.exe`, Python interpreter + stdlib, harness source (minus
tests), core site-packages (numpy, pandas, PIL, pydantic, fastapi, langchain,
langgraph, httpx, …).

### Optional packs — chosen on onboarding, installable later

| Pack | Contents | Download | What it unlocks |
| --- | --- | ---: | --- |
| **Browser automation** | playwright | ~105 MB | The browser tool |
| **Machine learning** | xgboost, sklearn, scipy | ~189 MB | ML adapters, model training |
| **Documents** | pymupdf | ~48 MB | PDF editing/inspection |
| **Computer control** | winsdk, comtypes | ~58 MB | Windows UI automation, OCR |
| **Charts (server-side)** | plotly, matplotlib | ~54 MB | Python-rendered figures |

Recommended defaults on onboarding: **none pre-selected except Documents** (it
backs the PDF features most people touch). Each row shows size, one-line value,
and a Recommended/Advanced tag.

---

## 4. Download model

```
BlackEclipse-Setup.exe   ~12 MB   (shell + downloader + onboarding)
        │
        ├─ first run: fetch CORE pack (~130–150 MB, resumable, SHA-256 verified)
        │      → app starts
        └─ onboarding: tick optional packs → fetched now or later
```

- Packs land in `%LOCALAPPDATA%\BlackEclipse\packs\<name>\`
- Enabled by appending to `PYTHONPATH` (the supervisor already sets it), so
  enabling/disabling never rewrites the install
- Settings › Components: add/remove packs any time
- **Offline option:** a full offline installer remains available for machines
  with no network (same bytes, one file)

### Honest floor

A 10 MB download is impossible: Node (83 MB), the Python interpreter (~120 MB)
and the compiled Next server (221 MB) are the application. Compressed core is
**≈ 130–150 MB**, which is in line with VS Code (~100 MB) and Discord (~80 MB).
Promising less would mean shipping a broken app.

---

## 5. Where the work lands

| Layer | Change |
| --- | --- |
| `scripts/desktop-package.js` | pack-aware assembly: `core/` + `packs/<name>/`, junk pruning |
| `scripts/desktop-installer.js` | stub installer + per-pack archives + manifest of sizes/hashes |
| Shell (Rust) | download manager (resume, SHA-256), progress UI, pack enable/disable, `PYTHONPATH` wiring |
| Onboarding (app) | pack chooser step; Settings › Components |
| Harness (Python) | no logic change; convert missing-import failures into "Install the X pack" errors |
| Docs | install/onboarding copy, pack catalogue |

---

## 6. Phases

| Phase | Work | Outcome | Effort |
| --- | --- | --- | --- |
| **S0** | Junk pruning (§2) | −115 MB, no downloads, no UI | 1 session |
| **S1** | Pack-aware assembly + per-pack archives + manifest | installer can ship packs separately | 1–2 sessions |
| **S2** | Stub installer + core download + progress | small download, working app | 2 sessions |
| **S3** | Onboarding pack chooser + Settings › Components | user chooses | 1–2 sessions |
| **S4** | Friendly "pack missing" errors in the harness | no confusing tracebacks | 1 session |
| **S5** | Offline installer variant | parity for no-network installs | 1 session |

**S0 alone** takes the download from 268 MB to ~245 MB and the install to
~1.30 GB. **S0–S3** lands the real target: ~12 MB download → ~140 MB core fetch →
~540 MB installed, growing only as the user asks for capability.

---

## 7. Risks and how they are handled

| Risk | Handling |
| --- | --- |
| A "lazy" import turns out to be needed at boot | S1 verifies each pack by removing it and booting + running the feature |
| Silent feature loss | Missing pack produces an explicit "Install the X pack" message, never a bare traceback |
| Partial download / corrupt pack | SHA-256 per archive, resumable transfer, staged extraction, atomic enable |
| Users on slow/offline networks | Full offline installer kept as an option |
| Pack sprawl | Fixed catalogue of five; no arbitrary downloads |
| Install footprint grows silently | Settings › Components shows every pack and its size |

## 8. What is explicitly **not** done

- **Tier 3** (a hand-built minimal Python runtime): rejected by the user — too
  risky for the gain.
- Removing pandas/numpy/PIL: core, used everywhere.
- Splitting the Next server per-route: possible, high effort, low payoff.

## 9. Open decisions

1. Default pre-selected pack on onboarding — Documents only, or none?
2. Stub-first download (small download) vs one full installer (simple) — offers
   both, but which is the *default* link on the release page?
3. Should packs auto-verify on app start and offer to repair a broken one?
