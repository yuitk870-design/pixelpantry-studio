"""Original chiptune background music + sound effects, synthesized from scratch (no samples)."""
import numpy as np
from scipy.io import wavfile

SR = 44100


def note_hz(n):  # MIDI note -> Hz
    return 440.0 * 2 ** ((n - 69) / 12)


def env(n, a=0.005, d=0.08, s=0.6, r=0.05):
    t = np.arange(n) / SR
    e = np.ones(n) * s
    ai = int(a * SR); di = int(d * SR); ri = int(r * SR)
    if ai: e[:ai] = np.linspace(0, 1, ai)
    if di: e[ai:ai + di] = np.linspace(1, s, len(e[ai:ai + di]))
    if ri: e[-ri:] *= np.linspace(1, 0, ri)
    return e


def square(f, n, duty=0.25):
    ph = (np.arange(n) * f / SR) % 1.0
    return np.where(ph < duty, 1.0, -1.0)


def tri(f, n):
    ph = (np.arange(n) * f / SR) % 1.0
    return 4 * np.abs(ph - 0.5) - 1


def sine(f, n):
    return np.sin(2 * np.pi * f * np.arange(n) / SR)


def noise(n, seed=0):
    return np.random.default_rng(seed).uniform(-1, 1, n)


def place(buf, sig, t, gain=1.0):
    i = int(t * SR)
    if i >= len(buf): return
    j = min(len(buf), i + len(sig))
    buf[i:j] += sig[: j - i] * gain


# ---------------- music ----------------
CHORDS = {"C": [48, 52, 55], "G": [43, 47, 50], "Am": [45, 48, 52], "F": [41, 45, 48], "Em": [40, 43, 47], "Dm": [38, 41, 45]}


def music(duration, prog, bpm=120, seed=1, lead_patterns=None):
    n = int(duration * SR)
    out = np.zeros(n)
    beat = 60 / bpm
    bar = beat * 4
    eighth = beat / 2
    pats = lead_patterns or [[0, 1, 2, 4, 2, 1, 2, 1], [0, 2, 4, 2, 5, 4, 2, 1], [4, 2, 1, 0, 1, 2, 4, 5], [0, 1, 2, 1, 4, 2, 1, 0]]
    nbars = int(np.ceil(duration / bar))
    for b in range(nbars):
        ch = CHORDS[prog[b % len(prog)]]
        t0 = b * bar
        # bass: root on eighths (octave bounce)
        for k in range(8):
            f = note_hz(ch[0] - 12 + (12 if k % 2 else 0))
            ln = int(eighth * 0.9 * SR)
            place(out, tri(f, ln) * env(ln, d=0.05, s=0.7, r=0.02), t0 + k * eighth, 0.30)
        # lead arpeggio (chord tones up 2 octaves): degrees -> chord tone index with octave
        tones = [ch[0], ch[1], ch[2], ch[0] + 12, ch[1] + 12, ch[2] + 12]
        pat = pats[b % len(pats)]
        for k, deg in enumerate(pat):
            f = note_hz(tones[deg] + 12)
            ln = int(eighth * 0.75 * SR)
            place(out, square(f, ln, 0.25) * env(ln, d=0.06, s=0.45, r=0.03), t0 + k * eighth, 0.11)
        # pad (soft triangle chord) whole bar
        ln = int(bar * SR)
        pad = sum(tri(note_hz(x + 12), ln) for x in ch) / 3
        place(out, pad * env(ln, a=0.2, d=0.3, s=0.5, r=0.3), t0, 0.07)
        # drums
        for k in range(4):
            tb = t0 + k * beat
            if k in (0, 2):  # kick
                ln = int(0.18 * SR)
                tt = np.arange(ln) / SR
                kick = np.sin(2 * np.pi * np.cumsum(60 + 140 * np.exp(-tt * 30)) / SR) * np.exp(-tt * 18)
                place(out, kick, tb, 0.55)
            else:  # snare
                ln = int(0.14 * SR)
                sn = noise(ln, seed + b * 4 + k) * np.exp(-np.arange(ln) / SR * 28)
                place(out, sn, tb, 0.16)
        for k in range(8):  # hats
            ln = int(0.03 * SR)
            hh = noise(ln, 100 + b * 8 + k)
            hh = np.diff(np.concatenate([[0], hh]))  # crude high-pass
            place(out, hh * np.exp(-np.arange(ln) / SR * 120), t0 + k * eighth, 0.05)
    # intro fade-in short, outro fade-out
    fi = int(0.05 * SR); fo = int(1.2 * SR)
    out[:fi] *= np.linspace(0, 1, fi)
    out[-fo:] *= np.linspace(1, 0, fo)
    return out


# ---------------- sound effects ----------------
def sfx_pop():
    ln = int(0.12 * SR)
    f = np.linspace(320, 960, ln)
    ph = np.cumsum(f) / SR
    s = np.where((ph % 1) < 0.5, 1.0, -1.0)
    return s * np.exp(-np.arange(ln) / SR * 22)


def sfx_plink(pitch=1200):
    ln = int(0.14 * SR)
    s = tri(pitch, ln) * 0.7 + tri(pitch * 1.5, ln) * 0.3
    return s * np.exp(-np.arange(ln) / SR * 30)


def sfx_whoosh(dur=0.35):
    ln = int(dur * SR)
    nz = noise(ln, 7)
    # simple low-pass via moving average with sweeping width
    out = np.convolve(nz, np.ones(12) / 12, mode="same")
    e = np.sin(np.linspace(0, np.pi, ln)) ** 2
    return out * e * 1.6


def sfx_ding():
    ln = int(0.7 * SR)
    t = np.arange(ln) / SR
    s = np.sin(2 * np.pi * 1318.5 * t) + 0.5 * np.sin(2 * np.pi * 1975.5 * t) + 0.25 * np.sin(2 * np.pi * 2637 * t)
    return s / 1.75 * np.exp(-t * 6)


def sfx_coin():
    a = square(987.8, int(0.07 * SR), 0.5) * 0.8
    b = square(1318.5, int(0.22 * SR), 0.5) * np.exp(-np.arange(int(0.22 * SR)) / SR * 12) * 0.8
    return np.concatenate([a, b])


def sfx_note(n, dur=0.1):
    ln = int(dur * SR)
    return square(note_hz(n), ln, 0.5) * env(ln, d=0.04, s=0.5, r=0.02)


def finish(buf, path):
    peak = np.max(np.abs(buf)) or 1
    buf = buf / peak * 0.89
    stereo = np.stack([buf, buf], axis=1)
    wavfile.write(path, SR, (stereo * 32767).astype(np.int16))
