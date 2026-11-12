---
title: Eclipse Mobile — Scheduling Limitations
status: Proposed
last-verified: 2026-11-12
---

# Scheduling limitations

This document exists to stop the product from promising something a phone cannot
deliver.

## 1. Three different things called "scheduling"

| Kind | What it means | v1 |
| --- | --- | --- |
| **Local best-effort** | The app asks the OS for a background slot; the OS may run it, delay it, or skip it | **Implemented** |
| **App-open catch-up** | On launch/foreground, run schedules that were missed | **Implemented** |
| **Reliable always-on** | A server runs the bot every N minutes regardless of the phone | **Not implemented; needs a hosted worker** |

Only the third can truthfully be called "always-on". It is explicitly outside v1
(D8 in `risks-and-decisions.md`).

## 2. Android

### What is available

| API | Use | Limits |
| --- | --- | --- |
| `WorkManager` `PeriodicWorkRequest` | Periodic scheduling | **Minimum interval 15 minutes**; flex ≥ 5 minutes; Doze/App Standby may delay further; not exact |
| `WorkManager` `OneTimeWorkRequest` | A one-off run / initial delay | Still inexact; subject to Doze and battery saver |
| `AlarmManager.setAndAllowWhileIdle` | A notification near a wall-clock time | Inexact; Doze can defer; exact alarms need a restricted permission and a Play policy justification |
| `AlarmManager.setExactAndAllowWhileIdle` | Exact alarm | Requires `SCHEDULE_EXACT_ALARM`/`USE_EXACT_ALARM`; **not used** |
| Foreground service | Continuous work | Requires an ongoing notification and a qualifying use case; **not used** — it would be a battery/policy abuse for a chat app |

### What actually breaks schedules

- **Doze**: idle devices batch background work into maintenance windows.
- **App Standby buckets**: rarely used apps get fewer opportunities.
- **Battery optimisation / OEM "app killers"** (some Chinese OEMs): can stop
  WorkManager entirely until the app is opened.
- **Force-stop**: the user swiping the app away from Recents (on many OEMs) cancels
  scheduled work until the next launch.
- **Reboot**: WorkManager persists across reboot, but only if the app is not
  force-stopped.
- **Notification permission** (Android 13+): denied permission means no visible
  notification, even if the run happens.

### What the app does

1. Registers one periodic worker per bot with `enabled = true` and a due schedule.
2. Uses the **smallest allowed interval (15 minutes)** as the floor; a 60-second
   interval schedule is refused in the UI with an explanation.
3. Posts a local notification at the intended time where possible, labelled
   "scheduled" — not "ran".
4. On worker execution, runs the bot if network and battery constraints allow; if
   not, records `skipped` and reschedules.
5. On every app open, recomputes due schedules and offers catch-up.

## 3. iOS

### What is available

| API | Use | Limits |
| --- | --- | --- |
| `UNUserNotificationCenter` local notification | Notify at a time | Reliable-ish delivery, but **runs no code** |
| `BGAppRefreshTask` | Short refresh | System decides; typically seconds of runtime; frequency learned from usage; not guaranteed |
| `BGProcessingTask` | Longer work (minutes) | Requires `processing` background mode; runs when the device is idle; the system terminates it if the user starts using the device; not guaranteed |
| `BGContinuedProcessingTask` | User-visible long task started in the foreground | iOS 26+; not a scheduler for unattended bots |
| Background push | Server wakes the app | Requires a server + APNs; rate-limited; discretionary |

Apple's own guidance is explicit: background execution is **opportunistic and
discretionary**, not guaranteed. This is a platform rule, not an implementation
gap.

### What actually breaks schedules

- The user force-quits the app: iOS will not relaunch it for background tasks.
- Low Power Mode and thermal pressure reduce background runtime.
- The system decides based on usage history; a rarely used app runs less.
- There is no "every 5 minutes" background execution.
- A local notification can fire while the app is closed, but it cannot execute the
  bot.

### What the app does

1. Schedules a local notification for the intended time (the user-visible promise
   that can be kept).
2. Submits a `BGAppRefreshTask` request for the next due schedule; on launch, asks
   again for the next one (one pending request per identifier).
3. Uses `BGProcessingTask` only for heavier catch-up when the system grants it.
4. Marks each schedule `notified`, `ran`, `skipped` or `missed`, with the reason.
5. On foreground, runs catch-up according to the bot's policy.

## 4. Behaviour matrix

| Schedule | While app is open | While backgrounded | After force-quit |
| --- | --- | --- | --- |
| `manual` / Run now | Runs immediately | N/A | N/A |
| `interval` < 15 min | Runs on the in-app 30 s tick | Clamped to 15 min (Android); opportunistic (iOS) | No |
| `interval` ≥ 15 min | Runs on time | WorkManager/BG task if granted | Android: maybe (unless force-stopped); iOS: no |
| `daily` / weekdays / weekly / monthly | Runs on time | Notification at time; execution on the next granted slot or app open | Android: maybe; iOS: no |
| `once` | Runs on time | Notification; execution on slot/open | Android: maybe; iOS: no |
| `cron` | Evaluated on the in-app tick | Approximated by the nearest platform mechanism | No |
| `event` / `condition` | Evaluated on the in-app tick | Not evaluated (no background bus) | No |

`event` and `condition` triggers are **not** supported in v1. The desktop engine
has them because a server is always running; a phone is not.

## 5. Misfire and catch-up

| Policy | Behaviour on app open |
| --- | --- |
| `skip` | Missed slots are recorded `missed`; nothing runs |
| `run_once` (default) | One run for the most recent missed slot |
| `catch_up` | Up to `catch_up_max` (default 1, cap 3) missed slots, oldest first, then stop |

Catch-up never runs in parallel with a user-triggered run on the same bot. It is
cancelled by user activity on that thread. It never replays a slot that already has
an execution row (idempotency by `(schedule_id, slot_at)`).

## 6. UX copy (must match reality)

Use these strings verbatim (localized later):

- Schedule editor, under the interval field:
  **"Phones limit background work. This is best effort — iOS may delay it, and
  Android enforces a 15-minute minimum. It will not run while the app is force-quit."**
- Scheduler list, per bot:
  **"Last ran 2 h ago · Next attempt ~09:00 (best effort)"**
- After a missed slot:
  **"Missed while the app was closed. Run it now?"**
- Settings › Schedules:
  **"Always-on bots need a server. Eclipse Mobile runs schedules only when the
  system allows."**

Do not use "runs every hour" without "best effort"; do not show a countdown that
implies a guarantee.

## 7. What a future remote worker would change

A hosted runner (post-v1) would provide:

- a real 24/7 scheduler with leases and exactly-once slot execution;
- remote push (APNs/FCM) for completion and approval requests;
- cross-device continuity;
- the existing Python tool set.

It would **not** be required for the standalone app. The bot/schedule/run contracts
already carry a `target`, so a bot can move from `local_mobile` to `remote_worker`
without changing the UI. Moving a bot must be explicit and must disclose that its
conversations will leave the device.

## 8. Test plan for scheduling

| Test | Method |
| --- | --- |
| 15-minute floor | Create a 60 s interval → UI refuses with the explanation |
| Due calculation | Unit tests for cron/interval/one-time across DST and timezone changes |
| Catch-up policy | Insert missed slots, open the app, assert `skip`/`run_once`/`catch_up` counts |
| Duplicate slot | Reopen twice → one execution row per slot |
| Force-quit (Android) | Swipe away, wait past the slot, reopen → `missed`, not `ran` |
| Force-quit (iOS) | Same; assert no background run is claimed |
| Doze (Android) | `adb shell dumpsys deviceidle force-idle`, wait → notification may be delayed; state remains `best effort` |
| Low Power Mode (iOS) | Enable, background → no false "ran" state |
| Notification denied | Deny permission → schedule still computes; UI explains that alerts are off |

## 9. Non-negotiable statements

1. The app does not keep a process alive to simulate always-on execution.
2. The app does not use an audio session, a fake foreground service or a hidden
   socket to evade background limits.
3. The app never reports a run as completed when the OS prevented it.
4. The app never promises exact-time execution.
5. A missing server is a product limitation, not a bug to hide.
