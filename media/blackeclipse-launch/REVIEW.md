# REVIEW — BlackEclipse launch film (30 s)

## What was built

Storyline A, **The map**: a real move you can see (AMD +8.00%, USD 19.97B
traded) and the reason you cannot, answered by the product on two screens — the
Market Discover tape (S&P 500 7,619.38 +1.309%, 28 markets, 56,516 instruments,
161 earnings reports) and the Eclipse Agent ("Ask in plain English." / "Answers
with sources."). It returns to the map for the payoff and ends on the mark and
`npm install && npm run dev`.

Not built, kept in `STORYLINES.md`:

- **B — 28 clocks**: a flight across exchange clocks, each cut landing on a
  different open market; heavier sound design, a world-grid look.
- **C — One question**: a real saved agent question at poster scale, then its
  citations assembling beside it; the agent's giant type as a recurring wall.

## Measured, not guessed

- `check`: 0 lint / 0 runtime / 0 motion / 0 contrast / 0 audio errors.
- 1920×1080, 30 fps, 900 frames, exactly 30.0 s; audio present.
- Rendered loudness −14.3 LUFS integrated, true peak −3.5 dBTP (spot SFX only).
  **The sound was measured, not heard.**
- Every number on screen is from the running app or `jdds.db` at capture:
  AMD $556.43 / +8.00% / USD 19.97B; S&P 500 $7,619.38 / +1.309%; Nasdaq
  25,466.19 / +1.597%; 28 markets; 56,516 assets; 161 reports today.
- Frames inspected in the rendered file: 0, 7.8, 13.6, 17.0, 17.2, 19.2, 21.7,
  24, 26.7, 26.9, 28.3, 29.2. Frame 0 is populated (map, HUD and AMD readout),
  despite the `first_frame_empty` warning below.
- Product screens are real captures, not mockups. The dev-only “N Issues”
  overlay was hidden before the agent capture; the S&P 500 card is rebuilt in
  HTML at 2.1× from the screenshot's own values so it stays sharp when isolated.

## Creative calls

- One accent: lime `#B4FF42` only on live numbers, the AMD focus, the word
  “sources”, and the install command.
- Real UI is the material; the only invented surface is the turnover map, and
  it uses the product's own bubble language and the vault's values (sized by
  24 h traded value).
- Transitions have a cause: the map's iris closes on AMD and becomes the mark;
  the Discover screen lifts its own S&P 500 card; the Agent cuts in on the
  whoosh and reveals copy by clip wipe, never by fade.
- No voiceover (not requested). Music could not be licensed in this run because
  the HyperFrames account is not signed in; the film ships with five placed
  transition/landing effects and is otherwise silent. Signing in to HyperFrames
  adds the catalog bed in one step.

## Weakest shot

**t≈10.2–17.0, Market Discover.** The isolated card is sharp and the numbers are
real, but the screen behind it is a frozen capture, so the beat explains rather
than performs. With more time I would capture a real market-filter click and
let the list repopulate, and hide the app's “10 NEW” notification before capture.
Second weakest: the agent is a still screen carrying three copy swaps; a real
provider-keyed agent run would give it an actual action to show.

## Warnings kept on purpose

- `first_frame_empty`: the checker samples before the nested map composition
  paints. The rendered frame 0 and the snapshot at 0 s both show the populated
  map with the AMD readout, so the thumbnail is not empty. Verified, not ignored.
- `container_overflow` (info): the turnover map intentionally bleeds past its
  frame at the camera's push; `data-layout-ignore` is on the field.
- Typography floor: bubble tickers and the app's own micro-labels are product
  texture at their real UI size; they are not the film's reading copy.

## Files

- Project: `media/blackeclipse-launch/` (HyperFrames, editable)
- Render: `media/blackeclipse-launch/out/blackeclipse-launch.mp4`
- Spec: `SPEC.md` · Storylines: `STORYLINES.md`
