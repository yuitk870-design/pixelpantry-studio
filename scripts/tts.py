"""Small Korean narration helper (free Edge TTS). If anything fails, callers just get None and the short has music only."""
import asyncio, os, subprocess, tempfile
import numpy as np

SR = 44100
VOICE = "ko-KR-SunHiNeural"


def say(text, rate="+15%"):
    """Return (samples as float64 mono at 44.1kHz, duration seconds) or (None, 0)."""
    try:
        import edge_tts
        tmp = tempfile.mkdtemp()
        mp3 = os.path.join(tmp, "v.mp3")
        asyncio.run(edge_tts.Communicate(text, VOICE, rate=rate).save(mp3))
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", mp3, "-ac", "1", "-ar", str(SR),
                              "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,"
                                     "silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                              "-f", "f32le", "-"], capture_output=True, check=True).stdout
        sig = np.frombuffer(raw, dtype=np.float32).astype(np.float64)
        if len(sig) < SR * 0.3:
            return None, 0
        return sig, len(sig) / SR
    except Exception as e:
        print("voice failed", e)
        return None, 0


def won_words(v):
    return f"{int(round(v)):,}원"


def short_name(name):
    """Shorter spoken game name: drop subtitles/editions and trademark signs."""
    import re
    n = re.sub(r"[™®©]", "", name)
    n = re.split(r"\s[-–—]\s|:|&|\(|\[", n)[0].strip()
    words = n.split()
    return " ".join(words[:4]) if words else name
