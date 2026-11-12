# BlackEclipse — Harness Report (12 Nov 2026)

Branded, technical explainer for the Round 5 core-integrity harness work,
plus the ready-to-post LinkedIn copy. Three pages: shipped changes, a run
lifecycle diagram with failure modes, and benchmark/SLO/category charts.

## Files

| File | What it is |
|---|---|
| `report.html` | Three-page A4 source of the report (screen preview + print). |
| `report.pdf` | Rendered three-page PDF, A4, print-ready. |
| `card.html` | 1080 × 1350 social card source. |
| `card.png` | Rendered card for the LinkedIn post. |
| `linkedin-post.md` | Post copy, including the proof points. |
| `assets/` | Brand wordmark and the two local fonts (Inter, JetBrains Mono). |

## Brand tokens used

- Ground `#050607`, cards `#101112`
- Ink `#F4F5F2`, muted `#8B918D`, dim `#636966`
- Accent `#B4FF42`, negative `#FF3E3E`
- Hairlines `rgba(255,255,255,0.10)`
- Inter for display/body, JetBrains Mono for data and labels

## Evidence for every number

- `Black-Eclipse-site/docs/harness/slo-report.json` — 40 probe runs, 39
  completed, 1 failed, 0 orphaned; p95 1,885 ms; $0.0007/task; 5/5 SLOs healthy.
- `Black-Eclipse-site/docs/harness/conformance.json` — 12 conformance cases
  (6 fault, 1 golden trace, 5 contract).
- `Black-Eclipse-site/docs/harness/scorecard.{md,json}` — measured/partial
  dimensions and their evidence paths.
- `Black-Eclipse-site/docs/CHANGELOG.md` — the shipped C2/C4/C6/C7/C8 entries.

## Regenerate

```powershell
# PDF and card (Edge is installed on Windows)
& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu --no-sandbox `
  --print-to-pdf="$PWD\media\blackeclipse-harness-report\report.pdf" --no-pdf-header-footer `
  "file:///$((Resolve-Path 'media\blackeclipse-harness-report\report.html').Path.Replace('\','/'))"

& "C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe" --headless --disable-gpu --no-sandbox `
  --window-size=1080,1350 --force-device-scale-factor=1 --hide-scrollbars `
  --screenshot="$PWD\media\blackeclipse-harness-report\card.png" `
  "file:///$((Resolve-Path 'media\blackeclipse-harness-report\card.html').Path.Replace('\','/'))"
```

## Honesty note

The report deliberately keeps the open items visible: loop correctness and
context economics are still `partial` on the scorecard, external benchmark
adapters (C8) and packaging/ACP (C9) are open, and the 40-run probe is a release
probe, not a public benchmark.
