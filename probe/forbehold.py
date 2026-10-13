"""Forbehold hos kilderne (kun på grenen kilder-udvid): robots.txt, AI-bots og TDM-forbehold.

Brug: python probe/forbehold.py [--workers 8]
Læser alle kilder i sources.yaml og domænerne i config/medier.yaml. For hver vært hentes robots.txt,
/.well-known/tdmrep.json og forsiden (kun hvis robots.txt tillader det). Resultatet skrives til
probe/forbehold.json og som oversigt på stdout. UA fra config/settings.yaml, mindst 2 sek. mellem kald
til samme vært, og værterne hentes parallelt.
"""

import argparse
import json
import re
import sys
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlsplit

import requests
import yaml
from lxml import html as lxml_html
from protego import Protego

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from affaldsfeed.config import load_sources  # noqa: E402

with open("config/settings.yaml", encoding="utf-8") as _f:
    UA = yaml.safe_load(_f)["fetch"]["user_agent"]
UA_TOKEN = UA.split("/")[0]

AI_BOTS = (
    "GPTBot", "ChatGPT-User", "OAI-SearchBot", "ClaudeBot", "Claude-User", "Claude-SearchBot", "anthropic-ai",
    "CCBot", "Google-Extended", "PerplexityBot", "Applebot-Extended", "Bytespider", "meta-externalagent",
    "cohere-ai", "Amazonbot",
)
# Ord, der peger på forbehold mod tekst- og datamining, AI eller scraping
RESERVE_RE = re.compile(
    r"tekst-? og datamining|text (?:and|&) data mining|\bTDM\b|datamining|data mining|§ ?11 ?b|"
    r"scrap\w*|crawl\w*|kunstig intelligens|\bAI\b|maskinlæring|machine learning|sprogmodel|"
    r"ophavsret\w*|copyright|eftertryk|gengiv\w*",
    re.IGNORECASE,
)
TERMS_RE = re.compile(r"vilkår|betingelser|ophavsret|copyright|terms|rettigheder|brug af indhold", re.IGNORECASE)
MAX_PAGE = 2_000_000
_local = threading.local()


def session() -> requests.Session:
    s = getattr(_local, "s", None)
    if s is None:
        s = requests.Session()
        s.headers["User-Agent"] = UA
        _local.s = s
    return s


def _decode(body: bytes, r: requests.Response) -> str:
    """Tegnsæt fra Content-Type, ellers UTF-8 og til sidst cp1252 (requests gætter ellers latin-1)."""
    if "charset=" in r.headers.get("content-type", "").lower() and r.encoding:
        return body.decode(r.encoding, errors="replace")
    try:
        return body.decode("utf-8")
    except UnicodeDecodeError:
        return body.decode("cp1252", errors="replace")


class Host:
    """Én vært: hentes sekventielt med mindst 2 sek. mellem kaldene."""

    def __init__(self, origin: str) -> None:
        self.origin = origin
        self.last = 0.0

    def get(self, url: str, limit: int = MAX_PAGE) -> tuple[int, dict, str, str]:
        wait = 2.0 - (time.time() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.time()
        try:
            with session().get(url, timeout=25, stream=True, allow_redirects=True) as r:
                body = b""
                for chunk in r.iter_content(65536):
                    body += chunk
                    if len(body) > limit:
                        break
                return r.status_code, {k.lower(): v for k, v in r.headers.items()}, _decode(body, r), r.url
        except requests.RequestException as e:
            return 0, {}, f"{type(e).__name__}: {e}"[:200], url


def check(origin: str, urls: list[str]) -> dict:
    h = Host(origin)
    out: dict = {"origin": origin}
    status, _, text, _ = h.get(origin + "/robots.txt", 500_000)
    out["robots_status"] = status
    rp = Protego.parse(text) if status == 200 else None
    if status == 0:
        out["robots_error"] = text
    if rp is not None:
        out["blocked_urls"] = [u for u in urls if not rp.can_fetch(u, UA)]
        out["star_root"] = rp.can_fetch(origin + "/", "*")
        out["ai_blocked"] = [b for b in AI_BOTS if not rp.can_fetch(origin + "/", b)]
        out["ua_named"] = UA_TOKEN.lower() in text.lower()
        out["crawl_delay"] = rp.crawl_delay(UA)
        out["robots_lines"] = [
            ln.strip()[:200] for ln in text.splitlines()
            if ln.strip().startswith("#") and RESERVE_RE.search(ln)
        ][:6]
    else:
        # 4xx: ingen robots.txt, alt er tilladt; 5xx eller fejl: pipelinen henter ikke
        out["blocked_urls"] = [] if 400 <= status < 500 else list(urls)
        out["ai_blocked"] = []
    allowed = (lambda u: rp.can_fetch(u, UA)) if rp is not None else (lambda u: 400 <= status < 500)

    tdm_url = origin + "/.well-known/tdmrep.json"
    if allowed(tdm_url):
        st, _, body, _ = h.get(tdm_url, 200_000)
        out["tdmrep_status"] = st
        if st == 200:
            try:
                out["tdmrep"] = json.loads(body)
            except ValueError:
                out["tdmrep"] = body[:300]
    home = origin + "/"
    if not allowed(home):
        out["home"] = "spærret af robots.txt" if rp is not None else "robots.txt utilgængelig"
        return out
    st, headers, body, final = h.get(home)
    out["home_status"] = st
    out["home_final"] = final
    out["tdm_header"] = headers.get("tdm-reservation")
    out["tdm_policy_header"] = headers.get("tdm-policy")
    out["x_robots"] = headers.get("x-robots-tag")
    if st == 200 and body:
        try:
            doc = lxml_html.fromstring(body)
        except (ValueError, lxml_html.etree.ParserError):
            return out
        meta = {
            (m.get("name") or "").lower(): (m.get("content") or "")
            for m in doc.xpath("//meta[@name]")
        }
        out["tdm_meta"] = meta.get("tdm-reservation")
        out["tdm_policy_meta"] = meta.get("tdm-policy")
        out["robots_meta"] = meta.get("robots")
        for bad in doc.xpath("//script|//style|//noscript"):
            bad.drop_tree()
        txt = re.sub(r"\s+", " ", doc.text_content())
        snips = []
        end = -1
        for m in RESERVE_RE.finditer(txt):
            if m.start() < end:
                continue  # inden for det forrige uddrag
            around = txt[max(0, m.start() - 90):m.end() + 90]
            if m.group(0).lower() == "ai" and not re.search(r"træn|model|tdm|data", around, re.I):
                continue
            snips.append(around.strip())
            end = m.end() + 90
            if len(snips) >= 3:
                break
        out["home_snippets"] = snips
        terms = []
        for a in doc.xpath("//a[@href]"):
            label = re.sub(r"\s+", " ", a.text_content()).strip()
            href = a.get("href") or ""
            if TERMS_RE.search(label) or TERMS_RE.search(href):
                full = urljoin(final, href)
                if full.startswith("http") and full not in terms:
                    terms.append(full)
            if len(terms) >= 4:
                break
        out["terms_links"] = terms
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    today = date.today().isoformat()
    origins: dict[str, list[str]] = defaultdict(list)
    who: dict[str, list[str]] = defaultdict(list)
    for s in load_sources(Path("sources.yaml")):
        for u in [*s.feeds, s.homepage]:
            u = u.replace("{dato}", today).replace("{q}", "affald")
            p = urlsplit(u)
            if not p.scheme.startswith("http") or "affaldsviden.info" in p.netloc:
                continue
            origin = f"{p.scheme}://{p.netloc}"
            if u not in origins[origin]:
                origins[origin].append(u)
            tag = f"{s.id} ({s.status}, {s.method}{', ai: false' if s.ai is False else ''})"
            if tag not in who[origin]:
                who[origin].append(tag)
    for m in yaml.safe_load(Path("config/medier.yaml").read_text(encoding="utf-8")) or []:
        for d in m.get("domains") or []:
            origin = f"https://{d}"
            origins.setdefault(origin, [origin + "/"])
            tag = f"{m['id']} (medier.yaml)"
            if tag not in who[origin]:
                who[origin].append(tag)
    print(f"# Forbehold hos kilderne {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
    print(f"\n{len(origins)} værter, UA: {UA}\n")
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        results = list(pool.map(lambda o: check(o, origins[o]), sorted(origins)))
    for r in results:
        r["sources"] = who[r["origin"]]
        r["urls"] = origins[r["origin"]]
    Path("probe/forbehold.json").write_text(json.dumps(results, ensure_ascii=False, indent=1), encoding="utf-8")
    for r in results:
        flags = []
        if r.get("blocked_urls"):
            flags.append(f"spærret for vores UA: {len(r['blocked_urls'])} adresser")
        if r.get("ai_blocked"):
            flags.append(f"AI-bots spærret: {len(r['ai_blocked'])}")
        if r.get("tdm_header") or r.get("tdm_meta") or r.get("tdmrep_status") == 200:
            flags.append("TDM-forbehold (maskinlæsbart)")
        print(f"- {r['origin']} [robots {r.get('robots_status')}] {'; '.join(flags) or 'ingen fund'}")
    print(f"\nFærdig: {len(results)} værter. Detaljer i probe/forbehold.json.")


if __name__ == "__main__":
    main()
