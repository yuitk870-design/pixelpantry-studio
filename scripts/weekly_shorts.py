"""Weekly 'Steam deals TOP 5' shorts for LootDrop (Pixel Pantry).
Runs on GitHub Actions: fetches real Steam KR deals, downloads game art,
renders a 1080x1920 video with original chiptune audio, writes to docs/weekly/.
"""
import io, json, math, os, subprocess, sys, datetime as dt
import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
import audio as A

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "weekly")
W, H, FPS = 1080, 1920, 30
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_K = "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc"
if not os.path.exists(FONT_K): FONT_K = FONT_B
f = lambda s, k=False: ImageFont.truetype(FONT_K if k else FONT_B, s)
BG = (10, 10, 15); PINK = (255, 45, 135); BLUE = (41, 121, 255); YEL = (255, 214, 10)
WHITE = (255, 255, 255); GRAY = (160, 160, 180); GREEN = (34, 197, 94)
UA = {"User-Agent": "Mozilla/5.0 (PixelPantry weekly shorts)"}
SITE = "lootdrop-deals.netlify.app"


def won(v):
    return "₩{:,}".format(int(round(v)))


def fetch_deals(n=5):
    r = requests.get("https://store.steampowered.com/api/featuredcategories", params={"cc": "kr", "l": "koreana"}, headers=UA, timeout=30)
    r.raise_for_status()
    items = r.json().get("specials", {}).get("items", [])
    seen, deals = set(), []
    for it in items:
        if it.get("id") in seen or not it.get("discounted") or it.get("discount_percent", 0) < 20:
            continue
        seen.add(it["id"])
        deals.append({"id": it["id"], "name": it["name"], "off": int(it["discount_percent"]),
                      "sale": it["final_price"] / 100, "orig": it["original_price"] / 100})
    deals = deals[:12]
    deals.sort(key=lambda d: -d["off"])  # biggest discounts first among Steam's featured specials
    return deals[:n]


def load_art(app_id):
    base = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app_id}/"
    for name in ("capsule_616x353.jpg", "header.jpg"):
        try:
            r = requests.get(base + name, headers=UA, timeout=30)
            if r.ok and r.headers.get("content-type", "").startswith("image"):
                return Image.open(io.BytesIO(r.content)).convert("RGB")
        except Exception:
            pass
    return Image.new("RGB", (616, 353), (40, 40, 60))


def ease(t):
    t = max(0.0, min(1.0, t)); return 1 - (1 - t) ** 3


def text_c(img, y, s, font, fill, a=1.0, x=None):
    if a <= 0: return
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(layer)
    w = d.textlength(s, font=font)
    d.text(((W - w) / 2 if x is None else x, y), s, font=font, fill=fill + (int(255 * min(1, a)),))
    img.alpha_composite(layer)


def fit_text(s, size, maxw, k=True):
    while size > 30:
        fnt = f(size, k)
        if ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(s, font=fnt) <= maxw: return fnt, s
        size -= 4
    fnt = f(30, k); t = s
    while ImageDraw.Draw(Image.new("RGB", (1, 1))).textlength(t + "…", font=fnt) > maxw and len(t) > 1: t = t[:-1]
    return fnt, t + "…"


def wrap_name(s, maxw):
    meas = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in (78, 70, 62):
        fnt = f(size, True)
        if meas.textlength(s, font=fnt) <= maxw: return [(fnt, s)]
    fnt = f(62, True); words = s.split(" "); line1 = ""
    for i, wd in enumerate(words):
        test = (line1 + " " + wd).strip()
        if meas.textlength(test, font=fnt) > maxw and line1:
            rest = " ".join(words[i:]); f2, r2 = fit_text(rest, 62, maxw)
            return [(fnt, line1), (f2, r2)]
        line1 = test
    f1, t1 = fit_text(s, 62, maxw); return [(f1, t1)]


def rr_mask(w, h, r):
    m = Image.new("L", (w, h), 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, w - 1, h - 1], r, fill=255); return m


def build_bg():
    bg = Image.new("RGB", (W, H), BG); g = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(g)
    d.ellipse([-300, -200, 700, 800], fill=(90, 20, 80)); d.ellipse([500, 1100, 1400, 2100], fill=(20, 40, 110))
    return Image.blend(bg, g.filter(ImageFilter.GaussianBlur(220)), 0.9)


def brand(img, a):
    fnt = f(150, True)
    tmp = Image.new("RGBA", (1100, 260), (0, 0, 0, 0)); td = ImageDraw.Draw(tmp)
    tw = td.textlength("LOOTDROP", font=fnt)
    td.text(((1100 - tw) / 2, 0), "LOOTDROP", font=fnt, fill=BLUE + (int(255 * a),))
    tmp = tmp.transform(tmp.size, Image.AFFINE, (1, 0.22, -40, 0, 1, 0), Image.BICUBIC)
    img.alpha_composite(tmp, (int((W - 1100) / 2), 690))
    logo = Image.open(os.path.join(ROOT, "assets", "logo.png")).convert("RGBA").resize((110, 110), Image.NEAREST)
    m = rr_mask(110, 110, 55); logo.putalpha(Image.eval(m, lambda v: int(v * a)))
    d = ImageDraw.Draw(img); fb = f(52, True); s = "by Pixel Pantry"; w = d.textlength(s, font=fb)
    x0 = (W - (110 + 18 + w)) / 2
    img.alpha_composite(logo, (int(x0), 960))
    text_c(img, 960 + (110 - 75) / 2, s, fb, WHITE, a, x=x0 + 128)


def make_card(deal, art, rank):
    """A deal card 960x1180 RGBA."""
    cw, ch = 960, 1180
    card = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    body = Image.new("RGBA", (cw, ch), (24, 24, 32, 255))
    card.paste(body, (0, 0), rr_mask(cw, ch, 48))
    a = art.resize((cw, int(art.height * cw / art.width)), Image.LANCZOS)
    a = a.crop((0, 0, cw, min(a.height, 560)))
    m = Image.new("L", a.size, 0); ImageDraw.Draw(m).rounded_rectangle([0, 0, a.width - 1, a.height + 60], 48, fill=255)
    card.paste(a, (0, 0), m)
    d = ImageDraw.Draw(card)
    # rank badge
    d.rounded_rectangle([28, 28, 168, 128], 30, fill=PINK); fr = f(64, True)
    s = f"#{rank}"; d.text((98 - d.textlength(s, font=fr) / 2, 30), s, font=fr, fill=WHITE)
    # off badge
    fo = f(72, True); s = f"-{deal['off']}%"; ow = d.textlength(s, font=fo)
    d.rounded_rectangle([cw - ow - 88, 28, cw - 28, 132], 30, fill=YEL); d.text((cw - ow - 58, 30), s, font=fo, fill=(10, 10, 15))
    y = a.height + 50
    lines = wrap_name(deal["name"], cw - 100)
    for fnt, ln in lines:
        d.text((50, y), ln, font=fnt, fill=WHITE); y += int(fnt.size * 1.3)
    y += 40
    fp = f(130, True); d.text((50, y), won(deal["sale"]), font=fp, fill=YEL)
    fo2 = f(56); sx = 50 + d.textlength(won(deal["sale"]), font=fp) + 30
    so = won(deal["orig"]); d.text((sx, y + 62), so, font=fo2, fill=GRAY)
    d.line([sx, y + 98, sx + d.textlength(so, font=fo2), y + 98], fill=GRAY, width=5)
    d.text((50, y + 200), "스팀 한국 스토어 기준", font=f(40), fill=(120, 120, 140))
    return card


def render(deals, arts, date_str, out_mp4, out_cover):
    bg = build_bg()
    cards = [make_card(d, a, i + 1) for i, (d, a) in enumerate(zip(deals, arts))]
    T_INTRO, T_TITLE, T_CARD, T_OUT = 1.8, 1.6, 2.3, 2.6
    t_cards0 = T_INTRO + T_TITLE
    dur = t_cards0 + T_CARD * len(cards) + T_OUT
    n = int(dur * FPS)
    cards[0].save(out_cover.replace(".jpg", ".png"))
    cover = bg.copy().convert("RGBA"); cover.alpha_composite(cards[0], (60, 470))
    text_c(cover, 200, "이번 주 스팀 할인", f(84, True), WHITE); text_c(cover, 310, "TOP PICK", f(60, True), PINK)
    cover.convert("RGB").save(out_cover, quality=92)

    def frame(i):
        t = i / FPS
        img = bg.copy().convert("RGBA")
        if t < T_INTRO + 0.2:
            a = ease(t / 0.15) * (1 - (ease((t - T_INTRO + 0.3) / 0.4) if t > T_INTRO - 0.3 else 0))
            brand(img, a)
        if T_INTRO - 0.1 <= t < t_cards0 + 0.2:
            a = ease((t - T_INTRO + 0.1) / 0.4) * (1 - (ease((t - t_cards0 + 0.2) / 0.3) if t > t_cards0 - 0.2 else 0))
            text_c(img, 700, "이번 주 스팀 할인", f(100, True), WHITE, a)
            text_c(img, 850, f"TOP {len(cards)}", f(150, True), YEL, a)
            text_c(img, 1060, date_str + " 기준", f(48), GRAY, a)
        if t_cards0 <= t < t_cards0 + T_CARD * len(cards) + 0.4:
            k = min(len(cards) - 1, int((t - t_cards0) // T_CARD)); lt = t - t_cards0 - k * T_CARD
            text_c(img, 150, "이번 주 스팀 할인", f(64, True), WHITE)
            text_c(img, 240, "LootDrop · by Pixel Pantry", f(36, True), (150, 170, 230))
            p = ease(lt / 0.45)
            x = int(60 + (1 - p) * W)
            if k > 0 and lt < 0.45:
                img.alpha_composite(cards[k - 1], (int(60 - p * W), 470))
            last_fade = (t - (t_cards0 + T_CARD * len(cards))) if k == len(cards) - 1 else -1
            if last_fade < 0:
                img.alpha_composite(cards[k], (x, 470))
            else:
                c = cards[k].copy(); c.putalpha(Image.eval(c.getchannel("A"), lambda v: int(v * max(0, 1 - last_fade / 0.4))))
                img.alpha_composite(c, (60, 470))
            for j in range(len(cards)):
                cx = W // 2 + int((j - (len(cards) - 1) / 2) * 36)
                ImageDraw.Draw(img).ellipse([cx - 8, 1700, cx + 8, 1716], fill=PINK if j == k else (70, 70, 90))
        to = t_cards0 + T_CARD * len(cards)
        if t >= to:
            a = ease((t - to) / 0.5)
            text_c(img, 640, "더 많은 할인은", f(80, True), WHITE, a)
            text_c(img, 750, "LootDrop에서", f(100, True), YEL, a)
            b = ease((t - to - 0.4) / 0.5)
            if b > 0:
                layer = Image.new("RGBA", (W, H), (0, 0, 0, 0)); ld = ImageDraw.Draw(layer); fu = f(54, True)
                tw = ld.textlength(SITE, font=fu); x0 = (W - tw) / 2 - 50
                ld.rounded_rectangle([x0, 960, x0 + tw + 100, 1070], 55, fill=PINK + (int(255 * b),))
                ld.text(((W - tw) / 2, 976), SITE, font=fu, fill=WHITE + (int(255 * b),))
                img.alpha_composite(layer)
                text_c(img, 1120, "무료 · 설치 없이 바로 · 원화 가격", f(44), GRAY, b)
                text_c(img, 1400, "@pixelpantryhq", f(46, True), WHITE, b)
        return img.convert("RGB")

    silent = out_mp4 + ".silent.mp4"
    p = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-",
                          "-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", silent], stdin=subprocess.PIPE)
    for i in range(n):
        p.stdin.write(frame(i).tobytes())
    p.stdin.close(); p.wait()

    # audio: original chiptune + sfx at transitions
    buf = A.music(dur, ["C", "G", "Am", "F"], bpm=124, seed=int(date_str.replace("-", "")) % 97)
    A.place(buf, A.sfx_pop(), 0.0, 0.5); A.place(buf, A.sfx_pop(), 0.12, 0.35)
    A.place(buf, A.sfx_whoosh(0.4), T_INTRO - 0.1, 0.4); A.place(buf, A.sfx_coin(), T_INTRO + 0.2, 0.35)
    for k in range(len(cards)):
        tk = t_cards0 + k * T_CARD
        A.place(buf, A.sfx_whoosh(0.35), tk, 0.4); A.place(buf, A.sfx_coin(), tk + 0.45, 0.3)
    A.place(buf, A.sfx_ding(), t_cards0 + T_CARD * len(cards) + 0.4, 0.4)
    wav = out_mp4 + ".wav"; A.finish(buf, wav)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", silent, "-i", wav, "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                    "-af", "lowpass=f=8000,loudnorm=I=-16:TP=-1.5:LRA=11", "-shortest", "-movflags", "+faststart", out_mp4], check=True)
    os.remove(silent); os.remove(wav)
    return dur


def main():
    os.makedirs(OUT, exist_ok=True)
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()  # Korea date
    deals = fetch_deals(5)
    if len(deals) < 3:
        print("not enough deals", deals); sys.exit(1)
    arts = [load_art(d["id"]) for d in deals]
    mp4 = os.path.join(OUT, f"{today}.mp4"); cover = os.path.join(OUT, f"{today}.jpg")
    dur = render(deals, arts, today, mp4, cover)
    for d in deals:
        d["store"] = f"https://store.steampowered.com/app/{d['id']}/"
        d["capsule"] = f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{d['id']}/capsule_616x353.jpg"
    info = {"date": today, "video": f"weekly/{today}.mp4", "cover": f"weekly/{today}.jpg", "duration": round(dur, 1), "deals": deals}
    with open(os.path.join(OUT, f"{today}.json"), "w", encoding="utf-8") as fh: json.dump(info, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT, "latest.json"), "w", encoding="utf-8") as fh: json.dump(info, fh, ensure_ascii=False, indent=1)
    print(json.dumps(info, ensure_ascii=False))


if __name__ == "__main__":
    main()
