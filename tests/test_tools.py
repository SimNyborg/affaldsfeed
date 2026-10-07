"""Tests for tools/: check_colors (CIEDE2000, kontrast, Machado), import_csv og find_feed. Intet netværk."""

import gzip
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml

from affaldsfeed.models import Source

ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "tools"


def _load(name: str):
    mod_name = f"affaldsfeed_tools_{name}"
    if mod_name in sys.modules:
        return sys.modules[mod_name]
    spec = importlib.util.spec_from_file_location(mod_name, TOOLS / f"{name}.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


check_colors = _load("check_colors")
import_csv = _load("import_csv")
find_feed = _load("find_feed")


# ── check_colors ────────────────────────────────────────────

# Sharma, Wu & Dalal (2005), tabel 1: (Lab1, Lab2, ΔE00)
SHARMA = [
    ((50.0000, 2.6772, -79.7751), (50.0000, 0.0000, -82.7485), 2.0425),
    ((50.0000, 3.1571, -77.2803), (50.0000, 0.0000, -82.7485), 2.8615),
    ((50.0000, 2.8361, -74.0200), (50.0000, 0.0000, -82.7485), 3.4412),
    ((50.0000, -1.3802, -84.2814), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -1.1848, -84.8006), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, -0.9009, -85.5211), (50.0000, 0.0000, -82.7485), 1.0000),
    ((50.0000, 0.0000, 0.0000), (50.0000, -1.0000, 2.0000), 2.3669),
    ((50.0000, -1.0000, 2.0000), (50.0000, 0.0000, 0.0000), 2.3669),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0009), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0010), 7.1792),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0011), 7.2195),
    ((50.0000, 2.4900, -0.0010), (50.0000, -2.4900, 0.0012), 7.2195),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0009, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0010, -2.4900), 4.8045),
    ((50.0000, -0.0010, 2.4900), (50.0000, 0.0011, -2.4900), 4.7461),
    ((50.0000, 2.5000, 0.0000), (50.0000, 0.0000, -2.5000), 4.3065),
    ((50.0000, 2.5000, 0.0000), (73.0000, 25.0000, -18.0000), 27.1492),
    ((50.0000, 2.5000, 0.0000), (61.0000, -5.0000, 29.0000), 22.8977),
    ((50.0000, 2.5000, 0.0000), (56.0000, -27.0000, -3.0000), 31.9030),
    ((50.0000, 2.5000, 0.0000), (58.0000, 24.0000, 15.0000), 19.4535),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.1736, 0.5854), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2972, 0.0000), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 1.8634, 0.5757), 1.0000),
    ((50.0000, 2.5000, 0.0000), (50.0000, 3.2592, 0.3350), 1.0000),
    ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
    ((63.0109, -31.0961, -5.8663), (62.8187, -29.7946, -4.0864), 1.2630),
    ((61.2901, 3.7196, -5.3901), (61.4292, 2.2480, -4.9620), 1.8731),
    ((35.0831, -44.1164, 3.7933), (35.0232, -40.0716, 1.5901), 1.8645),
    ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ((36.4612, 47.8580, 18.3852), (36.2715, 50.5065, 21.2231), 1.4146),
    ((90.8027, -2.0831, 1.4410), (91.1528, -1.6435, 0.0447), 1.4441),
    ((90.9257, -0.5406, -0.9208), (88.6381, -0.8985, -0.7239), 1.5381),
    ((6.7747, -0.2908, -2.4247), (5.8714, -0.0985, -2.2286), 0.6377),
    ((2.0776, 0.0795, -1.1350), (0.9033, -0.0636, -0.5514), 0.9082),
]


@pytest.mark.parametrize(("lab1", "lab2", "expected"), SHARMA)
def test_ciede2000_sharma(lab1, lab2, expected):
    assert check_colors.ciede2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)
    assert check_colors.ciede2000(lab2, lab1) == pytest.approx(expected, abs=1e-4)


def test_ciede2000_same_color_is_zero():
    lab = check_colors.hex_to_lab("#0A602D")
    assert check_colors.ciede2000(lab, lab) == pytest.approx(0.0, abs=1e-9)


def test_lab_of_white_and_black():
    assert check_colors.hex_to_lab("#FFFFFF") == pytest.approx((100.0, 0.0, 0.0), abs=0.01)
    assert check_colors.hex_to_lab("#000000") == pytest.approx((0.0, 0.0, 0.0), abs=0.01)


def test_contrast_ratio():
    assert check_colors.contrast_ratio("#FFFFFF", "#000000") == pytest.approx(21.0)
    assert check_colors.contrast_ratio("#777777", "#777777") == pytest.approx(1.0)
    assert check_colors.contrast_ratio("#FFF", "#000") == pytest.approx(21.0)


@pytest.mark.parametrize("kind", ["deuteranopi", "protanopi"])
def test_machado_keeps_grays(kind):
    for gray in ("#000000", "#808080", "#FFFFFF"):
        assert check_colors.simulate(gray, kind) == gray


def test_machado_red_green_confusion():
    # Rød og grøn ligger tæt for deuteranoper, langt fra hinanden for normalsynede
    normal = check_colors.delta_e_hex("#D62728", "#2CA02C")
    deut = check_colors.delta_e_hex(
        check_colors.simulate("#D62728", "deuteranopi"), check_colors.simulate("#2CA02C", "deuteranopi")
    )
    assert deut < normal / 2


def _write_categories(path: Path, rows: list[tuple[str, str, str]]) -> Path:
    data = [
        {"id": cid, "name": cid, "short": cid, "color": c, "color_dark": cd, "icon": "x", "help": "x"}
        for cid, c, cd in rows
    ]
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def test_check_colors_main_ok_and_fail(tmp_path, capsys):
    good = _write_categories(
        tmp_path / "good.yaml",
        [("nyhedsmedie", "#1F5FA8", "#6FA8E8"), ("organisation", "#B35C00", "#F0A048")],
    )
    assert check_colors.main(["--file", str(good)]) == 0
    bad = _write_categories(
        tmp_path / "bad.yaml",
        [("nyhedsmedie", "#FFFF00", "#6FA8E8"), ("organisation", "#B35C00", "#20201F")],
    )
    assert check_colors.main(["--file", str(bad)]) == 1
    out = capsys.readouterr().out
    assert "FEJL" in out


def test_check_colors_strict(tmp_path):
    close = _write_categories(
        tmp_path / "close.yaml",
        [("nyhedsmedie", "#1F5FA8", "#6FA8E8"), ("eu_norden", "#2058A8", "#70A0E8")],
    )
    assert check_colors.main(["--file", str(close)]) == 0
    assert check_colors.main(["--file", str(close), "--strict"]) == 1


# ── import_csv: slug ────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Århus Kommune", "aarhus-kommune"),
        ("Københavns Kommune", "koebenhavns-kommune"),
        ("Grøn Omstilling & Co.", "groen-omstilling-co"),
        ("ÆØÅ æøå", "aeoeaa-aeoeaa"),
        ("Café Économie", "cafe-economie"),
        ("KL – Kommunernes Landsforening", "kl-kommunernes-landsforening"),
        ("Dansk Affaldsforening (DAF)", "dansk-affaldsforening-daf"),
        ("  ", "kilde"),
        ("3F", "3f"),
    ],
)
def test_slugify(name, slug):
    assert import_csv.slugify(name) == slug


def test_slugify_long_name_and_valid_id():
    s = import_csv.slugify("Den Selvejende Institution for Bæredygtig Affaldshåndtering i Region Syddanmark")
    assert len(s) <= import_csv.SLUG_MAX
    assert not s.endswith("-")
    assert import_csv.re.match(r"^[a-z0-9][a-z0-9-]*$", s)


def test_unique_id():
    assert import_csv.unique_id("arc", {"kraka"}) == "arc"
    assert import_csv.unique_id("arc", {"arc", "arc-2"}) == "arc-3"


def test_host_of():
    assert import_csv.host_of("https://WWW.Renosyd.dk:443/om") == "renosyd.dk"
    assert import_csv.host_of("renosyd.dk") == "renosyd.dk"


def test_resolve_category():
    table = import_csv.category_table()
    assert import_csv.resolve_category("Kommune og affaldsselskab", table) == "kommunal"
    assert import_csv.resolve_category("Tænketank/NGO", table) == "taenketank"
    assert import_csv.resolve_category("eu_norden", table) == "eu_norden"
    assert import_csv.resolve_category("Kommune", table) == "kommunal"
    assert import_csv.resolve_category("noget helt andet", table) is None
    assert import_csv.resolve_category("", table) is None


# ── import_csv: kørsel mod en tmp sources.yaml ──────────────

SOURCES = """\
# Kilderegister (test)
- id: arc
  name: ARC
  category: kommunal
  homepage: https://www.a-r-c.dk/
  feeds: https://www.a-r-c.dk/feed/
  basis: offentlig
  checked: 2026-10-01

- id: kraka
  name: Kraka
  category: taenketank
  homepage: https://kraka.dk/
  feeds: [https://kraka.dk/rss]
  basis: organisation
  status: aktiv     # tjekket
  checked: 2026-10-01

- id: google-news
  name: Google News
  category: nyhedsmedie
  homepage: https://news.google.com/
  method: search
  feeds: ["https://news.google.com/rss/search?q={q}"]
  basis: redaktionelt
  checked: 2026-10-01

- id: refa
  name: REFA
  category: kommunal
  homepage: https://refa.dk/
  feeds: [https://refa.dk/feed]
  status: planlagt
"""

CSV = """\
navn;url;kategori;note
ARC;https://a-r-c.dk/nyheder;Kommunal;
Renosyd;renosyd.dk;Kommune og affaldsselskab;Fra listen
Grøn Omstilling;https://www.groen-omstilling.dk;;
Dansk Affaldsforening;https://danskaffaldsforening.dk;Branche;Interesse: varetager medlemmer
Renosyd igen;https://www.renosyd.dk/om;kommunal;
Uden url;;fagmedie;
Ukendt;https://ukendt.dk;Forsyningsselskab;
"""

NOW = "2026-10-07T10:00:00Z"


def _setup(tmp_path: Path, csv_text: str = CSV, sources: str = SOURCES) -> tuple[Path, Path]:
    src = tmp_path / "sources.yaml"
    src.write_bytes(sources.encode("utf-8"))
    csv_path = tmp_path / "liste.csv"
    csv_path.write_bytes(csv_text.encode("utf-8"))
    return src, csv_path


def test_import_dry_run(tmp_path, capsys):
    src, csv_path = _setup(tmp_path)
    before = src.read_bytes()
    rc = import_csv.main([str(csv_path), "--sources", str(src), "--dry-run", "--now", NOW])
    assert rc == 0
    assert src.read_bytes() == before
    out = capsys.readouterr().out
    assert "+ renosyd" in out
    assert "+ groen-omstilling" in out
    assert "+ dansk-affaldsforening" in out
    assert "arc (aktiv)" in out
    assert "række 6: Renosyd igen har samme vært som række 3" in out
    assert "række 7: url mangler" in out
    assert "+# ── Importeret 2026-10-07 ──" in out
    assert "Tørkørsel" in out


def test_import_appends_without_reformatting(tmp_path):
    src, csv_path = _setup(tmp_path)
    rc = import_csv.main([str(csv_path), "--sources", str(src), "--now", NOW])
    assert rc == 0
    text = src.read_text(encoding="utf-8")
    assert text.startswith(SOURCES)
    assert "# ── Importeret 2026-10-07 ──" in text
    entries = yaml.safe_load(text)
    for e in entries:
        Source.model_validate(e)
    new = {e["id"]: e for e in entries[4:]}
    assert set(new) == {"renosyd", "groen-omstilling", "dansk-affaldsforening", "ukendt"}
    assert all(e["status"] == "kandidat" for e in new.values())
    assert new["renosyd"]["homepage"] == "https://renosyd.dk"
    assert new["renosyd"]["category"] == "kommunal"
    assert new["renosyd"]["note"] == "Fra listen"
    assert new["dansk-affaldsforening"]["category"] == "organisation"
    assert new["groen-omstilling"]["category"] == "nyhedsmedie"
    assert "category: nyhedsmedie  # kategori mangler i CSV" in text
    assert "# ukendt kategori i CSV: Forsyningsselskab" in text
    # Anden kørsel: alt findes nu, intet ændres
    rc = import_csv.main([str(csv_path), "--sources", str(src), "--now", NOW])
    assert rc == 0
    assert src.read_text(encoding="utf-8") == text


def test_import_replace_changes_only_status_line(tmp_path):
    src, csv_path = _setup(tmp_path, csv_text="navn,url\nARC,https://www.a-r-c.dk/\n")
    rc = import_csv.main([str(csv_path), "--sources", str(src), "--replace", "--now", NOW])
    assert rc == 0
    new_lines = src.read_text(encoding="utf-8").splitlines()
    old_lines = SOURCES.splitlines()
    assert len(new_lines) == len(old_lines)
    changed = [(o, n) for o, n in zip(old_lines, new_lines, strict=True) if o != n]
    assert changed == [("  status: aktiv     # tjekket", "  status: pause     # tjekket")]
    by_id = {e["id"]: e for e in yaml.safe_load(src.read_text(encoding="utf-8"))}
    assert by_id["kraka"]["status"] == "pause"
    assert by_id["google-news"].get("status", "aktiv") == "aktiv"
    assert by_id["refa"]["status"] == "planlagt"


def test_import_replace_inserts_missing_status(tmp_path, capsys):
    src, csv_path = _setup(tmp_path, csv_text="navn,url\nKraka,kraka.dk\n")
    rc = import_csv.main([str(csv_path), "--sources", str(src), "--replace", "--dry-run", "--now", NOW])
    assert rc == 0
    assert src.read_text(encoding="utf-8") == SOURCES
    assert "+  status: pause" in capsys.readouterr().out
    rc = import_csv.main([str(csv_path), "--sources", str(src), "--replace", "--now", NOW])
    assert rc == 0
    text = src.read_text(encoding="utf-8")
    assert "- id: arc\n  status: pause\n  name: ARC\n" in text
    by_id = {e["id"]: e for e in yaml.safe_load(text)}
    assert by_id["arc"]["status"] == "pause"
    assert by_id["kraka"]["status"] == "aktiv"


def test_import_keeps_crlf(tmp_path):
    src, csv_path = _setup(tmp_path, sources=SOURCES.replace("\n", "\r\n"))
    rc = import_csv.main([str(csv_path), "--sources", str(src), "--now", NOW])
    assert rc == 0
    raw = src.read_bytes()
    assert raw.startswith(SOURCES.replace("\n", "\r\n").encode("utf-8"))
    assert b"\n" not in raw.replace(b"\r\n", b"")


def test_import_missing_column(tmp_path, capsys):
    src, csv_path = _setup(tmp_path, csv_text="navn;kategori\nARC;kommunal\n")
    assert import_csv.main([str(csv_path), "--sources", str(src), "--dry-run"]) == 1
    assert "mangler kolonne: url" in capsys.readouterr().err


def test_import_cp1252_csv(tmp_path, capsys):
    src, csv_path = _setup(tmp_path)
    csv_path.write_bytes("navn;url\nGrøn Ø;https://groen-oe.dk\n".encode("cp1252"))
    assert import_csv.main([str(csv_path), "--sources", str(src), "--dry-run", "--now", NOW]) == 0
    out = capsys.readouterr().out
    assert "+ groen-oe" in out
    assert "Windows-1252" in out


# ── find_feed (falsk HTTP-session) ──────────────────────────

RSS = b"""<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0"><channel><title>Testkilde</title>
<item><title>Nyt om affaldsgebyrer</title><link>https://x.dk/a</link>
<pubDate>Mon, 06 Oct 2026 08:00:00 GMT</pubDate></item>
<item><title>Genbrugspladsen udvider</title><link>https://x.dk/b</link>
<pubDate>Tue, 07 Oct 2026 06:30:00 GMT</pubDate></item>
</channel></rss>"""

HOME = b"""<!doctype html><html><head>
<link rel="stylesheet" href="/style.css">
<link rel="alternate" type="application/rss+xml" title="Nyheder" href="/feed/">
<link rel="Alternate" type="application/atom+xml; charset=utf-8" href="https://x.dk/atom/">
<link rel="alternate" hreflang="en" href="/en/">
</head><body>Forside</body></html>"""

ROBOTS = b"""User-agent: GPTBot
Disallow: /

User-agent: CCBot
Disallow: /

User-agent: *
Disallow: /rss
Sitemap: https://x.dk/sitemap_index.xml
"""

SITEMAP_INDEX = b"""<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://x.dk/post-sitemap.xml</loc><lastmod>2026-10-05T10:00:00+00:00</lastmod></sitemap>
<sitemap><loc>https://x.dk/page-sitemap.xml</loc><lastmod>2026-09-01</lastmod></sitemap>
</sitemapindex>"""

URLSET = b"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://x.dk/a</loc><lastmod>2026-10-06</lastmod></url>
<url><loc>https://x.dk/b</loc></url>
<url><loc>https://x.dk/c</loc><lastmod>2026-10-07T09:00:00Z</lastmod></url>
</urlset>"""


class FakeResponse:
    def __init__(self, status: int, content: bytes = b"", ctype: str = "", location: str | None = None):
        self.status_code = status
        self.content = content
        self.headers = {"Content-Type": ctype}
        if location:
            self.headers["Location"] = location


class FakeSession:
    def __init__(self, routes: dict[str, FakeResponse]):
        self.routes = routes
        self.requested: list[str] = []
        self.user_agents: set[str] = set()

    def get(self, url, headers=None, timeout=None, allow_redirects=True):
        assert allow_redirects is False
        self.requested.append(url)
        self.user_agents.add((headers or {}).get("User-Agent", ""))
        return self.routes.get(url, FakeResponse(404, b"not found", "text/html"))


class FakeClock:
    def __init__(self):
        self.t = 1000.0
        self.waits: list[float] = []

    def clock(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.waits.append(s)
        self.t += s


def test_feed_links():
    links = find_feed.feed_links(HOME, "https://x.dk/")
    assert links == ["https://x.dk/feed/", "https://x.dk/atom/"]
    based = b'<html><head><base href="https://cdn.x.dk/s/"><link rel="alternate" type="application/rss+xml" href="rss.xml"></head></html>'
    assert find_feed.feed_links(based, "https://x.dk/") == ["https://cdn.x.dk/s/rss.xml"]
    assert find_feed.feed_links(b"", "https://x.dk/") == []


def test_guess_urls():
    urls = find_feed.guess_urls("https://x.dk/miljoe")
    assert urls[0] == "https://x.dk/miljoe/feed/"
    assert "https://x.dk/feed/" in urls and "https://x.dk/atom.xml" in urls
    assert len(urls) == len(set(urls)) == 10
    assert find_feed.guess_urls("https://x.dk/") == [
        "https://x.dk/feed/",
        "https://x.dk/rss",
        "https://x.dk/rss.xml",
        "https://x.dk/feed",
        "https://x.dk/atom.xml",
    ]


def test_summarize_feed_and_sitemap():
    info = find_feed.summarize_feed(RSS)
    assert info["items"] == 2 and info["title"] == "Testkilde" and info["kind"] == "rss20"
    assert find_feed.iso(info["newest"]) == "2026-10-07T06:30:00Z"
    assert find_feed.summarize_feed(HOME) is None

    sm = find_feed.summarize_sitemap(URLSET)
    assert sm["kind"] == "urlset" and sm["entries"] == 3
    assert find_feed.iso(sm["newest"]) == "2026-10-07T09:00:00Z"
    idx = find_feed.summarize_sitemap(gzip.compress(SITEMAP_INDEX), "https://x.dk/s.xml.gz")
    assert idx["kind"] == "sitemapindex" and idx["entries"] == 2
    assert find_feed.summarize_sitemap(HOME) is None


def test_discover_respects_robots_and_pauses(capsys):
    session = FakeSession(
        {
            "https://x.dk/robots.txt": FakeResponse(200, ROBOTS, "text/plain"),
            "https://x.dk/": FakeResponse(200, HOME, "text/html; charset=utf-8"),
            "https://x.dk/feed/": FakeResponse(200, RSS, "application/rss+xml"),
            "https://x.dk/feed": FakeResponse(301, location="https://x.dk/feed/"),
            "https://x.dk/sitemap_index.xml": FakeResponse(200, SITEMAP_INDEX, "application/xml"),
            "https://x.dk/sitemap.xml": FakeResponse(200, URLSET, "application/xml"),
        }
    )
    clock = FakeClock()
    ua = "Affaldsfeed/0.1 (+https://github.com/SimNyborg/affaldsfeed)"
    client = find_feed.Client(ua, session=session, sleep=clock.sleep, clock=clock.clock)
    report = find_feed.discover("x.dk", client)

    assert report["robots"]["status"] == "fundet"
    assert report["robots"]["ai_blocked"] == ["GPTBot", "CCBot"]
    assert report["robots"]["allowed"] is True
    feeds = {r["url"]: r for r in report["feeds"]}
    assert feeds["https://x.dk/feed/"]["ok"] and feeds["https://x.dk/feed/"]["found_via"] == "link-tag"
    assert feeds["https://x.dk/feed/"]["items"] == 2
    assert feeds["https://x.dk/rss"]["status"] == find_feed.BLOCKED
    assert feeds["https://x.dk/feed"]["same_as"] == "https://x.dk/feed/"
    assert not feeds["https://x.dk/atom/"]["ok"]
    # robots.txt-forbudte adresser hentes aldrig, og hver URL hentes én gang
    assert "https://x.dk/rss" not in session.requested
    assert session.requested.count("https://x.dk/feed/") == 2  # direkte + efter omdirigering fra /feed
    assert session.user_agents == {ua}
    # mindst 2 sek. mellem kald til samme vært
    assert clock.waits and all(w == pytest.approx(2.0) for w in clock.waits)
    assert len(clock.waits) == len(session.requested) - 1
    maps = {r["url"]: r for r in report["sitemaps"]}
    assert maps["https://x.dk/sitemap_index.xml"]["kind"] == "sitemapindex"
    assert maps["https://x.dk/sitemap.xml"]["entries"] == 3

    find_feed.print_report(report, ua)
    out = capsys.readouterr().out
    assert "AI-fravalg: GPTBot, CCBot" in out
    assert "feeds: https://x.dk/feed/" in out


def test_discover_robots_unavailable_blocks_everything():
    session = FakeSession({"https://x.dk/robots.txt": FakeResponse(503, b"", "text/html")})
    clock = FakeClock()
    client = find_feed.Client("Affaldsfeed/0.1", session=session, sleep=clock.sleep, clock=clock.clock)
    report = find_feed.discover("https://x.dk/", client)
    assert report["robots"]["status"] == "utilgængelig"
    assert session.requested == ["https://x.dk/robots.txt"]
    assert not any(r["ok"] for r in report["feeds"] + report["sitemaps"])


def test_crawl_delay_is_respected():
    robots = b"User-agent: *\nCrawl-delay: 7\n"
    session = FakeSession(
        {
            "https://x.dk/robots.txt": FakeResponse(200, robots, "text/plain"),
            "https://x.dk/": FakeResponse(200, RSS, "application/rss+xml"),
        }
    )
    clock = FakeClock()
    client = find_feed.Client("Affaldsfeed/0.1", session=session, sleep=clock.sleep, clock=clock.clock)
    report = find_feed.discover("https://x.dk/", client)
    assert report["feeds"][0]["found_via"] == "input" and report["feeds"][0]["ok"]
    assert all(w == pytest.approx(7.0) for w in clock.waits)
