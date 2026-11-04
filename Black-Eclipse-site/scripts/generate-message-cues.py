#!/usr/bin/env python3
"""Generate the AI-result message cues.

The message cue is shared across voice packs (it announces an Eclipse reply, not
an interaction tick), so it lives in `public/sounds/message/<variant>.wav` and is
selected in Settings > Sound > Notifications & alarms.

Four deliberately different voices are generated with pure math (no deps):
  chime   - soft ascending perfect fifth, the recommended default
  marimba - warm wooden mallet two-note
  glass   - gentle bell with inharmonic partials
  blip    - very short, low two-tone blip

Run from the app root:  python scripts/generate-message-cues.py
"""

from __future__ import annotations

import math
import os
import struct
import wave

SR = 44_100
OUT_DIR = os.path.join("public", "sounds", "message")


def env(t: float, attack: float, tau: float) -> float:
    """Click-free attack + exponential decay."""
    a = min(1.0, t / attack) if attack > 0 else 1.0
    return a * math.exp(-t / tau)


def note(t: float, freq: float, tau: float, attack: float, gain: float) -> float:
    """Fundamental plus two quiet harmonics — warm, never a raw sine beep."""
    e = env(t, attack, tau) * gain
    if e <= 0:
        return 0.0
    return e * (
        math.sin(2 * math.pi * freq * t)
        + 0.22 * math.sin(2 * math.pi * freq * 2 * t)
        + 0.08 * math.sin(2 * math.pi * freq * 3 * t)
    )


def write_wav(name: str, samples: list[float]) -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, f"{name}.wav")
    peak = max(1e-9, max(abs(s) for s in samples))
    # Normalize to a calm -6 dBFS so the cue sits under the mix.
    scale = (10 ** (-6 / 20)) * 32767 / peak
    frames = b"".join(struct.pack("<h", int(max(-32767, min(32767, s * scale)))) for s in samples)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(frames)
    print(f"{path}: {len(samples) / SR:.3f}s, {os.path.getsize(path)} bytes")


def chime() -> list[float]:
    """Soft E5 -> B5 perfect fifth. The recommended default."""
    dur = 0.46
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        # Second note enters after 105ms, so it reads as one gesture.
        s = note(t, 659.25, 0.16, 0.008, 0.9)
        if t >= 0.105:
            s += note(t - 0.105, 987.77, 0.14, 0.007, 0.65)
        # Tiny low body so phone/laptop speakers still convey the cue.
        if t < 0.09:
            s += 0.10 * math.sin(2 * math.pi * 196 * t) * env(t, 0.004, 0.035)
        out.append(s)
    return out


def marimba() -> list[float]:
    """Warm wooden A4 -> E5, with a soft mallet transient."""
    dur = 0.42
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        s = note(t, 440.0, 0.13, 0.006, 0.85)
        if t >= 0.115:
            s += note(t - 0.115, 659.25, 0.11, 0.005, 0.6)
        # Mallet noise: very short, low-passed by the decay.
        if t < 0.012:
            s += 0.08 * math.sin(2 * math.pi * 2600 * t) * env(t, 0.001, 0.004)
        out.append(s)
    return out


def glass() -> list[float]:
    """Gentle E6 -> B6 bell with a small inharmonic shimmer."""
    dur = 0.58
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        s = note(t, 1318.5, 0.22, 0.006, 0.55)
        if t >= 0.09:
            s += note(t - 0.09, 1975.5, 0.19, 0.005, 0.42)
        # Inharmonic partial gives glass its character, kept quiet.
        s += 0.05 * math.sin(2 * math.pi * 2730 * t) * env(t, 0.004, 0.10)
        out.append(s)
    return out


def blip() -> list[float]:
    """Very short, low C5 -> G5 — the least intrusive option."""
    dur = 0.27
    n = int(dur * SR)
    out = []
    for i in range(n):
        t = i / SR
        s = note(t, 523.25, 0.09, 0.004, 0.8)
        if t >= 0.075:
            s += note(t - 0.075, 783.99, 0.08, 0.004, 0.55)
        out.append(s)
    return out


def main() -> None:
    write_wav("chime", chime())
    write_wav("marimba", marimba())
    write_wav("glass", glass())
    write_wav("blip", blip())


if __name__ == "__main__":
    main()
