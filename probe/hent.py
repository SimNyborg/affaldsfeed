"""Midlertidigt probeværktøj til kildeudvidelsen (kun på grenen kilder-udvid, fjernes før PR).

Linjer i probe/request.txt:
  links URL [regex] [max]   links på en HTML-side (href | tekst), evt. filtreret på regex
  text URL [kB]             synlig tekst fra en HTML-side
  pdf URL [kB]              tekst fra en PDF
  raw URL [kB]              rå tekst (som url-linjen i probe.yml)
  rss URL [max]             indslag i et RSS/Atom-feed (dato | titel | link)
  sitemap URL [regex] [max] sitemap eller indeks: antal, under-sitemaps og nyeste URL'er efter lastmod
  feed URL                  python -m affaldsfeed find-feed URL
robots.txt respekteres, UA fra config/settings.yaml, mindst 2 sek. mellem kald til samme vært.
"""

import io
import re
import subprocess
import sys
import time
from urllib.parse import urljoin, urlsplit, urlunsplit

import feedparser
import requests
import yaml
from lxml import etree
from lxml import html as lxml_html
from protego import Protego

with open("config/settings.yaml", encoding="utf-8") as _f:
    UA = yaml.safe_load(_f)["fetch"]["user_agent"]
SESSION = requests.Session()
SESSION.headers["User-Agent"] = UA
_robots: dict[str, Protego | None | bool] = {}
_last: dict[str, float] = {}


def _pace(host: str) -> None:
    wait = 2.0 - (time.time() - _last.get(host, 0.0))
    if wait > 0:
        time.sleep(wait)
    _last[host] = time.time()


def allowed(url: str) -> bool:
    p = urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    if origin not in _robots:
        _pace(p.netloc)
        try:
            r = SESSION.get(origin + "/robots.txt", timeout=30)
            if r.status_code == 200:
                _robots[origin] = Protego.parse(r.text[:500_000])
            elif 400 <= r.status_code < 500:
                _robots[origin] = None
            else:
                print(f"(robots.txt svarede {r.status_code}; henter ikke)")
                _robots[origin] = False
        except requests.RequestException as e:
            print(f"(robots.txt fejlede: {e}; henter ikke)")
            _robots[origin] = False
    rp = _robots[origin]
    if rp is False:
        return False
    return True if rp is None else rp.can_fetch(url, UA)


def get(url: str) -> requests.Response | None:
    if "affaldsviden.info" in url:
        print("(afvist: affaldsviden.info hentes aldrig)")
        return None
    if not allowed(url):
        print("(blokeret af robots.txt)")
        return None
    _pace(urlsplit(url).netloc)
    t0 = time.monotonic()
    try:
        r = SESSION.get(url, timeout=60, allow_redirects=True)
    except requests.RequestException as e:
        print(f"(netværksfejl efter {time.monotonic() - t0:.1f} s: {e})")
        return None
    secs = time.monotonic() - t0
    print(f"status {r.status_code}, {r.headers.get('content-type', '')}, {len(r.content)} bytes, {secs:.1f} s, slut-URL {r.url}")
    return r


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", s or "").strip()


def _doc(r: requests.Response):
    doc = lxml_html.fromstring(r.content)
    base = doc.xpath("//base/@href")
    return doc, urljoin(r.url, base[0]) if base else r.url


def links(url: str, rx: str | None = None, maxn: int = 400) -> None:
    r = get(url)
    if r is None or not r.content:
        return
    doc, base = _doc(r)
    seen: dict[str, str] = {}
    for a in doc.xpath("//a[@href]"):
        href = a.get("href", "").strip()
        if href.startswith(("javascript:", "mailto:", "tel:", "#")):
            continue
        u = urlunsplit(urlsplit(urljoin(base, href))._replace(fragment=""))
        if rx and not re.search(rx, u):
            continue
        t = _clean(a.text_content()) or _clean(a.get("title", "")) or _clean(a.get("aria-label", ""))
        if not t:
            alts = a.xpath(".//img/@alt")
            t = _clean(alts[0]) if alts else ""
        if u not in seen or len(t) > len(seen[u]):
            seen[u] = t
    print(f"{len(seen)} links")
    for i, (u, t) in enumerate(seen.items()):
        if i >= maxn:
            print(f"... ({len(seen) - maxn} flere)")
            break
        print(f"{u} | {t[:120]}")


def text(url: str, kb: int = 30) -> None:
    r = get(url)
    if r is None or not r.content:
        return
    doc, _ = _doc(r)
    for bad in doc.xpath("//script|//style|//noscript|//svg|//template|//iframe"):
        bad.getparent().remove(bad)
    for el in doc.iter():
        if isinstance(el.tag, str) and el.tag in ("p", "div", "li", "br", "h1", "h2", "h3", "h4", "tr", "section", "article"):
            el.tail = "\n" + (el.tail or "")
    t = doc.text_content()
    lines = [_clean(x) for x in t.splitlines()]
    out = "\n".join(x for x in lines if x)
    print(out[: kb * 1000])


def pdf(url: str, kb: int = 100) -> None:
    from pypdf import PdfReader

    r = get(url)
    if r is None or not r.content:
        return
    try:
        reader = PdfReader(io.BytesIO(r.content))
        parts = [(p.extract_text() or "") for p in reader.pages]
    except Exception as e:  # noqa: BLE001 - kun et probeværktøj
        print(f"(kunne ikke læse PDF: {e})")
        return
    out = "\n".join(parts)
    print(f"{len(reader.pages)} sider")
    print(out[: kb * 1000])


def raw(url: str, kb: int = 30) -> None:
    r = get(url)
    if r is None:
        return
    print(r.text[: kb * 1000])


def rss(url: str, maxn: int = 60) -> None:
    r = get(url)
    if r is None or not r.content:
        return
    f = feedparser.parse(r.content)
    print(f"feed: {_clean(f.feed.get('title', ''))} | {len(f.entries)} indslag | bozo {f.bozo}")
    for e in f.entries[:maxn]:
        d = e.get("published") or e.get("updated") or "-"
        print(f"{d} | {_clean(e.get('title', ''))[:110]} | {e.get('link', '')}")


def _local(tag: object) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def sitemap(url: str, rx: str | None = None, maxn: int = 40) -> None:
    r = get(url)
    if r is None or not r.content:
        return
    try:
        root = etree.fromstring(r.content, etree.XMLParser(resolve_entities=False, no_network=True, huge_tree=True))
    except etree.XMLSyntaxError as e:
        print(f"(ikke XML: {e})")
        print(r.text[:2000])
        return
    kind = _local(root.tag)
    rows = []
    for el in root:
        loc = lastmod = ""
        news_title = ""
        for c in el.iter():
            n = _local(c.tag)
            if n == "loc" and not loc:
                loc = (c.text or "").strip()
            elif n == "lastmod":
                lastmod = (c.text or "").strip()
            elif n == "title":
                news_title = _clean(c.text or "")
            elif n == "publication_date" and not lastmod:
                lastmod = (c.text or "").strip()
        if loc:
            rows.append((lastmod, loc, news_title))
    print(f"{kind}: {len(rows)} poster, {sum(1 for x in rows if x[0])} med lastmod")
    if rx:
        rows = [x for x in rows if re.search(rx, x[1])]
        print(f"matcher {rx!r}: {len(rows)}")
    rows.sort(key=lambda x: x[0], reverse=True)
    for lastmod, loc, t in rows[:maxn]:
        print(f"{lastmod or '-'} | {loc}" + (f" | {t[:90]}" if t else ""))
    if not rx and len(rows) > maxn:
        # Et udsnit af resten, så stierne kan ses
        step = max(1, len(rows) // 20)
        print("... udsnit:")
        for lastmod, loc, _ in rows[maxn::step][:20]:
            print(f"{lastmod or '-'} | {loc}")


def main() -> None:
    mode, *rest = sys.argv[1:]
    url = rest[0]
    args = rest[1:]
    if mode == "links":
        rx = args[0] if args and not args[0].isdigit() else None
        nums = [int(a) for a in args if a.isdigit()]
        links(url, rx, nums[0] if nums else 400)
    elif mode == "text":
        text(url, int(args[0]) if args else 30)
    elif mode == "pdf":
        pdf(url, int(args[0]) if args else 100)
    elif mode in ("raw", "url"):
        raw(url, min(400, int(args[0])) if args else 30)
    elif mode == "rss":
        rss(url, int(args[0]) if args else 60)
    elif mode == "sitemap":
        rx = args[0] if args and not args[0].isdigit() else None
        nums = [int(a) for a in args if a.isdigit()]
        sitemap(url, rx, nums[0] if nums else 40)
    elif mode == "feed":
        subprocess.run([sys.executable, "-m", "affaldsfeed", "find-feed", url], timeout=240, check=False)
    elif mode == "site":
        for u in rest:
            site(u)
    elif mode == "robots":
        for u in rest:
            robots(u)
    else:
        print(f"ukendt tilstand: {mode}")


AI_BOTS = ("GPTBot", "ClaudeBot", "anthropic-ai", "CCBot", "Google-Extended", "PerplexityBot", "Applebot-Extended")


def robots(url: str) -> None:
    """Kort robots-status: * og AI-bots for / (og stien i URL'en), Crawl-delay, sitemaps og TDM-linjer."""
    if not url.startswith("http"):
        url = "https://" + url
    p = urlsplit(url)
    origin = f"{p.scheme}://{p.netloc}"
    path_url = url if p.path not in ("", "/") else origin + "/"
    _pace(p.netloc)
    try:
        r = SESSION.get(origin + "/robots.txt", timeout=30)
    except requests.RequestException as e:
        print(f"# {origin}: robots.txt fejlede: {e}")
        return
    if r.status_code != 200:
        print(f"# {origin}: robots.txt svarer {r.status_code} (4xx = alt tilladt)")
        return
    rp = Protego.parse(r.text[:500_000])
    star = "ja" if rp.can_fetch(path_url, UA) else "NEJ"
    ai = [b for b in AI_BOTS if not rp.can_fetch(path_url, b)]
    delay = rp.crawl_delay(UA)
    maps = list(rp.sitemaps)[:4]
    extra = [x.strip() for x in r.text.splitlines() if re.search(r"tdm|\bai\b|train", x, re.IGNORECASE)][:4]
    print(
        f"# {origin}: vores UA må hente {path_url}: {star} | Crawl-delay: {delay or '-'} | "
        f"AI-bots spærret: {', '.join(ai) or 'ingen'} | sitemaps: {', '.join(maps) or '-'}"
        + (f" | linjer: {' ; '.join(extra)}" if extra else "")
    )


_DATE_RE = re.compile(r"(20[0-3]\d)-(0[1-9]|1[0-2])-([0-2]\d|3[01])")
_DA_MONTHS = "januar|februar|marts|april|maj|juni|juli|august|september|oktober|november|december"
_DA_DATE_RE = re.compile(rf"\b([0-3]?\d)\. ({_DA_MONTHS}) (20[0-3]\d)\b", re.IGNORECASE)


def site(url: str) -> None:
    """Én linje pr. hjemmeside: status, slut-URL, titel, site_name, nyeste dato og feed-links."""
    if not url.startswith("http"):
        url = "https://" + url
    print(f"# {url}")
    r = get(url)
    if r is None:
        return
    if not r.content or "html" not in r.headers.get("content-type", "html"):
        return
    try:
        doc, base = _doc(r)
    except (etree.ParserError, ValueError):
        print("  (kunne ikke parse HTML)")
        return
    title = _clean(" ".join(doc.xpath("//title/text()")))[:100]
    site_name = _clean(" ".join(doc.xpath("//meta[@property='og:site_name']/@content")))[:60]
    html_text = r.text
    today = time.strftime("%Y-%m-%d")
    dates = sorted({"-".join(m.groups()) for m in _DATE_RE.finditer(html_text)})
    dates = [d for d in dates if d <= today]
    months = {m: i + 1 for i, m in enumerate(_DA_MONTHS.split("|"))}
    da_dates = sorted(
        f"{y}-{months[mo.lower()]:02d}-{int(d):02d}"
        for d, mo, y in _DA_DATE_RE.findall(doc.text_content())
        if f"{y}-{months[mo.lower()]:02d}-{int(d):02d}" <= today
    )
    feeds = [
        urljoin(base, h)
        for h in doc.xpath("//link[@rel='alternate'][contains(@type,'rss') or contains(@type,'atom')]/@href")
    ]
    gen = _clean(" ".join(doc.xpath("//meta[@name='generator']/@content")))[:40]
    n2026 = sum(1 for h in doc.xpath("//a/@href") if "2026" in h)
    print(
        f"  titel: {title} | site_name: {site_name or '-'} | generator: {gen or '-'}\n"
        f"  nyeste ISO-dato: {dates[-1] if dates else '-'} | nyeste danske dato: {da_dates[-1] if da_dates else '-'}"
        f" | links med 2026: {n2026} | feeds: {', '.join(feeds[:3]) or '-'}"
    )


if __name__ == "__main__":
    main()
