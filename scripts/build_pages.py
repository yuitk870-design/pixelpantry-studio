"""Build SEO pages for LootDrop: /game/<appid>/ per game, /game/ index, /sale/ special, sitemap.xml.
Runs daily on GitHub Actions. Uses Steam KR store data (real KRW prices) + CheapShark (deal IDs, historical low).
"""
import html, json, os, re, sys, time, datetime as dt
import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(ROOT, "site")
BASE = "https://lootdrop-deals.netlify.app"
UA = {"User-Agent": "LootDrop/1.0 (+https://lootdrop-deals.netlify.app; Pixel Pantry studio)"}
CS = "https://www.cheapshark.com/api/1.0"
KST = dt.timezone(dt.timedelta(hours=9))
NOW = dt.datetime.now(KST)
GA = "G-EKX2S6X3T0"
MAX_GAMES = 300

# Steam events (KST dates). The sale page switches automatically between "upcoming" and "live".
EVENTS = [
    {"name": "스팀 스크림 페스티벌", "start": "2026-10-27", "end": "2026-11-03"},
    {"name": "스팀 겨울 세일", "start": "2026-12-18", "end": "2027-01-05"},
]


HEADER_SETS = [UA, {**UA, "Accept": "application/json"}]


def get(url, params=None, tries=3):
    for i in range(tries):
        hdr = HEADER_SETS[min(i, len(HEADER_SETS) - 1)]
        try:
            r = requests.get(url, params=params, headers=hdr, timeout=30)
            if r.status_code == 429:
                time.sleep(10 * (i + 1)); continue
            if not r.ok:
                print("HTTP", r.status_code, url, params, "hdr#%d" % i, repr(r.text[:300]))
            r.raise_for_status()
            return r.json()
        except Exception as e:
            if i == tries - 1:
                print("GET failed", url, params, e)
            time.sleep(2 * (i + 1))
    return None


def won(v):
    return "₩{:,}".format(int(round(v)))


def esc(s):
    return html.escape(str(s or ""), quote=True)


# ---------------- data ----------------
def collect_candidates():
    """CheapShark Steam deals: on-sale by deal rating + well-reviewed games (incl. not on sale)."""
    found = {}
    queries = [{"sortBy": "Deal Rating", "onSale": 1}, {"sortBy": "Reviews", "onSale": 0}, {"sortBy": "Metacritic", "onSale": 0}]
    for q in queries:
        for page in range(3):
            data = get(CS + "/deals", {"storeID": 1, "pageSize": 60, "pageNumber": page, **q}) or []
            for d in data:
                app = d.get("steamAppID")
                if not app or app == "0":
                    continue
                cnt = int(d.get("steamRatingCount") or 0)
                if cnt < 800:
                    continue
                if app not in found:
                    found[app] = {"app": int(app), "dealID": d["dealID"], "gameID": d.get("gameID"), "title": d["title"], "reviews": cnt,
                                  "rating": int(d.get("steamRatingPercent") or 0)}
            time.sleep(1)
    return found


def cheapest_ever(game_ids):
    out = {}
    ids = [g for g in game_ids if g]
    for i in range(0, len(ids), 25):
        data = get(CS + "/games", {"ids": ",".join(ids[i:i + 25])}) or {}
        for gid, v in data.items():
            try:
                out[gid] = float(v["cheapestPriceEver"]["price"])
            except Exception:
                pass
        time.sleep(1)
    return out


def steam_details(app):
    data = get("https://store.steampowered.com/api/appdetails", {"appids": app, "cc": "kr", "l": "koreana"})
    if not data or not data.get(str(app), {}).get("success"):
        return None
    d = data[str(app)]["data"]
    if d.get("type") != "game":
        return None
    po = d.get("price_overview") or {}
    if d.get("is_free"):
        return None
    if not po:
        return None
    return {
        "name": d.get("name"),
        "desc": re.sub(r"\s+", " ", d.get("short_description") or "").strip(),
        "genres": [g["description"] for g in (d.get("genres") or [])][:4],
        "release": (d.get("release_date") or {}).get("date", ""),
        "meta": (d.get("metacritic") or {}).get("score"),
        "dev": ", ".join(d.get("developers") or [])[:60],
        "price": po.get("final", 0) / 100,
        "regular": po.get("initial", 0) / 100,
        "off": int(po.get("discount_percent") or 0),
        "header": d.get("header_image") or f"https://shared.akamai.steamstatic.com/store_item_assets/steam/apps/{app}/header.jpg",
        "korean": "한국어" in (d.get("supported_languages") or ""),
    }


def usd_krw():
    data = get("https://api.frankfurter.dev/v1/latest", {"base": "USD", "symbols": "KRW"}) or {}
    return float((data.get("rates") or {}).get("KRW") or 1400)


# ---------------- html ----------------
CSS = """
:root{--bg:#0A0A0F;--card:#15151d;--line:#262633;--text:#F4F5FA;--dim:#9a9ab0;--blue:#2979FF;--pink:#FF2D87;--yel:#FFD60A;--green:#22C55E}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:"Noto Sans KR",system-ui,-apple-system,sans-serif;line-height:1.55}
a{color:inherit}.wrap{max-width:860px;margin:0 auto;padding:16px}
header.top{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;max-width:860px;margin:0 auto}
.logo{font-weight:900;font-style:italic;color:var(--blue);text-decoration:none;font-size:22px;letter-spacing:.02em}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:6px;border-radius:999px;padding:12px 18px;font-weight:800;text-decoration:none;border:0;font-size:15px}
.btn-pink{background:var(--pink);color:#fff}.btn-blue{background:var(--blue);color:#fff}.btn-ghost{background:#1d1d27;color:var(--text);border:1px solid var(--line)}
.hero img{width:100%;border-radius:18px;display:block;aspect-ratio:460/215;object-fit:cover;background:#1d1d27}
h1{font-size:26px;line-height:1.3;margin:18px 0 6px}h2{font-size:19px;margin:28px 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:8px 0}.chip{background:#1d1d27;border:1px solid var(--line);border-radius:999px;padding:4px 10px;font-size:13px;color:var(--dim)}
.price{background:var(--card);border:1px solid var(--line);border-radius:18px;padding:18px;margin-top:16px}
.now{font-size:34px;font-weight:900;color:var(--yel)}.old{color:var(--dim);text-decoration:line-through;margin-left:8px}
.off{background:var(--green);color:#04210f;font-weight:900;border-radius:999px;padding:3px 10px;margin-left:8px;font-size:14px}
.row{display:flex;justify-content:space-between;border-top:1px solid var(--line);padding:10px 0;margin-top:10px;color:var(--dim)}.row b{color:var(--text)}
.actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}.actions .btn{flex:1;min-width:150px}
.note{color:var(--dim);font-size:13px;margin-top:10px}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:12px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;text-decoration:none;display:block}
.card img{width:100%;aspect-ratio:460/215;object-fit:cover;display:block;background:#1d1d27}.card .b{padding:10px 12px}
.card .t{font-weight:800;font-size:15px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}.card .p{margin-top:4px;font-size:14px}
.card .p .y{color:var(--yel);font-weight:900}.card .p .g{color:var(--green);font-weight:800;margin-left:6px}
.search{width:100%;padding:13px 16px;border-radius:12px;border:1px solid var(--line);background:#14141b;color:var(--text);font-size:16px;margin:10px 0 16px}
footer{color:var(--dim);font-size:13px;text-align:center;padding:30px 16px 40px}
.badge{display:inline-block;background:var(--yel);color:#111;font-weight:900;border-radius:8px;padding:2px 8px;font-size:12px;margin-left:6px}
.event{background:linear-gradient(135deg,#ff2d87,#7b3cff 55%,#2979ff);border-radius:20px;padding:22px;margin:10px 0 18px}
.event h1{margin:0 0 6px}.event p{margin:0;opacity:.92}
"""


def page(title, desc, path, body, extra_head=""):
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(desc)}">
<link rel="canonical" href="{BASE}{path}"><meta name="robots" content="index,follow">
<meta property="og:type" content="website"><meta property="og:title" content="{esc(title)}"><meta property="og:description" content="{esc(desc)}">
<meta property="og:url" content="{BASE}{path}"><meta property="og:image" content="{BASE}/og-image.png"><meta property="og:locale" content="ko_KR">
<meta name="theme-color" content="#0A0A0F">
<script async src="https://www.googletagmanager.com/gtag/js?id={GA}"></script>
<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{GA}',{{allow_google_signals:false,allow_ad_personalization_signals:false}});</script>
<style>{CSS}</style>{extra_head}</head><body>
<header class="top"><a class="logo" href="/">LOOTDROP</a><a class="btn btn-pink" href="/" style="padding:9px 14px;font-size:13px">앱에서 보기</a></header>
<main class="wrap">{body}</main>
<footer>LootDrop · by Pixel Pantry — 가격은 스팀 한국 스토어 기준이며 바뀔 수 있어요. 업데이트 {NOW:%Y-%m-%d}</footer>
</body></html>"""


def game_page(g):
    name = g["name"]
    title = f"{name} 최저가·할인 정보 — 지금 {won(g['price'])}" + (f" ({g['off']}% 할인)" if g["off"] else "")
    desc = f"{name} 스팀 현재 가격 {won(g['price'])}" + (f", 정가 {won(g['regular'])}에서 {g['off']}% 할인 중" if g["off"] else "") + \
           (f". 역대 최저가 약 {won(g['low_krw'])}" if g.get("low_krw") else "") + ". 가격 변동 그래프와 목표가 알림은 LootDrop에서."
    chips = "".join(f'<span class="chip">{esc(x)}</span>' for x in (g["genres"] + ([f"출시 {g['release']}"] if g["release"] else []) +
                                                               (["한국어 지원"] if g["korean"] else []) + ([f"메타크리틱 {g['meta']}"] if g["meta"] else [])))
    low_row = f'<div class="row"><span>역대 최저가 (약)</span><b>{won(g["low_krw"])}</b></div>' if g.get("low_krw") else ""
    is_low = g.get("low_krw") and g["price"] <= g["low_krw"] * 1.02 and g["off"] > 0
    ld = {"@context": "https://schema.org", "@type": "VideoGame", "name": name, "url": f"{BASE}/game/{g['app']}/", "image": g["header"],
          "description": g["desc"][:300], "gamePlatform": "PC",
          "offers": {"@type": "Offer", "price": int(g["price"]), "priceCurrency": "KRW", "availability": "https://schema.org/InStock",
                     "url": f"https://store.steampowered.com/app/{g['app']}/"}}
    body = f"""
<div class="hero"><img src="{esc(g['header'])}" alt="{esc(name)}" loading="eager"></div>
<h1>{esc(name)} 최저가·할인 정보{'<span class="badge">역대 최저가</span>' if is_low else ''}</h1>
<div class="chips">{chips}</div>
<p style="color:var(--dim);margin:6px 0 0">{esc(g['desc'])}</p>
<div class="price">
  <div><span class="now">{won(g['price'])}</span>{f'<span class="old">{won(g["regular"])}</span><span class="off">-{g["off"]}%</span>' if g['off'] else ''}</div>
  {low_row}
  <div class="row"><span>스팀 평가</span><b>{g.get('rating') or '-'}% · 리뷰 {g.get('reviews', 0):,}개</b></div>
  <div class="actions">
    <a class="btn btn-blue" href="/#deal={esc(g['dealID'])}">가격 그래프 보기 · 목표가 알림</a>
    <a class="btn btn-ghost" href="https://store.steampowered.com/app/{g['app']}/" rel="noopener" target="_blank">스팀에서 보기</a>
  </div>
  <div class="note">현재가와 정가는 스팀 한국 스토어 기준이에요. 역대 최저가는 달러 기록을 오늘 환율로 바꾼 대략적인 값이에요.</div>
</div>
<h2>{esc(name)} 지금 사도 될까?</h2>
<p style="color:var(--dim)">{verdict(g)}</p>
<h2>다른 할인 게임</h2>
<p><a href="/game/">게임별 최저가 전체 보기 →</a> · <a href="/sale/">이번 세일 특집 →</a></p>
"""
    return page(title, desc, f"/game/{g['app']}/", body, f'<script type="application/ld+json">{json.dumps(ld, ensure_ascii=False)}</script>')


def verdict(g):
    if not g["off"]:
        return "지금은 할인 중이 아니에요. LootDrop에서 찜하고 목표가를 걸어두면 가격이 내려갈 때 확인하기 쉬워요."
    if g.get("low_krw") and g["price"] <= g["low_krw"] * 1.02:
        return f"지금 가격이 역대 최저가 수준이에요. {g['off']}% 할인 중이라 사기 좋은 타이밍이에요."
    if g.get("low_krw"):
        gap = g["price"] - g["low_krw"]
        return f"{g['off']}% 할인 중이지만 역대 최저가보다 약 {won(gap)} 비싸요. 급하지 않다면 목표가를 걸어두고 기다려봐도 좋아요."
    return f"{g['off']}% 할인 중이에요. 가격 변동 그래프로 예전 가격과 비교해보세요."


def card(g):
    p = f'<span class="y">{won(g["price"])}</span>' + (f'<span class="g">-{g["off"]}%</span>' if g["off"] else "")
    return (f'<a class="card" href="/game/{g["app"]}/" data-n="{esc((g["name"] + " " + g.get("title", "")).lower())}">'
            f'<img src="{esc(g["header"])}" alt="" loading="lazy"><div class="b"><div class="t">{esc(g["name"])}</div><div class="p">{p}</div></div></a>')


def index_page(games):
    games = sorted(games, key=lambda g: (-g["off"], -g.get("reviews", 0)))
    cards = "".join(card(g) for g in games)
    body = f"""<h1>스팀 게임별 최저가·할인 정보</h1>
<p style="color:var(--dim)">인기 스팀 게임 {len(games)}개의 현재 원화 가격, 할인율, 역대 최저가를 매일 업데이트해요.</p>
<input class="search" id="q" placeholder="게임 이름으로 찾기 (예: 엘든 링, 스카이림)">
<div class="grid" id="g">{cards}</div>
<script>document.getElementById('q').addEventListener('input',function(e){{var v=e.target.value.trim().toLowerCase();document.querySelectorAll('#g .card').forEach(function(c){{c.style.display=!v||c.dataset.n.indexOf(v)>-1?'':'none';}});}});</script>"""
    return page("스팀 게임 최저가·할인 정보 모음 — LootDrop", f"인기 스팀 게임 {len(games)}개의 현재 원화 가격과 역대 최저가를 한눈에. 매일 업데이트.", "/game/", body)


def sale_page(games):
    today = NOW.date()
    ev_html, title, desc = "", "스팀 할인 특집 — 지금 역대 최저가인 게임", "지금 스팀에서 역대 최저가 수준인 게임과 큰 폭으로 할인 중인 게임 모음. 매일 업데이트."
    for ev in EVENTS:
        s, e = dt.date.fromisoformat(ev["start"]), dt.date.fromisoformat(ev["end"])
        if today <= e:
            y = s.year
            if s <= today:
                ev_html = f'<div class="event"><h1>{ev["name"]} {y} 진행 중!</h1><p>{s:%m월 %d일} ~ {e:%m월 %d일} · 지금 사면 좋은 게임을 매일 골라드려요</p></div>'
                title = f'{ev["name"]} {y} 최저가 추천 — 역대 최저가 게임 모음'
            else:
                days = (s - today).days
                ev_html = f'<div class="event"><h1>{ev["name"]} {y}까지 D-{days}</h1><p>{s:%Y년 %m월 %d일} 시작 · 세일 전에 찜하고 목표가를 걸어두세요</p></div>'
                title = f'{ev["name"]} {y} 날짜·추천 게임 — 지금 미리 찜하기'
            desc = f'{ev["name"]} {y} ({s:%m/%d}~{e:%m/%d}) 일정과 추천 할인 게임, 역대 최저가 모음. 원화 가격으로 매일 업데이트.'
            break
    lows = [g for g in games if g["off"] and g.get("low_krw") and g["price"] <= g["low_krw"] * 1.02]
    big = [g for g in games if g["off"] >= 60 and g not in lows]
    lows.sort(key=lambda g: -g.get("reviews", 0)); big.sort(key=lambda g: (-g["off"], -g.get("reviews", 0)))
    body = ev_html + f"""
<h2>지금 역대 최저가인 게임 ({len(lows)})</h2>
<div class="grid">{''.join(card(g) for g in lows[:60]) or '<p style="color:var(--dim)">오늘은 역대 최저가 게임이 없어요.</p>'}</div>
<h2>60% 이상 할인 중 ({len(big)})</h2>
<div class="grid">{''.join(card(g) for g in big[:60])}</div>
<p style="margin-top:24px"><a class="btn btn-pink" href="/">LootDrop에서 목표가 걸어두기</a></p>"""
    return page(title, desc, "/sale/", body)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def main():
    data_path = os.path.join(SITE, "game", "data.json")
    known = {}
    if os.path.exists(data_path):
        with open(data_path, encoding="utf-8") as fh:
            known = {str(g["app"]): g for g in json.load(fh)}
    cands = collect_candidates()
    for app, c in cands.items():
        known.setdefault(app, {}).update({k: c[k] for k in ("app", "dealID", "gameID", "title", "reviews", "rating")})
    apps = sorted(known.values(), key=lambda g: -g.get("reviews", 0))[:MAX_GAMES]
    low = cheapest_ever([g.get("gameID") for g in apps])
    rate = usd_krw()
    games = []
    for g in apps:
        d = steam_details(g["app"])
        time.sleep(1.2)
        if not d:
            continue
        g.update(d)
        if g.get("gameID") in low:
            g["low_krw"] = round(low[g["gameID"]] * rate / 10) * 10
            if g["low_krw"] > g["price"] and g["off"] > 0:
                g["low_krw"] = g["price"]  # today's KR price is lower than the converted USD record
        games.append(g)
    if len(games) < 20:
        print("too few games, abort", len(games)); sys.exit(1)
    for g in games:
        write(os.path.join(SITE, "game", str(g["app"]), "index.html"), game_page(g))
    write(os.path.join(SITE, "game", "index.html"), index_page(games))
    write(os.path.join(SITE, "sale", "index.html"), sale_page(games))
    with open(data_path, "w", encoding="utf-8") as fh:
        json.dump(games, fh, ensure_ascii=False)
    # sitemap: home + index pages + every game page that exists on disk
    urls = [(f"{BASE}/", "daily", "1.0"), (f"{BASE}/game/", "daily", "0.9"), (f"{BASE}/sale/", "daily", "0.9")]
    gdir = os.path.join(SITE, "game")
    for name in sorted(os.listdir(gdir)):
        if name.isdigit() and os.path.exists(os.path.join(gdir, name, "index.html")):
            urls.append((f"{BASE}/game/{name}/", "daily", "0.7"))
    sm = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u, f_, p in urls:
        sm.append(f"  <url><loc>{u}</loc><lastmod>{NOW:%Y-%m-%d}</lastmod><changefreq>{f_}</changefreq><priority>{p}</priority></url>")
    sm.append("</urlset>")
    write(os.path.join(SITE, "sitemap.xml"), "\n".join(sm) + "\n")
    print(f"built {len(games)} game pages, sitemap {len(urls)} urls")


if __name__ == "__main__":
    main()
