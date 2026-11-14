# Contributing to BlackEclipse

BlackEclipse is an open-source, **desktop-first** agentic investment-research
application. The native desktop app is the product; there is no website runtime.

The canonical contributor instructions live next to the application:

- **Development setup, tests, code style, and the release gate:**
  [`Black-Eclipse-site/CONTRIBUTING.md`](Black-Eclipse-site/CONTRIBUTING.md)
- **What to read first:**
  [`Black-Eclipse-site/docs/OVERVIEW.md`](Black-Eclipse-site/docs/OVERVIEW.md)
  then [`Black-Eclipse-site/docs/NAVIGATION.md`](Black-Eclipse-site/docs/NAVIGATION.md)
- **How the project documents changes:**
  [`Black-Eclipse-site/docs/README.md`](Black-Eclipse-site/docs/README.md)
- **Open-source release checklist:**
  [`Black-Eclipse-site/docs/OPEN-SOURCE-READINESS.md`](Black-Eclipse-site/docs/OPEN-SOURCE-READINESS.md)

## Before you open a pull request

1. Read the Code of Conduct in [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).
2. Sign off every commit: `git commit -s` (Developer Certificate of Origin 1.1,
   [`Black-Eclipse-site/DCO`](Black-Eclipse-site/DCO)). A commit without a
   `Signed-off-by:` line is not merged.
3. Run the release gate from `Black-Eclipse-site/`:
   `npm run check:all` (or the individual pieces in the contributing guide).
4. If the change alters architecture, a data shape/contract, or setup steps,
   update the owning doc and append an entry to
   `Black-Eclipse-site/docs/CHANGELOG.md`.

## Security

Do **not** open a public issue for a suspected vulnerability. Use the private
advisory channel described in [`SECURITY.md`](SECURITY.md).

## Licensing

The repository's original code is MIT (see [`LICENSE`](LICENSE)). The isolated
Pine Script engine in `Black-Eclipse-site/pine-engine/` is a separate program
under AGPL-3.0-only; see its
[`NOTICE.md`](Black-Eclipse-site/pine-engine/NOTICE.md). By contributing you
agree that your contribution is licensed under the licence that covers the files
you change, and the DCO records that you have the right to submit it.
