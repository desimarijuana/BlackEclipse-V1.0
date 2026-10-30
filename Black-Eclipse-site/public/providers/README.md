# Provider brand marks

Vendored SVG marks used by `src/components/providers/provider-logo.tsx` to
identify the configured model provider in the composer, provider picker and
Manage-models dialog.

Sources: [Iconify `logos`](https://icon-sets.iconify.design/logos/) and
[LobeHub icons](https://github.com/lobehub/lobe-icons) (static SVG set). They are
used solely for provider identification; all trademarks remain the property of
their respective owners.

The UI renders them as a `currentColor` mask (silhouette), so edits must keep the
alpha shape intact. No network request is made for these assets.
