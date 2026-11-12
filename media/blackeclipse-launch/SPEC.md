# SPEC — BlackEclipse launch film

GOAL: A viewer who has never seen BlackEclipse understands, in 30 s, that it is
one terminal for 28 world markets and a research agent that explains what moved —
and wants to run it.
OUTPUT: HyperFrames, 1920×1080, 30 fps.
TIME: 30.0 s = 900 frames. Cut points 7.5 / 10.2 / 17.0 / 21.4 / 26.6 s.
LOOK: ground `#050607` throughout; ink `#F4F5F2`; muted `#8B918D`; one accent
`#B4FF42` (live numbers, hairline rules, CTA) and market red `#FF3E3E` (negative
values only). Display face Inter, 700, −0.03em tracking; copy at 56–72 px, the
reveal wordmark 760 px wide; data and labels JetBrains Mono, 18–34 px, uppercase
where the app uses it. Material: the product itself — captured 2× screenshots of
the real interface, plus one rebuilt turnover map with the app's own bubble
language and real JDDS values. Depth: 1 px hairline rules at 10% white, cards at
`#101112` on black, one 0.55-opacity shadow under the end-card lockup; a 6%
vignette on the map; no glow, no bloom, no particles.
OBJECTS: the turnover map (26 translucent bubbles, area by 24 h traded value,
green for up and red for down, each with its ticker, % change and USD value);
the terminal window (real sidebar, top tape, tab content); the S&P 500 card from
Market Discover; the Eclipse Agent screen with its giant ECLIPSE AGENT word;
the eclipse mark and BlackEclipse wordmark.
MOTION: enter `expo.out` 0.55 s; move `power3.inOut` 0.7 s; exit `power2.in`
0.3 s; camera push linear 0.02 scale/s; springs only on the AMD bubble (damping
0.55, one pulse). Copy reveals by clip wipe 0.35 s, never slides while read.
SHOTS:
  0.0–7.5   map: 1.03→1.00 push; AMD ring at 0.5; readout present at 0; copy
            2.4 and 4.6; black iris closes 7.05–7.5. Sound: impact, pop, whoosh.
  7.5–10.2  reveal: hairline rule draws at 0; lockup clip-wipes 0.02–0.64,
            tagline at 0.64; ground holds. Sound: whoosh tail.
  10.2–17.0 discover: real screen wipes up 0.38 s; S&P card isolates at 1.0
            (scale 2.12×, ends 980×460 at x 1040 y 390); left copy at 1.75;
            returns 3.9; 161-reports outline at 4.55; holds to 6.7; hard cut.
            Sound: whoosh, pop.
  16.55–21.4 agent: mounted 0.45 s early under Discover, visible on the cut at
            17.0; copy at 0.95 and 2.87 local (17.5 / 19.42); no camera move.
            Sound: whoosh at 16.92.
  21.4–26.6 payoff: map at 1.6 on AMD, pulls to 1.0 by 4.1; ring and readout at
            0.2; copy at 2.5 and 3.6; bubble-to-black iris 4.78–5.18.
            Sound: riser, impact.
  26.6–30.0 end card: lockup clip-wipes and stamps at 0.08–0.72; claim 0.88;
            command strip 1.1; micro 1.36; holds 2.0 s. Sound: impact at 0.76.
  Preload: both captured screens are mounted full-size at the root at opacity 0
  so the agent shot is decoded before its hard cut.
BANNED: glow/neon/particles; floating glass cards; three-card rows; metric grids;
a title over a dimmed screenshot (copy sits in clear ground or beside an isolated
component); logo docked in a corner; everything fading and sliding up; invented
UI; made-up numbers; a voiceover.
QA: frame 0 map already populated; 2.0 AMD ring + label; 5.5 copy legible over
black; 8.5 lockup correct; 12.0 isolated S&P card sharp with real value; 14.0
161-reports callout real; 18.5 agent copy clear of the giant word; 23.0 AMD
close-up; 27.6 mark and wordmark locked; 29.2 CTA readable and held.
