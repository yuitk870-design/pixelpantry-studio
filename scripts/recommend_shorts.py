"""Weekly 'recommended games' Short for 픽셀팬트리 | 스팀 특가·추천 (Pixel Pantry).
Runs every Friday on GitHub Actions (Saturday morning in Korea). Picks 3 well-reviewed Steam games that are on sale
from site/game/data.json, using a theme that rotates every week, re-checks live Korean prices, renders a
1080x1920 video with original chiptune audio and writes docs/recommend/<date>.mp4 + latest.json + title/caption.
"""
import json, math, os, subprocess, sys, datetime as dt
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(__file__))
import audio as A
import weekly_shorts as WS
import daily_short as DS

ROOT = WS.ROOT
OUT = os.path.join(ROOT, "docs", "recommend")
DATA = os.path.join(ROOT, "site", "game", "data.json")
PAGES = "https://yuitk870-design.github.io/pixelpantry-studio"
W, H, FPS = WS.W, WS.H, WS.FPS
f, text_c, ease, won = WS.f, WS.text_c, WS.ease, WS.won
WHITE, GRAY, YEL, PINK, BLUE, GREEN = WS.WHITE, WS.GRAY, WS.YEL, WS.PINK, WS.BLUE, WS.GREEN
KST = dt.timezone(dt.timedelta(hours=9))

THEMES = [
    {"key": "hidden", "title": "숨은 명작", "sub": "평가는 압도적인데 의외로 덜 알려진 게임",
     "ok": lambda g: (g.get("rating") or 0) >= 92 and 1000 <= g.get("reviews", 0) <= 25000 and g["price"] <= 20000},
    {"key": "indie", "title": "인디 명작", "sub": "작지만 평가 좋은 인디 게임",
     "ok": lambda g: "인디" in g.get("genres", []) and (g.get("rating") or 0) >= 90},
    {"key": "rpg", "title": "빠져드는 RPG·어드벤처", "sub": "스토리와 모험이 좋은 게임",
     "ok": lambda g: any(x in g.get("genres", []) for x in ("RPG", "어드벤처")) and (g.get("rating") or 0) >= 88},
    {"key": "low", "title": "역대 최저가 대작", "sub": "유명한 게임이 지금 가장 싸요",
     "ok": lambda g: DS.is_low(g) and g.get("reviews", 0) >= 20000},
]


def theme_for(today):
    return THEMES[today.isocalendar()[1] % len(THEMES)]


def pick(games, theme, recent):
    def score(g):
        return (g.get("rating") or 0) * 2 + math.log10(max(10, g.get("reviews", 10))) * 10 + g.get("off", 0) * 0.5

    for relax in (False, True):
        pool = [g for g in games if g.get("off", 0) >= 20 and str(g["app"]) not in recent
                and (g.get("rating") or 0) >= 80 and (relax or theme["ok"](g))]
        pool.sort(key=score, reverse=True)
        picked = []
        for g in pool[:12]:
            lp = DS.live_price(g["app"])
            if lp and lp["off"] > 0:
                g = dict(g); g.update({k: lp[k] for k in ("price", "regular", "off")})
                picked.append(g)
            if len(picked) == 3:
                return picked, relax
    return picked, True


def why(g):
    parts = []
    if g.get("rating"):
        parts.append(f"스팀 평가 {g['rating']}%")
    if g.get("reviews"):
        parts.append(f"리뷰 {g['reviews']:,}개")
    if g.get("korean"):
        parts.append("한국어 지원")
    return " · ".join(parts)


def make_card(g, art, rank):
    cw, ch = 960, 1120
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    card.paste(Image.new("RGBA", (cw, ch), (24, 24, 32, 255)), (0, 0), WS.rr_mask(cw, ch, 48))
    a = art.resize((cw, int(art.height * cw / art.width)), Image.LANCZOS)
    a = a.crop((0, 0, cw, min(a.height, 540)))
    m = Image.new("L", a.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, a.width - 1, a.height + 60], 48, fill=255)
    card.paste(a, (0, 0), m)
    d = ImageDraw.Draw(card)
    d.rounded_rectangle([28, 28, 168, 128], 30, fill=BLUE); fr = f(64, True)
    s = f"#{rank}"; d.text((98 - d.textlength(s, font=fr) / 2, 30), s, font=fr, fill=WHITE)
    fo = f(72, True); s = f"-{g['off']}%"; ow = d.textlength(s, font=fo)
    d.rounded_rectangle([cw - ow - 88, 28, cw - 28, 132], 30, fill=YEL); d.text((cw - ow - 58, 30), s, font=fo, fill=(10, 10, 15))
    y = a.height + 40
    for fnt, ln in WS.wrap_name(g["name"], cw - 100):
        d.text((50, y), ln, font=fnt, fill=WHITE); y += int(fnt.size * 1.3)
    y += 16
    genres = " · ".join(g.get("genres", [])[:3])
    if genres:
        d.text((50, y), genres, font=f(40), fill=(150, 170, 230)); y += 64
    fp = f(120, True); d.text((50, y), won(g["price"]), font=fp, fill=YEL)
    fo2 = f(54); sx = 50 + d.textlength(won(g["price"]), font=fp) + 30; so = won(g["regular"])
    d.text((sx, y + 56), so, font=fo2, fill=GRAY)
    d.line([sx, y + 90, sx + d.textlength(so, font=fo2), y + 90], fill=GRAY, width=5)
    d.text((50, y + 170), why(g), font=f(40, True), fill=GREEN)
    return card


def render(games, arts, theme, today, out_mp4, out_cover):
    bg = WS.build_bg()
    cards = [make_card(g, a, i + 1) for i, (g, a) in enumerate(zip(games, arts))]
    T_INTRO, T_CARD, T_OUT = 2.4, 3.0, 2.8
    dur = T_INTRO + T_CARD * len(cards) + T_OUT
    n = int(dur * FPS)
    cover = bg.copy().convert("RGBA"); cover.alpha_composite(cards[0], (60, 500))
    text_c(cover, 200, "이번 주 추천 게임", f(84, True), WHITE); text_c(cover, 310, theme["title"], f(70, True), YEL)
    cover.convert("RGB").save(out_cover, quality=92)

    def frame(i):
        t = i / FPS
        img = bg.copy().convert("RGBA")
        if t < T_INTRO + 0.2:
            a = ease(t / 0.2) * (1 - (ease((t - T_INTRO + 0.2) / 0.35) if t > T_INTRO - 0.2 else 0))
            text_c(img, 660, "이번 주 추천 게임", f(100, True), WHITE, a)
            text_c(img, 820, theme["title"], f(110, True), YEL, ease((t - 0.3) / 0.3) * a)
            text_c(img, 990, theme["sub"], f(48), GRAY, ease((t - 0.5) / 0.3) * a)
            text_c(img, 1100, "지금 할인 중인 게임만 골랐어요", f(44, True), (150, 170, 230), ease((t - 0.6) / 0.3) * a)
        t0 = T_INTRO
        if t0 <= t < t0 + T_CARD * len(cards) + 0.4:
            k = min(len(cards) - 1, int((t - t0) // T_CARD)); lt = t - t0 - k * T_CARD
            text_c(img, 150, "이번 주 추천 · " + theme["title"], f(60, True), WHITE)
            text_c(img, 240, "픽셀팬트리 · 매주 토요일", f(36, True), (150, 170, 230))
            p = ease(lt / 0.45)
            if k > 0 and lt < 0.45:
                img.alpha_composite(cards[k - 1], (int(60 - p * W), 440))
            last_fade = (t - (t0 + T_CARD * len(cards))) if k == len(cards) - 1 else -1
            if last_fade < 0:
                img.alpha_composite(cards[k], (int(60 + (1 - p) * W), 440))
            else:
                c = cards[k].copy(); c.putalpha(Image.eval(c.getchannel("A"), lambda v: int(v * max(0, 1 - last_fade / 0.4))))
                img.alpha_composite(c, (60, 440))
            for j in range(len(cards)):
                cx = W // 2 + int((j - (len(cards) - 1) / 2) * 36)
                ImageDraw.Draw(img).ellipse([cx - 8, 1660, cx + 8, 1676], fill=BLUE if j == k else (70, 70, 90))
        to = t0 + T_CARD * len(cards)
        if t >= to:
            a = ease((t - to) / 0.5)
            text_c(img, 600, "매주 토요일 추천 게임", f(76, True), WHITE, a)
            text_c(img, 710, "매일 밤 9시 특가", f(100, True), YEL, a)
            b = ease((t - to - 0.4) / 0.5)
            if b > 0:
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer); fu = f(58, True)
                btn = "구독하고 다음 추천 받기"
                tw = ld.textlength(btn, font=fu); x0 = (W - tw) / 2 - 56
                ld.rounded_rectangle([x0, 920, x0 + tw + 112, 1040], 60, fill=PINK + (int(255 * b),))
                ld.text(((W - tw) / 2, 936), btn, font=fu, fill=WHITE + (int(255 * b),))
                img.alpha_composite(layer)
                text_c(img, 1090, "스팀 평가와 할인 정보를 바탕으로 골랐어요", f(42), GRAY, b)
                text_c(img, 1400, "픽셀팬트리 · @pixelpantryhq", f(46, True), WHITE, b)
        return img.convert("RGB")

    silent = out_mp4 + ".silent.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", silent], stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait()

    seed = int(today.isoformat().replace("-", ""))
    buf = A.music(dur, ["F", "C", "G", "Am"], bpm=112 + seed % 10, seed=seed % 89)
    A.place(buf, A.sfx_pop(), 0.0, 0.5); A.place(buf, A.sfx_pop(), 0.3, 0.35)
    for k in range(len(cards)):
        tk = T_INTRO + k * T_CARD
        A.place(buf, A.sfx_whoosh(0.35), tk, 0.4); A.place(buf, A.sfx_coin(), tk + 0.45, 0.3)
    A.place(buf, A.sfx_ding(), T_INTRO + T_CARD * len(cards) + 0.4, 0.4)
    wav = out_mp4 + ".wav"; A.finish(buf, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-af", "lowpass=f=8000,loudnorm=I=-16:TP=-1.5:LRA=11", "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    os.remove(silent); os.remove(wav)
    return dur


def texts(games, theme):
    names = ", ".join(g["name"] for g in games[:2])
    title = f"이번 주 추천 게임: {theme['title']} — {names}"
    if len(title) > 90:
        title = title[:88] + "…"
    title += " #Shorts"
    lines = [f"이번 주 추천 게임 · {theme['title']} 🎮", theme["sub"], ""]
    for i, g in enumerate(games, 1):
        lines.append(f"{i}. {g['name']} — {won(g['price'])} (-{g['off']}%) · {why(g)}")
    lines += ["", "스팀 평가와 리뷰 수, 할인 정보를 바탕으로 고른 목록이에요.",
              "매주 토요일 추천 게임, 매일 밤 9시 오늘의 스팀 특가를 올려요. 구독해 두면 좋은 세일을 놓치지 않아요 🔔", "",
              "가격은 스팀 한국 스토어 기준이며 바뀔 수 있어요.", "",
              "#Shorts #스팀게임추천 #스팀할인 #스팀세일 #게임추천 #스팀특가"]
    return title, "\n".join(lines)


def main():
    os.makedirs(OUT, exist_ok=True)
    today = dt.datetime.now(KST).date()
    with open(DATA, encoding="utf-8") as fh:
        games = json.load(fh)
    hist_path = os.path.join(OUT, "history.json")
    history = json.load(open(hist_path, encoding="utf-8")) if os.path.exists(hist_path) else []
    recent = set(str(a) for h in history[-8:] for a in h.get("apps", []))
    theme = theme_for(today)
    picked, relaxed = pick(games, theme, recent)
    if len(picked) < 3:
        print("not enough games", len(picked)); sys.exit(1)
    if relaxed:
        theme = {"key": "best", "title": "평가 좋은 할인 게임", "sub": "스팀 평가가 좋은 게임만 모았어요"}
    arts = [WS.load_art(g["app"]) for g in picked]
    ds = today.isoformat()
    mp4 = os.path.join(OUT, f"{ds}.mp4"); cover = os.path.join(OUT, f"{ds}.jpg")
    dur = render(picked, arts, theme, today, mp4, cover)
    title, caption = texts(picked, theme)
    info = {"date": ds, "video": f"recommend/{ds}.mp4", "video_url": f"{PAGES}/recommend/{ds}.mp4", "cover": f"recommend/{ds}.jpg",
            "duration": round(dur, 1), "theme": theme["title"], "title": title, "caption": caption,
            "games": [{"app": g["app"], "name": g["name"], "price": g["price"], "regular": g["regular"], "off": g["off"],
                       "rating": g.get("rating"), "reviews": g.get("reviews")} for g in picked]}
    for path in (os.path.join(OUT, f"{ds}.json"), os.path.join(OUT, "latest.json")):
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(info, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "latest_title.txt"), "w", encoding="utf-8") as fh:
        fh.write(title + "\n")
    with open(os.path.join(OUT, "latest_caption.txt"), "w", encoding="utf-8") as fh:
        fh.write(caption + "\n")
    history = [h for h in history if h.get("date") != ds] + [{"date": ds, "theme": theme["title"], "apps": [g["app"] for g in picked]}]
    with open(hist_path, "w", encoding="utf-8") as fh:
        json.dump(history[-30:], fh, ensure_ascii=False, indent=1)
    vids = sorted(x for x in os.listdir(OUT) if x.endswith(".mp4"))
    for old in vids[:-6]:
        for ext in (".mp4", ".jpg", ".json"):
            pth = os.path.join(OUT, old[:-4] + ext)
            if os.path.exists(pth):
                os.remove(pth)
    print(json.dumps(info, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
