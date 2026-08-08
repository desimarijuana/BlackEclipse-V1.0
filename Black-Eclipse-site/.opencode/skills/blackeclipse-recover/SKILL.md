---
name: blackeclipse-recover
description: Use when something breaks during BlackEclipse development. Provides the STOP-INSPECT-IDENTIFY-RECOVER-VERIFY protocol, recovery levels, and Git/database safety rules to avoid making a bad situation worse.
---

Follow `skills/RECOVER.md` when an implementation starts failing. The core protocol:

**STOP → INSPECT → IDENTIFY → RECOVER → VERIFY**

Do not blindly keep modifying code. Key rules:

- Identify what changed and when the problem started.
- Compare against the previous working state via Git (`git status`, `git diff`, `git log`).
- Take the **smallest safe recovery path**; revert only the broken change.
- Re-run tests/builds (`npm run test`, `npx tsc --noEmit`, `npm run build`).
- Verify the system returns to a known-good state.

Never:
- Randomly rewrite large portions of the app.
- Delete working code to hide an error.
- Change multiple unrelated systems at once.
- Disable validation or suppress errors to hide the root cause.

**Memory guidance:** If a build fails with `memory allocation ... bytes failed`, free RAM first (close heavy apps); don't fight the compiler on the large `market-overview.tsx`.

Document significant failures in `skills/REMEMBER.md`.
