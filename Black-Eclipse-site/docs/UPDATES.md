---
title: Updates & Release Signing
status: Current
last-verified: 2026-11-09
---

# Updates & Release Signing

**Who this is for:** anyone publishing a Black Eclipse release, or changing how
the app detects and applies one.

Eclipse is **self-hosted**: users clone the repo and run it on their own machine.
"There is an update" therefore means *a newer signed release exists*, and
applying it means *check out that release and rebuild*. This document covers the
whole path — publishing, notifying, and updating safely — plus the key handling
that keeps a compromised account from turning into a malicious update.

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
  "version": "0.4.0",
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
| Committed public key / key id `7a08848038457e37` | `config/update-signing-key.pub` |
| Generate / print fingerprint | `scripts/update-keys.js` (`npm run update:keys`) |
| Sign a release manifest | `scripts/update-sign.js` (`npm run update:sign`) |
| `black update` / `npm run update` | `scripts/update.js`, wired in `bin/black.js` |
| Local status endpoint | `src/app/api/updates/route.ts` |
| In-app notice | `src/components/layout/update-banner.tsx` (mounted in `src/app/layout.tsx`) |
| Dismiss/skip/enable prefs | `src/lib/updates/prefs.ts` (`be_update_prefs_v1`) |
| Settings UI | `src/components/screens/general-settings.tsx` → General › Updates |
| Tests | `src/lib/updates/core.test.ts` |

## Private development (current state)

The repository is **private during development**, so there is no public
`stable.json` yet — a release asset on a private repo requires authentication and
would 404 for every anonymous check.

`config/updates.json` therefore ships with:

```json
"published": false
```

While it is false:

- the local server makes **no network request** — it cannot learn anything, and
  users see no banner;
- Settings › General › Updates reports **"Updates are not published yet."**;
- `black update` says the same and changes nothing.

This is the honest pre-launch state, not a silent failure. When you are ready to
launch:

1. Make the release repo public (or point `repository` at a public release repo).
2. Change `"published"` to `true` in `config/updates.json`.
3. Publish the first signed release (below).

Only that one flag changes in code. Do **not** flip it while the repo is still
private: the check would just fail with "Could not reach the update service".

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
- Prefs are local only (`be_update_prefs_v1`). There is no install ID, no
  account, no analytics. Turning the check off means the banner never calls the
  route. The upstream request is an anonymous GET for a public file.

## Applying an update: `black update`

```bash
black update --check            # read-only
black update                    # prompt, then apply
black update --yes --restart    # unattended
black update --channel beta
```

Order of operations (enforced in `scripts/update.js`):

1. Verify the manifest signature and the allowlisted URLs.
2. Refuse if the working tree is dirty.
3. `git fetch --tags`; require `v<version>` to resolve to the **signed commit**.
   A moved or mismatched tag aborts the update.
4. Back up `jdds.db` through `scripts/db-guard.js backup` (unless
   `--no-backup`, which is discouraged).
5. Check out the tag (detached), `npm ci`, `npm run build`.
6. Any failure → check out the previous commit, reinstall, rebuild. The DB
   backup is left untouched and reported.

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
