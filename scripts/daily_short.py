"""Daily 'game of the day' YouTube Short for LootDrop (Pixel Pantry).
Runs every day on GitHub Actions. Picks one well-reviewed Steam game on sale from site/game/data.json
(refreshed daily by build_pages.py), re-checks its live Korean Steam price, renders a ~13s 1080x1920
video with original chiptune audio and writes docs/daily/<date>.mp4/.jpg/.json + latest.json + caption.txt.
"""
import json, math, os, subprocess, sys, datetime as dt
import requests
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import audio as A
import weekly_shorts as WS  # shared drawing helpers (fonts, colours, art loader)

ROOT = WS.ROOT
OUT = os.path.join(ROOT, "docs", "daily")
DATA = os.path.join(ROOT, "site", "game", "data.json")
PAGES = "https://yuitk870-design.github.io/pixelpantry-studio"
SITE = "lootdrop-deals.vercel.app"
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
        return [f"역대 최저가는 약 {won(g['low_krw'])}", "급하지 않다면 목표가 알림 걸어두기"]
    return [f"{g['off']}% 할인 중", "가격 그래프로 비교해보세요"]


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


def render(g, art, today, out_mp4, out_cover):
    bg = WS.build_bg()
    card = make_card(g, art)
    low = is_low(g)
    hook1 = "오늘의 스팀 특가"
    hook2 = "역대 최저가 🎯" if low else "지금 살까? 기다릴까?"
    hook2 = hook2.replace(" 🎯", "")  # emoji glyphs are not in the font
    st = stamp("역대 최저가!", PINK) if low else stamp(f"-{g['off']}% 할인 중", BLUE)
    vl = verdict_lines(g)
    ev = next_event(today)
    T_HOOK, T_CARD, T_VERD, T_OUT = 1.7, 5.6, 2.4, 3.0
    dur = T_HOOK + T_CARD + T_VERD + T_OUT
    n = int(dur * FPS)
    cover = bg.copy().convert("RGBA"); cover.alpha_composite(card, (60, 520))
    text_c(cover, 220, hook1, f(90, True), WHITE); text_c(cover, 340, hook2, f(74, True), YEL)
    cover.alpha_composite(st, (W - st.width - 20, 380))
    cover.convert("RGB").save(out_cover, quality=92)

    def frame(i):
        t = i / FPS
        img = bg.copy().convert("RGBA")
        t1 = T_HOOK; t2 = t1 + T_CARD; t3 = t2 + T_VERD
        if t < t1 + 0.2:
            a = ease(t / 0.2) * (1 - (ease((t - t1 + 0.2) / 0.35) if t > t1 - 0.2 else 0))
            text_c(img, 720, hook1, f(110, True), WHITE, a)
            text_c(img, 880, hook2, f(92, True), YEL, ease((t - 0.35) / 0.3) * a)
            text_c(img, 1060, "LootDrop · by Pixel Pantry", f(44, True), (150, 170, 230), a)
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
            text_c(img, 560, "찜해두고 목표가 알림 받기", f(72, True), WHITE, a)
            text_c(img, 680, "LootDrop에서", f(100, True), YEL, a)
            b = ease((t - t3 - 0.4) / 0.5)
            if b > 0:
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer); fu = f(54, True)
                tw = ld.textlength(SITE, font=fu); x0 = (W - tw) / 2 - 50
                ld.rounded_rectangle([x0, 900, x0 + tw + 100, 1010], 55, fill=PINK + (int(255 * b),))
                ld.text(((W - tw) / 2, 916), SITE, font=fu, fill=WHITE + (int(255 * b),))
                img.alpha_composite(layer)
                text_c(img, 1060, "무료 · 설치 없이 바로 · 원화 가격", f(44), GRAY, b)
                if ev:
                    text_c(img, 1220, ev, f(58, True), PINK, b)
                text_c(img, 1420, "매일 하나씩 · @pixelpantryhq", f(46, True), WHITE, b)
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


def texts(g, today):
    name = g["name"]
    low = is_low(g)
    title = (f"{name} 역대 최저가! 지금 {won(g['price'])} (-{g['off']}%)" if low
             else f"{name} 지금 {won(g['price'])} (-{g['off']}%) 살까? 기다릴까?")
    if len(title) > 90:
        title = title[:88] + "…"
    title += " #Shorts"
    lines = [f"오늘의 스팀 특가: {name}", "",
             f"💰 지금 {won(g['price'])} (정가 {won(g['regular'])}, -{g['off']}%)"]
    if g.get("low_krw"):
        lines.append(f"📉 역대 최저가 약 {won(g['low_krw'])}" + (" → 지금이 최저가 수준!" if low else ""))
    if g.get("rating"):
        lines.append(f"👍 스팀 평가 {g['rating']}% (리뷰 {g.get('reviews', 0):,}개)")
    ev = next_event(today)
    if ev:
        lines.append(f"📅 {ev}")
    lines += ["", "가격 그래프랑 목표가 알림은 LootDrop에서 무료로 👉",
              f"https://{SITE}/game/{g['app']}/", "",
              "가격은 스팀 한국 스토어 기준이며 바뀔 수 있어요.", "",
              "#Shorts #스팀할인 #스팀세일 #게임할인 #LootDrop"]
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
    dur = render(g, art, today, mp4, cover)
    title, caption = texts(g, today)
    info = {"date": ds, "video": f"{PAGES}/daily/{ds}.mp4", "cover": f"{PAGES}/daily/{ds}.jpg", "duration": round(dur, 1),
            "title": title, "caption": caption, "game": g["name"], "app": g["app"], "price": g["price"], "regular": g["regular"],
            "off": g["off"], "low_krw": g.get("low_krw"), "is_low": is_low(g)}
    for path in (os.path.join(OUT, f"{ds}.json"), os.path.join(OUT, "latest.json")):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "latest_title.txt"), "w", encoding="utf-8") as fh:
        fh.write(title + "\n")
    with open(os.path.join(OUT, "latest_caption.txt"), "w", encoding="utf-8") as fh:
        fh.write(caption + "\n")
    history = [h for h in history if h.get("date") != ds] + [{"date": ds, "app": g["app"], "name": g["name"]}]
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
