"""Daily 'game of the day' YouTube Short for 픽셀팬트리 | 스팀 특가·추천 (Pixel Pantry).
Runs every day on GitHub Actions. Picks one well-reviewed Steam game on sale from site/game/data.json
(refreshed daily by build_pages.py), re-checks its live Korean Steam price, renders a ~13s 1080x1920
video with original chiptune audio and writes docs/daily/<date>.mp4/.jpg/.json + latest.json + caption.txt.
"""
import asyncio, json, math, os, subprocess, sys, tempfile, datetime as dt
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(__file__))
import audio as A
import weekly_shorts as WS  # shared drawing helpers (fonts, colours, art loader)

ROOT = WS.ROOT
OUT = os.path.join(ROOT, "docs", "daily")
DATA = os.path.join(ROOT, "site", "game", "data.json")
PAGES = "https://yuitk870-design.github.io/pixelpantry-studio"
CHANNEL = "@pixelpantryhq"
W, H, FPS = WS.W, WS.H, WS.FPS
f, text_c, ease, won = WS.f, WS.text_c, WS.ease, WS.won
WHITE, GRAY, YEL, PINK, BLUE, GREEN = WS.WHITE, WS.GRAY, WS.YEL, WS.PINK, WS.BLUE, WS.GREEN
KST = dt.timezone(dt.timedelta(hours=9))
EVENTS = [
    {"name": "스팀 스크림 페스티벌", "start": "2026-10-27", "end": "2026-11-03"},
    {"name": "스팀 겨울 세일", "start": "2026-12-18", "end": "2027-01-05"},
]


def live_price(app):
    """Fresh Korean Steam price right before rendering (data.json can be up to a day old)."""
    try:
        r = requests.get("https://store.steampowered.com/api/appdetails", params={"appids": app, "cc": "kr", "l": "koreana"},
                         headers=WS.UA, timeout=30)
        d = r.json()[str(app)]
        if not d.get("success"):
            return None
        po = d["data"].get("price_overview") or {}
        if not po:
            return None
        return {"price": po["final"] / 100, "regular": po["initial"] / 100, "off": int(po.get("discount_percent") or 0),
                "name": d["data"].get("name")}
    except Exception as e:
        print("live price failed", app, e)
        return None


def is_low(g):
    return bool(g.get("low_krw")) and g["off"] > 0 and g["price"] <= g["low_krw"] * 1.02


def pick(games, history):
    recent = set(str(h["app"]) for h in history[-30:])
    pool = [g for g in games if g.get("off", 0) >= 25 and (g.get("rating") or 0) >= 70 and g.get("reviews", 0) >= 2000
            and str(g["app"]) not in recent]
    if not pool:
        pool = [g for g in games if g.get("off", 0) >= 20 and str(g["app"]) not in recent]

    def score(g):
        return (1000 if is_low(g) else 0) + g["off"] * 3 + math.log10(max(10, g.get("reviews", 10))) * 25 + (g.get("rating") or 0) * 0.5

    pool.sort(key=score, reverse=True)
    for g in pool[:8]:
        lp = live_price(g["app"])
        if lp and lp["off"] > 0:
            g.update({k: lp[k] for k in ("price", "regular", "off")})
            if g.get("low_krw") and g["low_krw"] > g["price"]:
                g["low_krw"] = g["price"]
            return g
    return None


def next_event(today):
    for e in EVENTS:
        s = dt.date.fromisoformat(e["start"]); en = dt.date.fromisoformat(e["end"])
        if s <= today < en:
            return f"지금 {e['name']} 진행 중!"
        if 0 < (s - today).days <= 30:
            return f"{e['name']}까지 D-{(s - today).days}"
    return None


def verdict_lines(g):
    if is_low(g):
        return ["지금이 역대 최저가 수준!", "사기 좋은 타이밍이에요"]
    if g.get("low_krw"):
        return [f"역대 최저가는 약 {won(g['low_krw'])}", "급하지 않다면 조금 더 기다려도 OK"]
    return [f"{g['off']}% 할인 중", "평가 좋으면 담아둘 만해요"]


# ---------- trailer clip (first ~1.7s of the short, muted) ----------
def trailer_frames(app, seconds, fps):
    """Return a list of 1080x1920 RGB frames from the game's official Steam trailer (no audio), or None."""
    try:
        r = requests.get("https://store.steampowered.com/api/appdetails", params={"appids": app, "filters": "movies"},
                         headers=WS.UA, timeout=30)
        movies = (r.json()[str(app)].get("data") or {}).get("movies") or []
        if not movies:
            return None
        mv = next((m for m in movies if m.get("highlight")), movies[0])
        tmp = tempfile.mkdtemp()
        src = os.path.join(tmp, "seg.mp4")
        if mv.get("hls_h264"):
            base = mv["hls_h264"].split("?")[0].rsplit("/", 1)[0] + "/"
            master = requests.get(mv["hls_h264"], headers=WS.UA, timeout=30).text.splitlines()
            variants = [l for l in master if l.endswith(".m3u8") and "video" in l]
            var = next((v for v in variants if "_1_" in v), variants[0] if variants else None)
            if not var:
                return None
            pl = requests.get(base + var, headers=WS.UA, timeout=30).text.splitlines()
            init = [l.split('"')[1] for l in pl if "EXT-X-MAP" in l]
            segs = [l for l in pl if l.endswith(".m4s")]
            if not init or not segs:
                return None
            k = min(len(segs) - 1, max(1, int(len(segs) * 0.35)))
            data = requests.get(base + init[0], headers=WS.UA, timeout=30).content + requests.get(base + segs[k], headers=WS.UA, timeout=60).content
            open(src, "wb").write(data)
            ss = "0"
        elif mv.get("mp4"):
            u = mv["mp4"].get("max") or mv["mp4"].get("480")
            open(src, "wb").write(requests.get(u, headers=WS.UA, timeout=120).content)
            ss = "8"
        else:
            return None
        raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-ss", ss, "-i", src, "-t", str(seconds), "-an",
                              "-vf", f"fps={fps},scale=1080:-2", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                             capture_output=True, check=True).stdout
        h = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", src],
                           capture_output=True, text=True).stdout.strip().split(",")
        fh = int(round(1080 * int(h[1]) / int(h[0]) / 2) * 2)
        size = 1080 * fh * 3
        frames = [Image.frombytes("RGB", (1080, fh), raw[i:i + size]) for i in range(0, len(raw) - size + 1, size)]
        if len(frames) < fps:
            return None
        out = []
        for fr in frames:
            bgf = fr.resize((int(fr.width * H / fr.height), H), Image.BILINEAR)
            x0 = (bgf.width - W) // 2
            bgf = bgf.crop((x0, 0, x0 + W, H)).filter(ImageFilter.GaussianBlur(28))
            bgf = Image.blend(bgf, Image.new("RGB", (W, H), (10, 10, 15)), 0.55)
            bgf.paste(fr, (0, (H - fh) // 2 - 40))
            out.append(bgf)
        return out
    except Exception as e:
        print("trailer failed", app, e)
        return None


# ---------- Korean narration (free Edge TTS, optional) ----------
VOICE = "ko-KR-SunHiNeural"


def narration_text(g):
    name = g["name"]
    base = f"오늘의 스팀 특가! {name}, {g['off']}% 할인해서 {int(round(g['price'])):,}원!"
    if is_low(g):
        mid = " 역대 최저가예요."
    elif g.get("low_krw"):
        mid = f" 역대 최저가는 {int(round(g['low_krw'])):,}원이라, 급하지 않다면 조금 기다려도 괜찮아요."
    else:
        mid = " 평가 좋은 게임이라 담아둘 만해요."
    return base + mid + " 매일 밤 9시, 구독하고 받아보세요!"


def make_voice(text, out_wav):
    """Edge TTS -> trimmed mono wav. Returns duration in seconds or None (then the short has music only)."""
    try:
        import edge_tts
        mp3 = out_wav + ".mp3"
        asyncio.run(edge_tts.Communicate(text, VOICE, rate="+15%").save(mp3))
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", mp3, "-ac", "1", "-ar", str(A.SR),
                        "-af", "silenceremove=start_periods=1:start_threshold=-45dB,areverse,silenceremove=start_periods=1:start_threshold=-45dB,areverse",
                        out_wav], check=True)
        os.remove(mp3)
        d = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out_wav],
                                 capture_output=True, text=True).stdout.strip())
        return d
    except Exception as e:
        print("voice failed", e)
        return None


def load_wav(path):
    raw = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", path, "-f", "f32le", "-ac", "1", "-ar", str(A.SR), "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.float32).astype(np.float64)


def make_card(g, art):
    cw, ch = 960, 1040
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    card.paste(Image.new("RGBA", (cw, ch), (24, 24, 32, 255)), (0, 0), WS.rr_mask(cw, ch, 48))
    a = art.resize((cw, int(art.height * cw / art.width)), Image.LANCZOS)
    a = a.crop((0, 0, cw, min(a.height, 560)))
    m = Image.new("L", a.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, a.width - 1, a.height + 60], 48, fill=255)
    card.paste(a, (0, 0), m)
    d = ImageDraw.Draw(card)
    fo = f(72, True); s = f"-{g['off']}%"; ow = d.textlength(s, font=fo)
    d.rounded_rectangle([cw - ow - 88, 28, cw - 28, 132], 30, fill=YEL); d.text((cw - ow - 58, 30), s, font=fo, fill=(10, 10, 15))
    y = a.height + 44
    for fnt, ln in WS.wrap_name(g["name"], cw - 100):
        d.text((50, y), ln, font=fnt, fill=WHITE); y += int(fnt.size * 1.3)
    y += 24
    fp = f(130, True); d.text((50, y), won(g["price"]), font=fp, fill=YEL)
    fo2 = f(56); sx = 50 + d.textlength(won(g["price"]), font=fp) + 30; so = won(g["regular"])
    d.text((sx, y + 62), so, font=fo2, fill=GRAY)
    d.line([sx, y + 98, sx + d.textlength(so, font=fo2), y + 98], fill=GRAY, width=5)
    info = []
    if g.get("rating"):
        info.append(f"스팀 평가 {g['rating']}% · 리뷰 {g.get('reviews', 0):,}개")
    if g.get("korean"):
        info.append("한국어 지원")
    if info:
        d.text((50, y + 190), " · ".join(info), font=f(38), fill=(150, 150, 170))
    return card


def stamp(text, color):
    fnt = f(78, True)
    tmp = Image.new("RGBA", (700, 200), (0, 0, 0, 0)); td = ImageDraw.Draw(tmp)
    tw = td.textlength(text, font=fnt)
    td.rounded_rectangle([(700 - tw) / 2 - 40, 30, (700 + tw) / 2 + 40, 170], 34, fill=color + (255,), outline=WHITE + (255,), width=6)
    td.text(((700 - tw) / 2, 44), text, font=fnt, fill=WHITE + (255,))
    return tmp.rotate(-8, resample=Image.BICUBIC, expand=True)


def render(g, art, today, out_mp4, out_cover, no=None):
    bg = WS.build_bg()
    voice_wav = out_mp4 + ".voice.wav"
    vdur = make_voice(narration_text(g), voice_wav)
    clip = trailer_frames(g["app"], 1.8, FPS)
    card = make_card(g, art)
    low = is_low(g)
    hook1 = "오늘의 스팀 특가"
    tag = f"픽셀팬트리 · 오늘의 특가 #{no}" if no else "픽셀팬트리 · 오늘의 특가"
    hook2 = "역대 최저가 🎯" if low else "지금 살까? 기다릴까?"
    hook2 = hook2.replace(" 🎯", "")  # emoji glyphs are not in the font
    st = stamp("역대 최저가!", PINK) if low else stamp(f"-{g['off']}% 할인 중", BLUE)
    vl = verdict_lines(g)
    ev = next_event(today)
    T_HOOK, T_CARD, T_VERD, T_OUT = 1.7, 5.6, 2.4, 3.0
    if vdur:
        T_OUT = max(T_OUT, vdur + 0.3 + 0.8 - (T_HOOK + T_CARD + T_VERD))
    dur = T_HOOK + T_CARD + T_VERD + T_OUT
    n = int(dur * FPS)
    cover = bg.copy().convert("RGBA"); cover.alpha_composite(card, (60, 520))
    text_c(cover, 220, hook1, f(90, True), WHITE); text_c(cover, 340, hook2, f(74, True), YEL)
    cover.alpha_composite(st, (W - st.width - 30, 1440))
    cover.convert("RGB").save(out_cover, quality=92)

    def frame(i):
        t = i / FPS
        img = bg.copy().convert("RGBA")
        t1 = T_HOOK; t2 = t1 + T_CARD; t3 = t2 + T_VERD
        if t < t1 + 0.2 and clip:
            fi = min(len(clip) - 1, i)
            a = 1 - (ease((t - t1 + 0.2) / 0.35) if t > t1 - 0.2 else 0)
            fr = clip[fi].convert("RGBA")
            if a < 1:
                fr = Image.blend(img, fr, max(0.0, a))
            img = fr
            text_c(img, 250, hook1, f(100, True), WHITE, ease(t / 0.15) * a)
            text_c(img, 380, hook2, f(84, True), YEL, ease((t - 0.25) / 0.25) * a)
            ln = WS.fit_text(g["name"], 84, W - 120)
            text_c(img, 1420, ln[1], ln[0], WHITE, ease((t - 0.3) / 0.25) * a)
            text_c(img, 1560, f"-{g['off']}%  {won(g['price'])}", f(96, True), YEL, ease((t - 0.45) / 0.25) * a)
            text_c(img, 1730, tag, f(40, True), (170, 185, 235), a)
        elif t < t1 + 0.2:
            a = ease(t / 0.2) * (1 - (ease((t - t1 + 0.2) / 0.35) if t > t1 - 0.2 else 0))
            text_c(img, 720, hook1, f(110, True), WHITE, a)
            text_c(img, 880, hook2, f(92, True), YEL, ease((t - 0.35) / 0.3) * a)
            text_c(img, 1060, tag, f(44, True), (150, 170, 230), a)
        if t1 <= t < t3 + 0.2:
            text_c(img, 170, hook1, f(66, True), WHITE)
            text_c(img, 260, hook2, f(50, True), YEL)
            p = ease((t - t1) / 0.45)
            fade = 1 - ease((t - t3 + 0.1) / 0.3) if t > t3 - 0.1 else 1
            c = card if fade >= 1 else card.copy()
            if fade < 1:
                c.putalpha(Image.eval(card.getchannel("A"), lambda v: int(v * fade)))
            img.alpha_composite(c, (int(60 + (1 - p) * W), 420))
            if t >= t1 + 1.2 and fade > 0:
                sp = ease((t - t1 - 1.2) / 0.25); s = 1.6 - 0.6 * sp
                sm = st.resize((max(1, int(st.width * s)), max(1, int(st.height * s))), Image.BICUBIC)
                if sp < 1 or fade < 1:
                    sm.putalpha(Image.eval(sm.getchannel("A"), lambda v: int(v * min(sp * 1.5, 1) * fade)))
                img.alpha_composite(sm, (int(W - 60 - sm.width / 2 - 260), int(1480 - sm.height / 2)))
            if t >= t2:
                b = ease((t - t2) / 0.4) * fade
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ImageDraw.Draw(layer).rectangle([0, 1560, W, 1860], fill=(10, 10, 15, int(230 * b)))
                img.alpha_composite(layer)
                text_c(img, 1590, vl[0], f(64, True), YEL, b)
                text_c(img, 1690, vl[1], f(54, True), WHITE, b)
        if t >= t3:
            a = ease((t - t3) / 0.5)
            text_c(img, 560, "매일 밤 9시", f(72, True), WHITE, a)
            text_c(img, 680, "오늘의 스팀 특가", f(100, True), YEL, a)
            b = ease((t - t3 - 0.4) / 0.5)
            if b > 0:
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer); fu = f(58, True)
                btn = "구독하고 매일 받아보기"
                tw = ld.textlength(btn, font=fu); x0 = (W - tw) / 2 - 56
                ld.rounded_rectangle([x0, 890, x0 + tw + 112, 1010], 60, fill=PINK + (int(255 * b),))
                ld.text(((W - tw) / 2, 906), btn, font=fu, fill=WHITE + (int(255 * b),))
                img.alpha_composite(layer)
                text_c(img, 1060, "좋은 세일을 놓치지 않게 하나씩 골라드려요", f(44), GRAY, b)
                if ev:
                    text_c(img, 1220, ev, f(58, True), PINK, b)
                text_c(img, 1420, "픽셀팬트리 · " + CHANNEL, f(46, True), WHITE, b)
        return img.convert("RGB")

    silent = out_mp4 + ".silent.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", silent], stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait()

    seed = int(today.isoformat().replace("-", ""))
    progs = [["C", "G", "Am", "F"], ["Am", "F", "C", "G"], ["F", "C", "G", "Am"], ["C", "Am", "F", "G"]]
    buf = A.music(dur, progs[seed % 4], bpm=118 + seed % 12, seed=seed % 97)
    if vdur:
        buf *= 0.45
        A.place(buf, load_wav(voice_wav), 0.3, 1.0)
        os.remove(voice_wav)
    A.place(buf, A.sfx_pop(), 0.0, 0.5); A.place(buf, A.sfx_pop(), 0.35, 0.35)
    A.place(buf, A.sfx_whoosh(0.4), T_HOOK - 0.1, 0.4)
    A.place(buf, A.sfx_coin(), T_HOOK + 0.5, 0.35)
    A.place(buf, A.sfx_ding(), T_HOOK + 1.25, 0.4)
    A.place(buf, A.sfx_whoosh(0.35), T_HOOK + T_CARD, 0.35)
    A.place(buf, A.sfx_whoosh(0.4), T_HOOK + T_CARD + T_VERD, 0.4)
    A.place(buf, A.sfx_coin(), T_HOOK + T_CARD + T_VERD + 0.5, 0.35)
    wav = out_mp4 + ".wav"; A.finish(buf, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-af", "lowpass=f=8000,loudnorm=I=-16:TP=-1.5:LRA=11", "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    os.remove(silent); os.remove(wav)
    return dur


def texts(g, today, no=None):
    name = g["name"]
    low = is_low(g)
    title = (f"{name} 역대 최저가! 지금 {won(g['price'])} (-{g['off']}%)" if low
             else f"{name} 지금 {won(g['price'])} (-{g['off']}%) 살까? 기다릴까?")
    if len(title) > 90:
        title = title[:88] + "…"
    title += " #Shorts"
    lines = [f"오늘의 스팀 특가 #{no}: {name}" if no else f"오늘의 스팀 특가: {name}", "",
             f"💰 지금 {won(g['price'])} (정가 {won(g['regular'])}, -{g['off']}%)"]
    if g.get("low_krw"):
        lines.append(f"📉 역대 최저가 약 {won(g['low_krw'])}" + (" → 지금이 최저가 수준!" if low else ""))
    if g.get("rating"):
        lines.append(f"👍 스팀 평가 {g['rating']}% (리뷰 {g.get('reviews', 0):,}개)")
    ev = next_event(today)
    if ev:
        lines.append(f"📅 {ev}")
    lines += ["", "매일 밤 9시, 오늘의 스팀 특가를 하나씩 소개해요. 구독해 두면 좋은 세일을 놓치지 않아요 🔔", "",
              "가격은 스팀 한국 스토어 기준이며 바뀔 수 있어요.", "",
              "#Shorts #스팀할인 #스팀세일 #게임할인 #스팀특가"]
    return title, "\n".join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    today = dt.datetime.now(KST).date()
    with open(DATA, encoding="utf-8") as fh:
        games = json.load(fh)
    hist_path = os.path.join(OUT, "history.json")
    history = json.load(open(hist_path, encoding="utf-8")) if os.path.exists(hist_path) else []
    g = pick(games, history)
    if not g:
        print("no game picked"); sys.exit(1)
    art = WS.load_art(g["app"])
    ds = today.isoformat()
    mp4 = os.path.join(OUT, f"{ds}.mp4"); cover = os.path.join(OUT, f"{ds}.jpg")
    prev = [h for h in history if h.get("date") != ds]
    no = next((h.get("no") for h in history if h.get("date") == ds and h.get("no")), None) or \
        max([h.get("no", 0) for h in prev] + [len(prev)]) + 1
    dur = render(g, art, today, mp4, cover, no)
    title, caption = texts(g, today, no)
    info = {"date": ds, "video": f"{PAGES}/daily/{ds}.mp4", "cover": f"{PAGES}/daily/{ds}.jpg", "duration": round(dur, 1),
            "title": title, "caption": caption, "game": g["name"], "app": g["app"], "price": g["price"], "regular": g["regular"],
            "off": g["off"], "low_krw": g.get("low_krw"), "is_low": is_low(g), "no": no}
    for path in (os.path.join(OUT, f"{ds}.json"), os.path.join(OUT, "latest.json")):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "latest_title.txt"), "w", encoding="utf-8") as fh:
        fh.write(title + "\n")
    with open(os.path.join(OUT, "latest_caption.txt"), "w", encoding="utf-8") as fh:
        fh.write(caption + "\n")
    history = [h for h in history if h.get("date") != ds] + [{"date": ds, "app": g["app"], "name": g["name"], "no": no}]
    with open(hist_path, "w", encoding="utf-8") as fh:
        json.dump(history[-90:], fh, ensure_ascii=False, indent=1)
    # keep the repo small: only the last 14 daily videos
    vids = sorted(x for x in os.listdir(OUT) if x.endswith(".mp4"))
    for old in vids[:-14]:
        for ext in (".mp4", ".jpg", ".json"):
            pth = os.path.join(OUT, old[:-4] + ext)
            if os.path.exists(pth):
                os.remove(pth)
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
