---
title: Updates & Release Signing
status: Current
last-verified: 2026-11-19
---

# Updates & Release Signing

**Who this is for:** anyone publishing a Black Eclipse release, or changing how
the app detects and applies one.

Eclipse is **self-hosted**: nothing runs on our servers. Most users take the
signed release installer, or the one-command scripts in
[`install.md`](./install.md); contributors run a checkout. "There is an update"
therefore means *a newer signed release exists*, and applying it means *install
that release* (a checkout additionally tags, builds and re-pins). This document
covers the whole path — publishing, notifying, and updating safely — plus the
key handling that keeps a compromised account from turning into a malicious
update.

## The trust chain

```
 offline private key
        │  signs
        ▼
 release/stable.json  ──upload──▶  GitHub Release asset (public, static)
        │                                   │
        │                                   │ anonymous HTTPS GET
        │                                   ▼
        │                          /api/updates (local Next server)
        │                                   │  verifies with
        │                                   ▼
        │                    config/update-signing-key.pub (committed)
        ▼
 black update  ── verifies commit SHA ──▶ git checkout vX.Y.Z ──▶ npm ci ──▶ build
```

Invariants — do not relax these without updating this file:

1. **The manifest is only trusted after a signature verifies.** The public key
   is committed; the private key never is.
2. **Manifest and every URL inside it must be `https:` on an allowlisted host**
   (`config/updates.json` → `allowedHosts`). A signed payload is still remote
   input, so its URLs are re-checked before the UI renders them.
3. **Nothing fetched is executed.** The check is a read. `black update` moves to
   a git tag whose commit SHA equals the signed manifest's `commit`; it never
   runs a downloaded binary.
4. **A failed check is explicit.** The API returns `ok: false`. The banner stays
   quiet; Settings says "couldn't check". Never render "up to date" when the
   answer is unknown.

### The wire format

```json
{
  "schema": 1,
  "payload": "<base64url of the exact JSON bytes>",
  "signature": "<base64url Ed25519 signature over those bytes>"
}
```

The signed payload:

```json
{
  "schema": 1,
  "channel": "stable",
  "version": "0.4.1",
  "publishedAt": "2026-11-09T12:00:00.000Z",
  "commit": "<40-char git SHA of the release tag>",
  "notesUrl": "https://github.com/<org>/<repo>/releases/tag/v0.4.0",
  "downloadUrl": "https://github.com/<org>/<repo>/archive/refs/tags/v0.4.0.zip",
  "minSupported": "0.3.0"
}
```

Signing the exact payload bytes (rather than re-canonicalising JSON) removes all
key-order/whitespace ambiguity: change one byte and verification fails.

## File map

| Concern | File |
|---|---|
| Wire format, Ed25519 verify, semver, allowlist | `scripts/lib/update-verify.js` |
| Server mirror used by the route | `src/lib/updates/core.ts` |
| Shared types (client-safe) | `src/lib/updates/types.ts` |
| Repo slug, manifest URLs, allowed hosts | `config/updates.json` |
| Committed public key / key id `3e5f4f12096f06ac` | `config/update-signing-key.pub` |
| Generate / print fingerprint | `scripts/update-keys.js` (`npm run update:keys`) |
| Sign a release manifest | `scripts/update-sign.js` (`npm run update:sign`) |
| `black update` / `npm run update` | `scripts/update.js`, wired in `bin/black.js` |
| Local status endpoint | `src/app/api/updates/route.ts` |
| In-app notice | `src/components/layout/update-banner.tsx` (mounted in `src/app/layout.tsx`) |
| Title-bar update button + panel | `src/components/layout/update-button.tsx` (mounted by `desktop-tab-bar.tsx`) |
| Update status hook (shared) | `src/lib/updates/use-update-status.ts` |
| Stage an update in-app | `scripts/update-apply.js` (spawned by the shell via `be-update`, or by `src/app/api/updates/apply/route.ts` as a fallback) |
| Native-module lock probe (node_modules safety) | `scripts/lib/update-locks.js` |
| Staged-job reader (spent-job filtering) | `src/lib/updates/job.ts` (tests in `job.test.ts`) |
| Restart into the staged build | `src/lib/desktop/update-bridge.ts` (Tauri event `be-update`) → `main.rs` listener |
| Dismiss/skip/enable prefs | `src/lib/updates/prefs.ts` (`be_update_prefs_v1`) |
| Settings UI | `src/components/screens/general-settings.tsx` → General › Updates |
| Tests | `src/lib/updates/core.test.ts` |

## Release state (current)

Updates are **published**: the repository is
`dumbpabloo/BlackEclipse-V1.0` (public), `config/updates.json` has
`"published": true`, and a signed `stable.json` for **v0.4.15** is attached to
that release. A live check therefore verifies the signature and reports *up to
date* for anyone on 0.4.15; it starts offering a release as soon as a newer
signed manifest exists.

**Signing key id `3e5f4f12096f06ac`.** The previous key (`7a08848038457e37`) was
retired on 2026-11-19 — its private half no longer existed, so nothing could be
signed with it. Rotating leaves a one-time scar, not a permanent one: a build
verifies manifests against the `.pub` it shipped with, so anyone on **0.4.12 or
older** cannot verify a manifest signed by the new key. They keep running, get
no notice, and rejoin the update path by installing 0.4.13 manually once. 0.4.13
and later ship the new key and update normally.

Every release asset gap is visible from outside, so check it after publishing:
`node scripts/update.js --check` prints `HTTP 404` when the **latest** release
carries no `stable.json` (that was the state of v0.4.2 and v0.4.3: the manifest
was only ever on v0.4.1, and `releases/latest/download/stable.json` therefore
404'd for every user). The workflow asks for a **draft** and never signs a
manifest, but it can still end up published (v0.4.13 and v0.4.14 did): confirm
`draft` and which tag `releases/latest` resolves to before and after uploading
the manifest — a published release without one is the 404 state above. The
release step also goes red on `Not Found: update-a-release-asset` because each
platform artifact carries a `packs/manifest.json` and only one can win; that
failure does not withhold the installers or the release.

`published: false` remains the correct setting only for a private pre-launch
repo. While it is false:

- the local server makes **no network request** — it cannot learn anything, and
  users see no notice;
- Settings › General › Updates reports **"Updates are not published yet."**;
- `black update` says the same and changes nothing.

Do **not** flip it to true before a manifest is actually hosted: every check
would fail with "Could not reach the update service", which is worse than an
honest "not published yet".

Because the manifest is a release asset, it must be re-signed and re-uploaded for
**every** release. The current one describes v0.4.15 only — bump, re-sign,
re-upload, then publish the draft, in that order.

> Keeping the **source** private forever means there is nothing for `black update`
> to fetch. The git-based updater assumes users can reach the repo. If you later
> decide to ship packaged builds instead, that needs a separate download+verify
> path, not a config flag.

## One-time maintainer setup

1. **Publish under an organization, not a personal account.** Set
   `repository` in `config/updates.json` to `<org>/<repo>`. If the repo is not
   `black-eclipse/black-eclipse`, update it before the first release.
2. **Generate the keypair** — `npm run update:keys` — then **move
   `.black-eclipse/update-keys/update-signing-key.pem` offline** (encrypted USB,
   hardware token, or an offline machine).
   - Never commit it. `*.pem` is already gitignored; keep it that way.
   - Never put it in GitHub Actions secrets. A CI-held key can be used by anyone
     who compromises the account, which defeats the whole scheme.
3. **Commit `config/update-signing-key.pub`** in a normal reviewed release.
4. Verify the fingerprint matches what you published:
   `node scripts/update-keys.js fingerprint`.

## Publishing a release

```bash
# 1. Bump the version and commit normally
npm version 0.4.0 --no-git-tag-version
git add package.json package-lock.json && git commit -m "release: v0.4.0"

# 2. Tag and push
git tag v0.4.0
git push origin main --tags

# The tag must be on the commit you mean to ship. desktop-release.yml checks
# out the tag, not main: v0.4.2 was tagged on a branch that forked before the
# installer-branding commit, so its published setup still drew NSIS's stock
# disk. desktop:installer now verifies the finished exe's embedded icon and
# fails the release on a mismatch (`npm run installer:verify -- <setup.exe>`).

# 3. Create the GitHub release (source archive is automatic)
gh release create v0.4.0 --title "v0.4.0" --notes-file docs/releases/v0.4.0.md

# 4. Sign the manifest LOCALLY (offline key), then upload it
node scripts/update-sign.js \
  --version 0.4.0 \
  --channel stable \
  --commit "$(git rev-parse v0.4.0^{commit})" \
  --min-supported 0.3.0
gh release upload v0.4.0 release/stable.json --clobber
```

`scripts/update-sign.js` self-verifies against the committed public key before
writing the file: a manifest users cannot verify is worse than no manifest.

No `gh` CLI? The same two steps work in the browser: publish the GitHub release
from the tag, then **Edit release → Attach binaries** and upload
`release/stable.json`. The asset **must** be named exactly `stable.json`, because
the manifest URL is `releases/latest/download/stable.json`.

The app reads `stable.json` from the release's stable asset URL
(`releases/latest/download/stable.json`). For the **beta** channel, publish the
manifest on a `beta` release/tag and use the `beta` URL in
`config/updates.json`; the wire format is identical.

## How users are notified

- `UpdateBanner` waits ~6 s after boot, then calls `GET /api/updates`.
- The local server fetches the public manifest (8 s timeout), verifies it, and
  compares versions. The result is cached in-process for 6 hours; `?refresh=1`
  (used by Settings › Check now) bypasses the cache.
- The banner appears only when the manifest verifies and the version is newer.
  It offers **How to update** (copy `black update`), **What's new**, **Skip this
  version**, and dismiss.
- Settings › General › Updates has the on/off toggle, a manual **Check now**,
  and honest result text (up to date / available / could not check).
- The title-bar download button shows the same answer with a dot, and is the
  surface that can actually stage the release — see
  [In-app updates](#in-app-updates-title-bar-download-button).
- Prefs are local only (`be_update_prefs_v1`). There is no install ID, no
  account, no analytics. Turning the check off means the banner never calls the
  route. The upstream request is an anonymous GET for a public file.

## In-app updates (title-bar download button)

The signed-release check is also exposed as a **download button in the window
chrome**, immediately left of Minimize, with a dot when a newer release exists.
It opens a glass panel that reports the check honestly and can act:

1. **Stage.** *Update now* asks the shell (Tauri event `be-update`,
   `{action:"apply"}`) to spawn `scripts/update-apply.js`; the shell runs it as
   its own child so the app's supervisor cannot kill it. A window without that
   listener falls back to `POST /api/updates/apply`, which spawns the same
   runner from the server. Either way the runner calls the verified updater
   (`scripts/update.js --yes --no-desktop`): signature + allowlisted URLs, clean
   tree, tag == signed commit, `jdds.db` backup, checkout, `npm ci`,
   `npm run build`. It then **stops**.
   - **Windows file locks.** A loaded `.node` binary cannot be replaced, and
     `npm ci` empties `node_modules` before it installs — so installing over a
     running app would destroy the tree and then fail. Before touching anything
     the runner probes `node_modules` by rename (`scripts/lib/update-locks.js`).
     If a native module is held and the runner is not inside the server's own
     process tree (the shell-spawned path), it stops the server it owns, waits
     for the lock to clear, and continues — the panel shows the `stopping` phase.
     Otherwise it fails with the install intact and says to quit Eclipse and run
     `black update`. It also waits 2.5 s before stopping so the window can read
     the job it is about to lose.
2. **Promote.** The runner continues with
   `desktop-refresh.js --no-build`, which stages the new build under
   `releases/stable/<buildId>` and moves the pointer. When the runner stopped the
   app itself it passes the restart through (nothing is left to serve), so the
   window reopens on the new build; otherwise `--no-restart` keeps the running
   window on the build it already loaded and the old release is kept as
   `previous`.
3. **Restart.** The panel offers *Restart Eclipse*, which emits the Tauri event
   `be-update` (`{action:"restart", channel}`). The Rust shell spawns
   `desktop-refresh.js --no-build`, which re-promotes the same build (a no-op)
   and relaunches the window. Closing and reopening Eclipse achieves the same
   thing, so an older shell that predates the `be-update` listener still ends up
   on the new build once it is reopened.

**Why the restart lives in Rust.** Promotion itself is safe while the app runs
(atomic pointer write, previous release kept). The restart is the destructive
part: `desktop-refresh` calls `stopShell` and `stopOwnedServer`, and the latter
is `taskkill /F /T` on the desktop server — i.e. the entire server tree. A
refresh spawned by the server would be killed after its own copy but before it
relaunched anything. The shell is outside that tree, and `stopShell` kills only
the window pid, so a refresh spawned by the shell survives long enough to
finish. Do not "simplify" this by spawning the full restart from the API route;
do not remove `--no-restart` from the in-app promote.

Progress crosses the restart by **file, not IPC**: `scripts/update-apply.js`
writes `.runtime/update-job.json` (phase, message, log tail, target version,
heartbeat) and the UI polls `/api/updates/apply`. A `running` job whose heartbeat
is older than five minutes is reported as failed rather than as a spinner that
never ends (`src/lib/updates/job.ts`). A **finished** job is read against the
installed version: once the app is running a different version, the file is a
spent receipt and is not returned. Without that, a CLI update left the old
failure on screen forever.

Deliberate limits:

- The panel never claims to have applied anything the running window has not
  loaded. A staged job stays "ready" only while the running `version` is still
  the one it started from; after the restart it is treated as spent.
- In-app staging needs the running app to close eventually, because `npm ci`
  cannot replace `next-swc`/`skia` while they are loaded. The shell-spawned
  runner does that itself; the HTTP fallback (an older shell) refuses instead of
  emptying `node_modules`, and the CLI path does the same.
- Only the **stable desktop channel** can stage in-app, because `npm run build`
  always produces `.next` (the Stable channel's build dir). The Dev channel keeps
  using the CLI. Running it from an old shell that lacks the `be-update` listener
  still stages, then tells the user to run `npm run desktop:refresh`.
- Needs a shell rebuild (`npm run desktop:build` + repackage/install) to gain the
  `be-update` listener; without it the staged build still goes live the next
  time the app is opened. The web-side button is served by the pinned build as
  usual.

## Applying an update: `black update`

```bash
black update --check            # read-only
black update                    # prompt, then apply (desktop refreshed first)
black update --yes --restart    # unattended, desktop + browser production
black update --no-desktop       # skip the native-app refresh (web-only machines)
black update --channel beta
```

Order of operations (enforced in `scripts/update.js`):

1. Verify the manifest signature and the allowlisted URLs.
2. Refuse if the working tree is dirty.
3. `git fetch --tags`; require `v<version>` to resolve to the **signed commit**.
   A moved or mismatched tag aborts the update.
4. Back up `jdds.db` through `scripts/db-guard.js backup` (unless
   `--no-backup`, which is discouraged).
5. Check out the tag (detached), confirm `node_modules` can be replaced (stop
   the app this install owns, or wait), `npm ci`, `npm run build`. A failed
   install is retried once after the lock clears.
6. **Desktop first:** re-pin the native app's immutable build and restart its
   own server/reopen the window through `scripts/desktop-refresh.js`. It no-ops
   with an explanation if the desktop is not installed or is a packaged
   (non-bridged) install; `--no-desktop` skips it. The browser production server
   on 3105 is **not** started (or restarted) unless `--restart` is passed.
7. Any failure → check out the previous commit. Reinstall and rebuild only if
   `node_modules` was actually replaced; if the install never ran, the previous
   build is still intact and re-running `npm ci` could only do damage. The DB
   backup is left untouched and reported.

**Desktop-first is a product rule, not a preference.** The native window is the
primary front door; the browser build is secondary. An update that leaves the
desktop on the previous build while the website is current is a failed update.
The pinned copy makes this safe: the window can be restarted and re-pinned
without any web server, and the reverse (a web only update) is opt-in.

Updates never auto-apply from the browser. That is deliberate: the update path
touches the user's local database and runs new code, so the person whose data it
is gets the final yes.

`black update` checks out the release tag in **detached HEAD** state. That is the
point: the running code is exactly the signed commit. To go back to developing
on a branch, run `git switch main` (and `git pull`).

## Compromise and rotation

| Event | Response |
|---|---|
| Private key leaked | Generate a new keypair, commit the new `.pub`, publish a release, revoke the old key id in the release notes and here. Users on the old release still verify old manifests until they update — say so plainly. |
| Signing machine stolen | Same as leaked. The passphrase/offline storage is the only barrier; assume the key is gone. |
| GitHub account compromised | Users are still safe if the private key is offline: the attacker cannot sign a manifest. Rotate account credentials, audit releases, keep the key offline. |
| Tag moved / commit mismatch | `black update` refuses automatically. Investigate; do not add a bypass. |
| Lost private key | Users keep working; no new updates can be signed. Rotate by publishing a release from a new key (users must apply that one manually), then resume. |

## What never to do

- Never commit, paste, or CI-store the private key.
- Never distribute a zip of your working folder. Release from a clean clone or
  `git archive`, or a stray `.black-eclipse/` (private key, chats, cache) ships
  with the product. The doc above assumes releases come from git tags.
- Never host the manifest on a personal server or home network. GitHub Releases
  (or any static CDN) removes that exposure.
- Never let the client trust a URL from the manifest without the allowlist.
- Never auto-apply an update without a signature check and a DB backup.
- Never put personal contact details in `README`, `LICENSE`, `package.json`
  `author`, commit emails, or DNS WHOIS. Publish as the org; use
  `@users.noreply.github.com` and GitHub Security Advisories for reports.
- Never mark a failed check as "up to date".

## Tests & troubleshooting

```bash
npx vitest run src/lib/updates/core.test.ts   # signature, semver, allowlist
node scripts/update.js --check                # live check
node scripts/update-sign.js ... --out .black-eclipse/test.json --force
```

- **"Could not check for updates"** — the manifest URL 404s (no release yet), or
  the host is offline. Check `config/updates.json` and that `stable.json` is
  attached to the latest release.
- **"signature is invalid"** — the manifest was signed with a different private
  key than the committed `.pub`, or the bytes were edited after signing.
- **"tag points at … but the signed manifest names …"** — the tag moved, or you
  signed the wrong commit. Re-tag from the signed commit and re-sign.
