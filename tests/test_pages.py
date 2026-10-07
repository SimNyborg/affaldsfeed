"""Sitemap, html-lister og sideudtræk (collect/pages.py, KONTRAKTER §5.6). Ingen netværkskald."""

from __future__ import annotations

import argparse
import gzip
import importlib.util
import json
import sys
import time
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from affaldsfeed import fetch as fetchmod
from affaldsfeed import paths, pipeline, store
from affaldsfeed.collect import COLLECTORS, CollectContext, pages
from affaldsfeed.config import load_config, main_check
from affaldsfeed.models import Source
from affaldsfeed.normalize import item_id

FIXTURES = Path(__file__).resolve().parent / "fixtures"
P = FIXTURES / "pages"
REAL_CONFIG = paths.CONFIG_DIR
NOW = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)  # kl. 10.05 i København
HTML = "text/html; charset=utf-8"
XML = "application/xml"
SITEMAP = "https://www.kilde.dk/sitemap.xml"
NEWS = "https://www.kilde.dk/nyheder/"
ART1 = NEWS + "ny-genbrugsplads-aabner"
ART2 = NEWS + "affaldsgebyr-stiger"
ART3 = NEWS + "gammel-nyhed-om-deponi"
ART4 = NEWS + "tekstilaffald-uden-lastmod"
ARTICLES = {
    ART1: (P / "article_jsonld.html", HTML),
    ART2: (P / "article_meta.html", HTML),
    ART3: (P / "article_time.html", HTML),
    ART4: (P / "article_text.html", HTML),
}
LIST = "https://www.kilde.dk/da/nyheder/"
NAMES = ["Kildeforeningen", "kilde.dk", "kilde"]


def _fakes():
    name = "affaldsfeed_test_fakes"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, FIXTURES / "fakes.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


@pytest.fixture(scope="module")
def cfg():
    return load_config(REAL_CONFIG)


def src(**kw) -> Source:
    data = {
        "id": "kilde",
        "name": "Kildeforeningen",
        "category": "organisation",
        "homepage": "https://www.kilde.dk",
        "method": "sitemap",
        "feeds": [SITEMAP],
        "match": "/nyheder/",
        "basis": "organisation",
        "checked": date(2026, 10, 7),
    }
    data.update(kw)
    return Source(**data)


def html_src(**kw) -> Source:
    return src(**{"id": "liste", "method": "html", "feeds": [LIST], "select": "ul.news li.item", **kw})


def ctx(cfg, *, first_run: bool = False, seen: dict | None = None, last_ok: date | None = None) -> CollectContext:
    return CollectContext(
        config=cfg,
        sources=[],
        now=NOW,
        publisher_lookup={},
        conditional=not first_run,
        first_run=first_run,
        last_ok=last_ok,
        seen={} if seen is None else seen,
    )


def fetcher(routes: dict, etags: bool = False, http_cache: dict | None = None):
    cache = {} if http_cache is None else http_cache
    return _fakes().make_fetcher_class(routes, etags=etags)(None, cache, {}, NOW)


def routes(**extra) -> dict:
    return {SITEMAP: (P / "urlset.xml", XML), **ARTICLES, **extra}


def urls_called(f, skip: int = 1) -> list[str]:
    """Hentede URL'er efter de første skip (sitemap/liste)."""
    return [u for u, _ in f.calls[skip:]]


SM_NS = "http://www.sitemaps.org/schemas/sitemap/0.9"


def urlset(rows: list[tuple[str, str | None]]) -> bytes:
    body = "".join(
        f"<url><loc>{u}</loc>" + (f"<lastmod>{m}</lastmod>" if m else "") + "</url>" for u, m in rows
    )
    return f'<?xml version="1.0"?><urlset xmlns="{SM_NS}">{body}</urlset>'.encode()


def index(rows: list[tuple[str, str]]) -> bytes:
    body = "".join(f"<sitemap><loc>{u}</loc><lastmod>{m}</lastmod></sitemap>" for u, m in rows)
    return f'<sitemapindex xmlns="{SM_NS}">{body}</sitemapindex>'.encode()


def page(head: str = "", body: str = "") -> bytes:
    html = f'<!DOCTYPE html><html lang="da"><head><meta charset="utf-8">{head}</head>'
    return f"{html}<body>{body}</body></html>".encode()


def diag(res) -> str:
    return "\n".join(res.diagnostics)


# ── Sideudtræk ──────────────────────────────────────────────


def test_extract_jsonld_graph_prefers_article_over_webpage_and_meta():
    p = pages.extract_page((P / "article_jsonld.html").read_bytes(), ART1, HTML, now=NOW, names=NAMES)
    assert p.title == "Ny genbrugsplads åbner i Nordby"  # og:title
    assert p.published == datetime(2026, 10, 7, 5, 30, tzinfo=UTC)  # NewsArticle i @graph
    assert p.date_quality == "kilde"
    assert p.teaser == "Den nye plads har åbent alle ugens dage & tager imod 30 fraktioner."  # og:description


def test_extract_meta_published_time_and_h1_in_article():
    p = pages.extract_page((P / "article_meta.html").read_bytes(), ART2, HTML, now=NOW, names=NAMES)
    assert p.title == "Affaldsgebyret stiger i 2027"  # h1 i article, ikke logoets h1 i headeren
    assert p.published == datetime(2026, 10, 5, 12, 32, tzinfo=UTC) and p.date_quality == "kilde"
    assert p.teaser == "Gebyret for husstande stiger med 4 procent."  # meta description


def test_extract_time_in_article_and_title_tail():
    p = pages.extract_page((P / "article_time.html").read_bytes(), ART3, HTML, now=NOW, names=NAMES)
    assert p.title == "Gammel nyhed om deponi"  # <title> uden " – Kildeforeningen"
    assert p.published == datetime(
        2026, 9, 28, 7, 15, tzinfo=UTC
    )  # <time> i article, dansk tid, ikke sidebaren
    assert p.date_quality == "kilde" and p.teaser == ""


def test_extract_danish_text_date_with_time_in_main():
    p = pages.extract_page((P / "article_text.html").read_bytes(), ART4, HTML, now=NOW, names=NAMES)
    assert p.title == "Kommunen åbner for tekstilaffald"  # og:title er kun sidens navn, så h1 bruges
    assert p.published == datetime(2026, 10, 6, 11, 45, tzinfo=UTC) and p.date_quality == "kilde"


@pytest.mark.parametrize(
    ("url", "head", "body", "published", "quality"),
    [
        pytest.param(
            ART1,
            '<script type="application/ld+json">[{"@type": "Organization", "name": "X"}, '
            '{"@type": "BlogPosting", "datePublished": "2026-10-06T09:00:00Z"}]</script>',
            "",
            datetime(2026, 10, 6, 9, 0, tzinfo=UTC),
            "kilde",
            id="jsonld-liste",
        ),
        pytest.param(
            ART1,
            '<script type="application/ld+json"><!-- {"@type": "Article", "datePublished": "2026-10-06"} -->'
            "</script>",
            "",
            datetime(2026, 10, 5, 22, 0, tzinfo=UTC),
            "liste",
            id="jsonld-kun-dato",
        ),
        pytest.param(
            ART1,
            '<script type="application/ld+json">{ugyldig json</script>'
            '<meta property="article:published_time" content="2026-10-06T08:00:00Z">',
            "",
            datetime(2026, 10, 6, 8, 0, tzinfo=UTC),
            "kilde",
            id="ugyldig-jsonld",
        ),
        pytest.param(
            ART1,
            "",
            '<header><time datetime="2026-10-06T12:00:00+02:00">I går</time></header>',
            datetime(2026, 10, 6, 10, 0, tzinfo=UTC),
            "kilde",
            id="time-i-header",
        ),
        pytest.param(
            ART1,
            '<meta name="DC.date" content="2026-10-05">',
            "",
            datetime(2026, 10, 4, 22, 0, tzinfo=UTC),
            "liste",
            id="dc-date",
        ),
        pytest.param(
            ART1,
            '<meta name="publication-date" content="2026-10-05T08:00:00+02:00">',
            "",
            datetime(2026, 10, 5, 6, 0, tzinfo=UTC),
            "kilde",
            id="publication-date",
        ),
        pytest.param(
            "https://www.kilde.dk/nyheder/2026/10/05/ny-plads",
            "",
            "",
            datetime(2026, 10, 4, 22, 0, tzinfo=UTC),
            "url",
            id="url-sti",
        ),
        pytest.param(
            "https://www.kilde.dk/nyheder/2026-10-05-ny-plads",
            "",
            "",
            datetime(2026, 10, 4, 22, 0, tzinfo=UTC),
            "url",
            id="url-iso",
        ),
        pytest.param(
            ART1,
            "",
            "<main><h1>X</h1><p>Opdateret 7. okt. 2026</p></main>",
            datetime(2026, 10, 6, 22, 0, tzinfo=UTC),
            "liste",
            id="tekst-okt",
        ),
        pytest.param(
            ART1,
            "",
            "<article><p>Dato: 07.10.2026</p></article>",
            datetime(2026, 10, 6, 22, 0, tzinfo=UTC),
            "liste",
            id="tekst-tal",
        ),
        pytest.param(
            ART1,
            "",
            "<main><h1>X</h1></main><footer>7. oktober 2026</footer>",
            None,
            "fundet",
            id="tekst-uden-for-main",
        ),
        pytest.param(
            "https://www.kilde.dk/nyheder/2026/10/05/x",
            '<script type="application/ld+json">'
            '{"@type": "NewsArticle", "datePublished": "2026-10-08T12:00:00Z"}</script>',
            "",
            datetime(2026, 10, 4, 22, 0, tzinfo=UTC),
            "url",
            id="fremtid-ignoreres",
        ),
        pytest.param(
            ART1,
            '<meta property="article:published_time" content="2026-10-07T10:00:00Z">',
            "",
            datetime(2026, 10, 7, 10, 0, tzinfo=UTC),
            "kilde",
            id="under-2-t-i-fremtiden",
        ),
        pytest.param(
            ART1,
            '<script type="application/ld+json">{"@type": "Article", "datePublished": "0001-01-01"}</script>',
            "",
            None,
            "fundet",
            id="aar-1",
        ),
        pytest.param(
            ART1,
            "",
            "<main><h1>Titel</h1><p>Brødtekst</p><section><article><h3>Relateret</h3>"
            '<time datetime="2026-01-05">5. jan.</time></article></section></main>',
            None,
            "fundet",
            id="relateret-artikel-i-main",
        ),
        pytest.param(
            ART1,
            "",
            '<aside><time datetime="2026-10-01T10:00:00Z">1. okt.</time></aside><main><h1>Titel</h1></main>',
            None,
            "fundet",
            id="sidebar",
        ),
        pytest.param(
            ART1,
            "",
            "<header><h1>Kildeforeningen</h1></header>"
            '<article><h2>Relateret</h2><time datetime="2026-10-01T08:00:00Z"></time></article>'
            '<article><h1>Titel</h1><time datetime="2026-10-06T08:00:00Z"></time></article>',
            datetime(2026, 10, 6, 8, 0, tzinfo=UTC),
            "kilde",
            id="artiklen-med-h1",
        ),
        pytest.param(
            ART1,
            "",
            '<div class="indhold"><h1>Titel</h1>'
            '<p><time datetime="2026-10-06T08:00:00Z">I går</time></p></div>',
            datetime(2026, 10, 6, 8, 0, tzinfo=UTC),
            "kilde",
            id="side-uden-article-og-main",
        ),
        # h1 står i <main>, og brødteksten med sin <time> i main's eneste <article> (uden egen overskrift)
        pytest.param(
            ART1,
            "",
            '<main><h1>Nye regler for tekstiler</h1><article><p class="meta">'
            '<time datetime="2026-10-06T09:00:00+02:00">6. okt.</time></p><p>Brødtekst</p></article></main>',
            datetime(2026, 10, 6, 7, 0, tzinfo=UTC),
            "kilde",
            id="time-i-eneste-article-i-main",
        ),
        pytest.param(
            ART1,
            "",
            '<main><div class="page-header"><h1>Ny genbrugsplads</h1></div><article><p>'
            '<time datetime="2026-10-06T08:00:00Z">I går</time></p><p>Tekst</p></article></main>',
            datetime(2026, 10, 6, 8, 0, tzinfo=UTC),
            "kilde",
            id="time-i-article-efter-sidehoved",
        ),
        # Meta-dato i RFC 822 med "Sep" (også et dansk månedsnavn): tidszonen GMT gælder, ikke dansk tid
        pytest.param(
            ART1,
            '<meta name="date" content="Mon, 07 Sep 2026 22:30:00 GMT">',
            "",
            datetime(2026, 9, 7, 22, 30, tzinfo=UTC),
            "kilde",
            id="rfc822-sep-gmt",
        ),
        # ISO med mellemrum før tidszonen (Ruby/PHP): aldrig dag og måned byttet om
        pytest.param(
            ART1,
            '<meta property="article:published_time" content="2026-10-06 09:00:00 +0200">',
            "",
            datetime(2026, 10, 6, 7, 0, tzinfo=UTC),
            "kilde",
            id="iso-med-mellemrum-foer-tidszone",
        ),
        # En ugyldig tidszone (+24:00) giver ingen dato og ingen undtagelse; næste kilde til en dato bruges
        pytest.param(
            ART1,
            '<script type="application/ld+json">{"@type": "NewsArticle", '
            '"datePublished": "2026-10-07T08:00:00+24:00"}</script>'
            '<meta name="DC.date" content="2026-10-05">',
            "",
            datetime(2026, 10, 4, 22, 0, tzinfo=UTC),
            "liste",
            id="ugyldig-tidszone",
        ),
    ],
)
def test_extract_date_variants(url, head, body, published, quality):
    p = pages.extract_page(page(head, body), url, HTML, now=NOW)
    assert (p.published, p.date_quality) == (published, quality)


@pytest.mark.parametrize(
    ("body", "published"),
    [
        # En tidligere henvisning før byline-datoen: "Publiceret" vinder
        (
            "<main><h1>Status på madaffald</h1><p>Siden 1. april 2025 har alle husstande sorteret madaffald."
            "</p><p>Publiceret 6. oktober 2026</p></main>",
            datetime(2026, 10, 5, 22, 0, tzinfo=UTC),
        ),
        # En fremtidig ikrafttrædelse før byline-datoen springes over, i stedet for at opgive
        (
            "<main><h1>Nye regler for tekstiler</h1><p>Fra 1. januar 2027 skal alle sortere tekstiler. "
            "Publiceret 6. oktober 2026</p></main>",
            datetime(2026, 10, 5, 22, 0, tzinfo=UTC),
        ),
        # Uden etiket: den seneste mulige dato (en for gammel dato ville få artiklen afvist)
        (
            "<main><h1>Status på madaffald</h1><p>Siden 1. april 2025 har alle husstande sorteret madaffald."
            "</p><p>6. oktober 2026</p></main>",
            datetime(2026, 10, 5, 22, 0, tzinfo=UTC),
        ),
        ("<main><h1>Nye regler</h1><p>Fra 1. januar 2027 skal alle sortere tekstiler.</p></main>", None),
    ],
)
def test_text_date_skips_future_dates_and_prefers_publication_label(body, published):
    assert pages.extract_page(page(body=body), ART1, HTML, now=NOW).published == published


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-10-07 10:00:00 +0200", (datetime(2026, 10, 7, 8, 0, tzinfo=UTC), True)),  # Ruby, PHP
        ("2026-10-07 09:00:00 +02:00", (datetime(2026, 10, 7, 7, 0, tzinfo=UTC), True)),
        ("2026-10-06 14:30:00 UTC", (datetime(2026, 10, 6, 14, 30, tzinfo=UTC), True)),  # Rails
        ("2026-10-05T09:00:00 CEST", (datetime(2026, 10, 5, 7, 0, tzinfo=UTC), True)),
        ("2026-10-07T10:00:00 GMT+0200", (datetime(2026, 10, 7, 8, 0, tzinfo=UTC), True)),
        ("2026-10-07T10:00:00.000+0200", (datetime(2026, 10, 7, 8, 0, tzinfo=UTC), True)),
        ("2026/10/05 10:00", (datetime(2026, 10, 5, 8, 0, tzinfo=UTC), True)),
        ("20261005T101500Z", (datetime(2026, 10, 5, 10, 15, tzinfo=UTC), True)),
        ("2026-10-05", (datetime(2026, 10, 4, 22, 0, tzinfo=UTC), False)),
        ("Tue, 06 Oct 2026 10:00:00 +0200", (datetime(2026, 10, 6, 8, 0, tzinfo=UTC), True)),
        ("Mon, 07 Sep 2026 22:30:00 GMT", (datetime(2026, 9, 7, 22, 30, tzinfo=UTC), True)),
        ("05.10.2026", (datetime(2026, 10, 4, 22, 0, tzinfo=UTC), False)),
        ("5. okt. 2026 kl. 14.32", (datetime(2026, 10, 5, 12, 32, tzinfo=UTC), True)),
        # Ugyldige værdier og tidszoner giver None, aldrig en undtagelse eller et gæt
        ("2026-10-07T08:00:00+24:00", None),
        ("2026-10-07T08:00:00+2400", None),
        ("2026-10-07T08:00:00 GMT+24", None),
        ("2026-10-07T08:00:00 PST", None),
        ("2026-10-07T24:00:00", None),
        ("2026-13-01", None),
        ("0001-01-01", None),
        ("October 7, 2026", None),  # engelske månedsnavne kun for engelske kilder
    ],
)
def test_parse_date_never_guesses_day_first(value, expected):
    assert pages.parse_date(value) == expected


def test_english_month_names_only_for_english_sources():
    assert pages.parse_date("October 7, 2026", "en") == (datetime(2026, 10, 6, 22, 0, tzinfo=UTC), False)
    assert pages.parse_date("7th of October 2026", "en") == (datetime(2026, 10, 6, 22, 0, tzinfo=UTC), False)
    assert pages.parse_date("Oct. 6, 2026, 2:15 PM", "en") == (datetime(2026, 10, 6, 12, 15, tzinfo=UTC), True)
    doc = page(body="<main><h1>New rules for textiles</h1><p>Published 6 October 2026</p></main>")
    assert pages.extract_page(doc, ART1, HTML, now=NOW, lang="en").published == datetime(
        2026, 10, 5, 22, 0, tzinfo=UTC
    )
    assert pages.extract_page(doc, ART1, HTML, now=NOW).published is None  # dansk kilde: intet gæt


def test_extract_title_candidates():
    og_is_site = page(
        '<meta property="og:title" content="Kildeforeningen"><title>X | Kildeforeningen</title>',
        "<article><h1>Nye takster for storskrald</h1></article>",
    )
    assert (
        pages.extract_page(og_is_site, ART1, HTML, now=NOW, names=NAMES).title == "Nye takster for storskrald"
    )
    for sep in ("|", "-", "–"):
        doc = page(f"<title>Nye takster for storskrald {sep} Kildeforeningen</title>")
        assert pages.extract_page(doc, ART1, HTML, now=NOW, names=NAMES).title == "Nye takster for storskrald"
    keep = page("<title>Nye takster – se hvad de betyder for dig</title>")
    assert pages.extract_page(keep, ART1, HTML, now=NOW).title == "Nye takster – se hvad de betyder for dig"
    assert pages.extract_page(page(), ART1, HTML, now=NOW).title == ""


def test_extract_skips_non_html():
    pdf = b"%PDF-1.7\n1 0 obj\n"
    assert pages.extract_page(pdf, ART1, "application/pdf", now=NOW) is None
    assert pages.extract_page(pdf, ART1, None, now=NOW) is None  # ingen content-type: PDF genkendes
    assert pages.extract_page(page("<title>Hej verden</title>"), ART1, None, now=NOW).title == "Hej verden"
    assert pages.extract_page(b'{"a": 1}', ART1, "application/json", now=NOW) is None
    assert pages.extract_page(b"", ART1, HTML, now=NOW) is None


def test_extract_decodes_charset_correctly():
    latin1 = (
        '<html><head><meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1">'
        "<title>Ærø får ny affaldsløsning</title></head><body></body></html>"
    ).encode("latin-1")
    assert pages.extract_page(latin1, ART1, "text/html", now=NOW).title == "Ærø får ny affaldsløsning"
    # Header siger latin-1, men siden er utf-8 (en hyppig fejl)
    utf8 = "<html><head><title>Ærø får ny affaldsløsning</title></head></html>".encode()
    assert (
        pages.extract_page(utf8, ART1, "text/html; charset=ISO-8859-1", now=NOW).title
        == "Ærø får ny affaldsløsning"
    )
    # Intet erklæret og ikke gyldig utf-8: windows-1252
    cp1252 = "<html><head><title>Genbrug – det nye sort</title></head></html>".encode("cp1252")
    assert pages.extract_page(cp1252, ART1, "text/html", now=NOW).title == "Genbrug – det nye sort"
    assert pages.html_charset(b"\xef\xbb\xbf<html>", None) == "utf-8-sig"
    assert pages.html_charset(b"<html>", "text/html; charset=bogus") == "utf-8"


def test_declared_charset_is_kept_despite_an_invalid_byte():
    # En utf-8-side, hvor CMS'et har afkortet meta description midt i et "ø"
    body = (
        '<html><head><meta charset="utf-8"><title>Ny affaldsløsning på genbrugspladsen</title>'
        '<meta name="description" content="Kommunen indfører en ny affaldsl'
    ).encode() + "ø".encode()[:1] + b'"></head><body></body></html>'
    for ctype in ("text/html; charset=utf-8", "text/html", None):
        p = pages.extract_page(body, ART1, ctype, now=NOW)
        assert p.title == "Ny affaldsløsning på genbrugspladsen"
        assert p.teaser.startswith("Kommunen indfører en ny affaldsl")
    # Erklæret latin-1 læses som windows-1252, som i browsere (– er 0x96)
    latin = "<title>Genbrug – det nye sort</title>".encode("cp1252")
    p = pages.extract_page(latin, ART1, "text/html; charset=iso-8859-1", now=NOW)
    assert p.title == "Genbrug – det nye sort"
    # windows-1252 kun som sidste udvej: intet erklæret og ikke gyldig utf-8
    assert pages.html_charset(latin, "text/html") == "cp1252"


@pytest.mark.parametrize("charset", ["hex", "base64", "rot13", "zip", "uu", "idna", "unicode_escape", "utf-7"])
def test_only_text_charsets_are_accepted(charset):
    doc = f'<html><head><meta charset="{charset}"><title>Ærø får ny affaldsløsning</title></head></html>'.encode()
    assert pages.extract_page(doc, ART1, "text/html", now=NOW).title == "Ærø får ny affaldsløsning"
    p = pages.extract_page(doc, ART1, f"text/html; charset={charset}", now=NOW)
    assert p.title == "Ærø får ny affaldsløsning"


def test_meta_utf16_on_an_ascii_compatible_page_is_utf8():
    doc = '<html><head><meta charset="utf-16"><title>Ærø får ny affaldsløsning</title></head></html>'.encode()
    assert pages.extract_page(doc, ART1, "text/html", now=NOW).title == "Ærø får ny affaldsløsning"
    utf16 = '<html><head><title>Ærø får ny affaldsløsning</title></head></html>'.encode("utf-16")  # med BOM
    assert pages.extract_page(utf16, ART1, "text/html", now=NOW).title == "Ærø får ny affaldsløsning"


def test_parse_date_and_danish_dates():
    assert pages.parse_date("2026-10-07T10:00") == (
        datetime(2026, 10, 7, 8, 0, tzinfo=UTC),
        True,
    )  # dansk tid
    assert pages.parse_date("Wed, 07 Oct 2026 10:00:00 GMT") == (
        datetime(2026, 10, 7, 10, 0, tzinfo=UTC),
        True,
    )
    assert pages.parse_date("2026") is None and pages.parse_date("oktober 2026") is None
    assert pages.danish_date("den 7. oktober 2026 kl. 14.32") == (
        datetime(2026, 10, 7, 12, 32, tzinfo=UTC),
        True,
    )
    assert pages.danish_date("31. juni 2026 eller 1. juli 2026")[0] == datetime(
        2026, 6, 30, 22, 0, tzinfo=UTC
    )
    assert pages.danish_date("Vi henter 10.000 tons i 2026") is None
    # Den næste dato i et interval er ikke et klokkeslæt
    interval = pages.danish_date("Arrangement 07.10.2026 - 08.10.2026")
    assert interval == (datetime(2026, 10, 6, 22, 0, tzinfo=UTC), False)
    # "dato" inde i et andet ord er ingen etiket: den seneste dato vinder
    text = "Skæringsdato 1. september 2026. Nyheden er fra 6. oktober 2026."
    assert pages.text_date(text, NOW) == (datetime(2026, 10, 5, 22, 0, tzinfo=UTC), False)
    assert pages.text_date("Udgivelsesdato: 1. oktober 2026. Opdateret 6. oktober 2026", NOW)[0] == datetime(
        2026, 9, 30, 22, 0, tzinfo=UTC
    )


# ── Sitemap: parsing ────────────────────────────────────────


def test_parse_urlset_cdata_namespace_prefix_and_whitespace():
    sm = pages.parse_sitemap((P / "urlset.xml").read_bytes(), SITEMAP)
    assert sm.kind == "urlset" and len(sm.entries) == 8
    assert sm.entries[0].loc == ART1  # CDATA og whitespace
    assert sm.entries[0].lastmod == datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
    assert sm.entries[1].lastmod == datetime(
        2026, 10, 4, 22, 0, tzinfo=UTC
    )  # dato uden tid = dagen i København
    assert sm.entries[6].lastmod is None
    rel = pages.parse_sitemap(b"<urlset><url><loc> /nyheder/ny plads </loc></url></urlset>", SITEMAP)
    assert rel.entries[0].loc == NEWS + "ny%20plads"


def test_parse_sitemap_rejects_other_content():
    with pytest.raises(pages.SitemapError, match="ikke et sitemap"):
        pages.parse_sitemap((P / "list.html").read_bytes(), SITEMAP)
    with pytest.raises(pages.SitemapError, match="tomt"):
        pages.parse_sitemap(b"  ", SITEMAP)


def test_gzip_sitemap_by_magic_bytes_and_gz_url(cfg):
    raw = (P / "urlset.xml").read_bytes()
    assert len(pages.parse_sitemap(gzip.compress(raw), SITEMAP).entries) == 8
    assert len(pages.parse_sitemap(raw, SITEMAP + ".gz").entries) == 8  # allerede pakket ud af HTTP-laget
    gz_url = "https://www.kilde.dk/sitemap.xml.gz"
    f = fetcher({gz_url: (gzip.compress(raw), "application/x-gzip"), **ARTICLES})
    res = COLLECTORS["sitemap"](src(feeds=[gz_url]), f, ctx(cfg))
    assert res.error is None and len(res.entries) == 3
    with pytest.raises(pages.SitemapError, match="udpakket over"):
        pages._gunzip(gzip.compress(b"x" * 5000), limit=1000)
    with pytest.raises(pages.SitemapError, match="ugyldig gzip"):
        pages.parse_sitemap(b"\x1f\x8bikke gzip", SITEMAP)


def test_xxe_is_not_resolved():
    sm = pages.parse_sitemap((P / "xxe.xml").read_bytes(), SITEMAP)
    assert [e.loc for e in sm.entries] == [ART1]  # poster med entiteter springes over


def test_billion_laughs_is_rejected_quickly():
    t0 = time.monotonic()
    with pytest.raises(pages.SitemapError, match="entiteter"):
        pages.parse_sitemap((P / "billion_laughs.xml").read_bytes(), SITEMAP)
    assert time.monotonic() - t0 < 2


def test_news_sitemap_entries():
    sm = pages.parse_sitemap((P / "news.xml").read_bytes(), SITEMAP)
    pant, kun_dato, uden_titel = sm.entries
    assert pant.news_title == "Pant på vinflasker & saftflasker fra 2027"
    assert pant.news_published == datetime(2026, 10, 7, 7, 12, tzinfo=UTC) and pant.news_quality == "kilde"
    assert kun_dato.news_quality == "liste"
    assert uden_titel.news_title is None  # uden news:title er det en almindelig URL


def test_choose_sub_sitemaps():
    sm = pages.parse_sitemap((P / "sitemap_index.xml").read_bytes(), SITEMAP)
    chosen = [e.loc.rsplit("/", 1)[1] for e in pages.choose_sub_sitemaps(sm.entries, 5)]
    assert chosen == [
        "sitemap-tags.xml",
        "sitemap-nyheder-2.xml",
        "sitemap-nyheder-3.xml",
        "sitemap-presse.xml",
        "sitemap-nyheder-1.xml",
    ]
    undated = [pages.SitemapEntry(f"https://x.dk/s{i}.xml") for i in range(8)]
    assert [e.loc for e in pages.choose_sub_sitemaps(undated, 5)] == [
        f"https://x.dk/s{i}.xml" for i in (7, 6, 5, 4, 3)
    ]


def test_choose_sub_sitemaps_with_equal_lastmod_takes_the_last_ones():
    # Mange generatorer giver alle under-sitemaps genereringstidspunktet som lastmod
    same = datetime(2026, 10, 7, 6, 0, tzinfo=UTC)
    subs = [pages.SitemapEntry(f"https://x.dk/sitemap-{i}.xml", same) for i in range(1, 9)]
    assert [e.loc for e in pages.choose_sub_sitemaps(subs, 5)] == [
        f"https://x.dk/sitemap-{i}.xml" for i in (8, 7, 6, 5, 4)
    ]


def test_bare_ampersand_in_loc_is_kept():
    xml = (
        f'<urlset xmlns="{SM_NS}">'
        "<url><loc>https://www.kilde.dk/nyheder/visning?id=123&lang=da</loc></url>"
        "<url><loc>https://www.kilde.dk/nyheder/c&d</loc></url>"
        "<url><loc><![CDATA[https://www.kilde.dk/nyheder/x?a=1&b=2]]></loc></url>"
        "<url><loc>https://www.kilde.dk/nyheder/y?a=1&amp;b=2&#38;c=3</loc></url>"
        "</urlset>"
    ).encode()
    assert [e.loc for e in pages.parse_sitemap(xml, SITEMAP).entries] == [
        NEWS + "visning?id=123&lang=da",
        NEWS + "c&d",
        NEWS + "x?a=1&b=2",
        NEWS + "y?a=1&b=2&c=3",
    ]


# ── Sitemap: indsamling ─────────────────────────────────────


def test_sitemap_window_order_and_entries(cfg):
    c = ctx(cfg)
    f = fetcher(routes())
    res = COLLECTORS["sitemap"](src(), f, c)
    assert res.error is None
    # Nyeste lastmod først, URL'er uden lastmod sidst; sitemap med conditional GET, sider uden
    assert urls_called(f, 0) == [SITEMAP, ART1, ART2, ART4]
    assert f.calls[0][1] is True and not any(cond for _, cond in f.calls[1:])
    by_url = {e.url: e for e in res.entries}
    first = by_url[ART1]
    assert first.title == "Ny genbrugsplads åbner i Nordby" and first.source_id == "kilde"
    assert first.published == datetime(2026, 10, 7, 5, 30, tzinfo=UTC)  # sidens dato, aldrig lastmod
    assert first.date_quality == "kilde" and first.found_via == "feed" and first.lang == "da"
    assert by_url[ART4].published == datetime(2026, 10, 6, 11, 45, tzinfo=UTC)
    assert c.seen["kilde"] == {item_id(u): "2026-10-07" for u in (ART1, ART2, ART4)}
    text = diag(res)
    assert (
        "URL'er: 7 i alt, 5 matcher, 2 med lastmod inden for 3 dage, "
        "1 uden lastmod (0 registreret som baseline), 0 fra Google News, 3 nye, 0 sprunget over (strict)"
    ) in text
    assert "https://www.kilde.dk/om-os" in text and "https://andet-domaene.dk/nyheder/fremmed-artikel" in text
    assert "sider: 3 hentet (3 ok, 0 fejl)" in text


def test_sitemap_first_run_window_and_baseline(cfg):
    c = ctx(cfg, first_run=True)
    f = fetcher(routes())
    res = COLLECTORS["sitemap"](src(), f, c)
    assert res.error is None
    assert urls_called(f) == [ART1, ART2, ART3]  # 14 dage; meget-gammel er udenfor
    assert c.seen["kilde"][item_id(ART4)] == "2026-10-07"  # uden lastmod: baseline uden hentning
    assert len(c.seen["kilde"]) == 4
    assert "1 registreret som baseline" in diag(res)


def test_window_reaches_back_to_the_last_successful_run_after_downtime(cfg):
    during = NEWS + "skrevet-under-nedetiden"
    table = {
        SITEMAP: (urlset([(during, (NOW - timedelta(days=5)).isoformat())]), XML),
        during: (P / "article_plain.html", HTML),
    }
    f = fetcher(table)
    COLLECTORS["sitemap"](src(), f, ctx(cfg, last_ok=date(2026, 10, 7)))  # kørte i dag: 3 dage
    assert urls_called(f) == []
    f = fetcher(table)
    res = COLLECTORS["sitemap"](src(), f, ctx(cfg, last_ok=date(2026, 10, 1)))  # nede siden 1. oktober
    assert urls_called(f) == [during] and "med lastmod inden for 7 dage" in diag(res)
    res = COLLECTORS["sitemap"](src(), fetcher(table), ctx(cfg, last_ok=date(2026, 8, 1)))
    assert "med lastmod inden for 14 dage" in diag(res)  # højst som ved første kørsel


def test_seen_urls_are_skipped_and_dates_refreshed_after_30_days(cfg):
    old, recent = item_id(ART1), item_id(ART2)
    c = ctx(cfg, seen={"kilde": {old: "2026-08-01", recent: "2026-09-30", "ikke-set": "2026-01-01"}})
    f = fetcher(routes())
    COLLECTORS["sitemap"](src(), f, c)
    assert urls_called(f) == [ART4]
    s = c.seen["kilde"]
    assert s[old] == "2026-10-07"  # observeret igen, og datoen var over 30 dage gammel
    assert s[recent] == "2026-09-30"  # under 30 dage: uændret (ingen git-churn hver time)
    assert s["ikke-set"] == "2026-01-01"  # ikke observeret: fjernes først af save_seen


def test_unchanged_sitemap_touches_seen(cfg):
    c = ctx(cfg, seen={"kilde": {"a": "2026-01-01", "b": "2026-10-01"}})
    res = COLLECTORS["sitemap"](src(), fetcher({SITEMAP: 304}), c)
    assert res.error is None and res.entries == []
    assert c.seen["kilde"] == {"a": "2026-10-07", "b": "2026-10-01"}


def test_at_most_15_pages_newest_first_rest_next_run(cfg):
    rows = [(NEWS + f"artikel-{i:02d}", (NOW - timedelta(hours=i)).isoformat()) for i in range(20)]
    table = {
        SITEMAP: (urlset(list(reversed(rows))), XML),
        NEWS + "artikel-": (P / "article_plain.html", HTML),
    }
    c = ctx(cfg)
    f = fetcher(table)
    res = COLLECTORS["sitemap"](src(), f, c)
    assert res.error is None and len(res.entries) == 15
    assert urls_called(f) == [u for u, _ in rows[:15]]
    assert set(c.seen["kilde"]) == {item_id(u) for u, _ in rows[:15]}  # resten markeres ikke
    assert SITEMAP not in f.http_cache  # ETag glemt, så en 304 ikke skjuler resten
    assert "5 sider venter til næste kørsel" in diag(res)
    f2 = fetcher(table)
    COLLECTORS["sitemap"](src(), f2, c)
    assert urls_called(f2) == [u for u, _ in rows[15:]]
    assert SITEMAP in f2.http_cache


def test_strict_needs_strong_word_in_slug_also_with_aeoeaa(cfg):
    urls = [
        NEWS + "nyt-forbraendingsanlaeg-i-vest",
        NEWS + "kredsloeb-aabner-ny-plads",
        NEWS + "sommerfest-i-parken",
        NEWS + "gebyr%C3%A6ndring-p%C3%A5-affald",
    ]
    table = {
        SITEMAP: (urlset([(u, "2026-10-07") for u in urls]), XML),
        NEWS: (P / "article_plain.html", HTML),
    }
    f = fetcher(table)
    res = COLLECTORS["sitemap"](src(filter="strict"), f, ctx(cfg))
    assert urls_called(f) == [urls[0], urls[1], urls[3]]
    assert "1 sprunget over (strict)" in diag(res)


def test_news_sitemap_uses_title_and_date_without_fetching(cfg):
    uden_titel = NEWS + "uden-titel"
    c = ctx(cfg)
    f = fetcher({SITEMAP: (P / "news.xml", XML), uden_titel: (P / "article_plain.html", HTML)})
    res = COLLECTORS["sitemap"](src(), f, c)
    assert urls_called(f, 0) == [SITEMAP, uden_titel]  # kun posten uden news:title hentes
    by_url = {e.url: e for e in res.entries}
    pant = by_url[NEWS + "pant-paa-vinflasker"]
    assert pant.title == "Pant på vinflasker & saftflasker fra 2027" and pant.teaser == ""
    assert pant.published == datetime(2026, 10, 7, 7, 12, tzinfo=UTC) and pant.date_quality == "kilde"
    assert by_url[NEWS + "kun-dato"].date_quality == "liste"
    assert by_url[uden_titel].title == "Sommerfest i parken"
    assert set(c.seen["kilde"]) == {item_id(uden_titel)}  # Google News-poster behandles som RSS
    assert "2 fra Google News" in diag(res)


def test_index_follows_five_newest_sub_sitemaps(cfg):
    old = urlset([(NEWS + "arkiv", "2025-01-01")])
    table = {SITEMAP: (P / "sitemap_index.xml", XML), "https://www.kilde.dk/sitemap-": (old, XML)}
    f = fetcher(table)
    res = COLLECTORS["sitemap"](src(), f, ctx(cfg))
    assert res.error is None and res.entries == []  # ingen nye artikler er ikke en fejl
    assert [u.rsplit("/", 1)[1] for u in urls_called(f, 0)] == [
        "sitemap.xml",
        "sitemap-tags.xml",
        "sitemap-nyheder-2.xml",
        "sitemap-nyheder-3.xml",
        "sitemap-presse.xml",
        "sitemap-nyheder-1.xml",
    ]
    text = diag(res)
    assert "7 under-sitemaps, følger 5" in text
    assert "https://www.kilde.dk/sitemap-tags.xml (lastmod 2026-10-07)" in text


def test_index_only_follows_sub_sitemaps_on_own_hosts(cfg):
    foreign = "https://fremmed.example/sitemap.xml"
    own = "https://www.kilde.dk/s1.xml"
    table = {
        SITEMAP: (index([(foreign, "2026-10-07"), (own, "2026-10-06")]), XML),
        own: (urlset([(NEWS + "arkiv", "2025-01-01")]), XML),
        foreign: (urlset([]), XML),
    }
    f = fetcher(table)
    res = COLLECTORS["sitemap"](src(), f, ctx(cfg))
    assert res.error is None and urls_called(f, 0) == [SITEMAP, own]
    assert "2 under-sitemaps, følger 1 (1 på fremmede værter springes over)" in diag(res)
    f = fetcher(table)
    COLLECTORS["sitemap"](src(domains=["fremmed.example"]), f, ctx(cfg))  # domains tillader værten
    assert urls_called(f, 0) == [SITEMAP, foreign, own]


def test_nested_index_one_level_and_six_fetches(cfg):
    def idx(*names: str) -> tuple[bytes, str]:
        # Nyeste lastmod først i den rækkefølge, navnene står
        return index([(f"https://www.kilde.dk/{n}", f"2026-10-0{7 - i}") for i, n in enumerate(names)]), XML

    leaf = (urlset([(NEWS + "arkiv", "2025-01-01")]), XML)
    table = {
        SITEMAP: idx("idx-2.xml", "a.xml", "b.xml"),
        "https://www.kilde.dk/idx-2.xml": idx("n1.xml", "idx-3.xml", "n2.xml"),  # indlejret indeks
        "https://www.kilde.dk/idx-3.xml": idx("dyb.xml"),  # et niveau for dybt
        **{f"https://www.kilde.dk/{n}": leaf for n in ("n1.xml", "n2.xml", "a.xml", "b.xml", "dyb.xml")},
    }
    f = fetcher(table)
    res = COLLECTORS["sitemap"](src(), f, ctx(cfg))
    assert res.error is None
    assert [u.rsplit("/", 1)[1] for u in urls_called(f, 0)] == [
        "sitemap.xml",
        "idx-2.xml",
        "n1.xml",
        "idx-3.xml",
        "n2.xml",
        "a.xml",
    ]
    text = diag(res)
    assert "idx-3.xml: for dybt indlejret" in text
    assert "højst 6 sitemap-hentninger pr. kørsel: 1 springes over" in text


def test_zero_matching_urls_is_an_error_with_examples(cfg):
    res = COLLECTORS["sitemap"](src(match="/findes-ikke/"), fetcher(routes()), ctx(cfg))
    assert res.error.startswith("0 matchende URL'er i sitemap")
    assert "URL'er, der ikke matcher" in diag(res)


def test_diagnosis_shows_matching_examples_also_without_match(cfg):
    # En kandidatkilde uden match og uden lastmod: alt registreres som baseline, men eksemplerne viser URL'erne
    rows = [(f"https://www.kilde.dk/side-{i:02d}", None) for i in range(50)]
    source = src(match=None, status="kandidat")
    res = COLLECTORS["sitemap"](source, fetcher({SITEMAP: (urlset(rows), XML)}), ctx(cfg, first_run=True))
    text = diag(res)
    assert "URL'er, der matcher (eksempler, match None):" in text
    assert text.count("  https://www.kilde.dk/side-") == 10
    assert "  https://www.kilde.dk/side-45" in text  # jævnt fordelt, ikke kun de første


def test_empty_news_sitemap_is_not_an_error_but_an_empty_sitemap_is(cfg):
    # Et Google News-sitemap viser kun de seneste 48 timer og er tomt i en stille weekend
    empty_news = f'<urlset xmlns="{SM_NS}" xmlns:news="{pages.NEWS_NS}"></urlset>'.encode()
    res = COLLECTORS["sitemap"](src(), fetcher({SITEMAP: (empty_news, XML)}), ctx(cfg))
    assert res.error is None and "tomt Google News-sitemap" in diag(res)
    res = COLLECTORS["sitemap"](src(), fetcher({SITEMAP: (urlset([]), XML)}), ctx(cfg))
    assert res.error == "tomt sitemap (ingen URL'er)"


@pytest.mark.parametrize(
    ("table", "why"),
    [
        (
            {SITEMAP: (index([("https://kilde-cdn.example/sitemap-1.xml", "2026-10-07")]), XML)},
            "1 under-sitemaps på fremmede værter (tjek domains)",
        ),
        ({SITEMAP: (index([]), XML)}, "tomt indeks"),
        (
            {
                SITEMAP: (index([("https://www.kilde.dk/idx-2.xml", "2026-10-07")]), XML),
                "https://www.kilde.dk/idx-2.xml": (index([("https://www.kilde.dk/idx-3.xml", "2026-10-07")]), XML),
                "https://www.kilde.dk/idx-3.xml": (index([("https://www.kilde.dk/s.xml", "2026-10-07")]), XML),
            },
            "idx-3.xml: for dybt indlejret",
        ),
    ],
)
def test_index_without_usable_sub_sitemaps_is_an_error(cfg, table, why):
    res = COLLECTORS["sitemap"](src(), fetcher(table), ctx(cfg))
    assert res.error.startswith("indeks uden brugbare under-sitemaps") and why in res.error


def test_same_sitemap_is_fetched_once_per_run(cfg):
    news_sm = "https://www.kilde.dk/news-sitemap.xml"
    table = {
        SITEMAP: (index([(news_sm, "2026-10-07")]), XML),
        news_sm: (urlset([(NEWS + "arkiv", "2025-01-01")]), XML),
    }
    f = fetcher(table)
    res = COLLECTORS["sitemap"](src(feeds=[SITEMAP, news_sm]), f, ctx(cfg))
    assert res.error is None and urls_called(f, 0) == [SITEMAP, news_sm]


# ── Sitemap: betingede forespørgsler (ETag → 304) ──────────

SUB = "https://www.kilde.dk/sitemap-nyheder.xml"


def test_unchanged_index_still_reads_its_sub_sitemaps(cfg):
    seen: dict = {}
    cache: dict = {}
    table = {SITEMAP: (index([(SUB, "")]), XML), SUB: (urlset([(ART1, "2026-10-07")]), XML), **ARTICLES}
    cls = _fakes().make_fetcher_class(table, etags=True)

    res = COLLECTORS["sitemap"](src(), cls(None, cache, {}, NOW), ctx(cfg, seen=seen))
    assert [e.url for e in res.entries] == [ART1]
    assert cache[SITEMAP]["sitemaps"] == [SUB] and "etag" in cache[SUB]  # begge gemmes i state/http.json

    # Kørsel 2: indekset er uændret (304), men under-sitemappet har fået en ny artikel
    cls.routes[SUB] = (urlset([(ART1, "2026-10-07"), (ART2, "2026-10-07")]), XML)
    cls.calls.clear()
    res = COLLECTORS["sitemap"](src(), cls(None, cache, {}, NOW), ctx(cfg, seen=seen))
    assert res.error is None and [e.url for e in res.entries] == [ART2]
    assert cls.calls[:2] == [(SITEMAP, True), (SUB, True)]
    assert f"indeks {SITEMAP}: uændret (304); følger de 1 under-sitemaps fra sidst" in diag(res)

    # Kørsel 3: indeks og under-sitemap er begge uændrede: først da er der intet nyt
    cls.calls.clear()
    res = COLLECTORS["sitemap"](src(), cls(None, cache, {}, NOW), ctx(cfg, seen=seen))
    assert res.error is None and res.entries == [] and cls.calls == [(SITEMAP, True), (SUB, True)]
    assert f"sitemap {SUB}: uændret (304)" in diag(res)


def test_zero_matches_in_a_changed_sitemap_is_no_error_when_others_are_unchanged(cfg):
    # Kun sider-sitemappet er ændret; nyhedssitemappet (med de matchende URL'er) svarer 304
    pages_sm = "https://www.kilde.dk/sitemap-sider.xml"
    table = {
        SITEMAP: (index([(SUB, "2026-10-07"), (pages_sm, "2026-10-06")]), XML),
        SUB: (urlset([(ART1, "2026-10-07")]), XML),
        pages_sm: (urlset([("https://www.kilde.dk/om-os", "2026-10-07")]), XML),
        **ARTICLES,
    }
    cache: dict = {}
    seen: dict = {}
    cls = _fakes().make_fetcher_class(table, etags=True)
    assert COLLECTORS["sitemap"](src(), cls(None, cache, {}, NOW), ctx(cfg, seen=seen)).error is None
    cls.routes[pages_sm] = (urlset([("https://www.kilde.dk/kontakt", "2026-10-07")]), XML)
    res = COLLECTORS["sitemap"](src(), cls(None, cache, {}, NOW), ctx(cfg, seen=seen))
    assert res.error is None and "andre var uændrede (304)" in diag(res)


def test_partial_content_error_forgets_only_that_sitemap(cfg):
    broken = "https://www.kilde.dk/sitemap-sider.xml"
    table = {
        SITEMAP: (index([(SUB, "2026-10-07"), (broken, "2026-10-06")]), XML),
        SUB: (urlset([(ART1, "2026-10-07")]), XML),
        broken: (page("<title>Fejl</title>"), HTML),  # en HTML-side i stedet for et sitemap
        **ARTICLES,
    }
    cache: dict = {}
    res = COLLECTORS["sitemap"](src(), fetcher(table, etags=True, http_cache=cache), ctx(cfg))
    assert res.error is None and [e.url for e in res.entries] == [ART1]
    assert broken not in cache and SUB in cache and SITEMAP in cache


@pytest.mark.parametrize(
    ("failure", "incomplete"), [(500, True), ("timeout", True), ("budget", True), (404, False)]
)
def test_unread_sitemap_or_list_leaves_the_baseline_incomplete(cfg, failure, incomplete):
    sub2 = "https://www.kilde.dk/sitemap-2.xml"
    table = {
        SITEMAP: (index([(SUB, "2026-10-07"), (sub2, "2026-10-06")]), XML),
        SUB: (urlset([(NEWS + "arkiv", "2025-01-01")]), XML),
        sub2: failure,
    }
    res = COLLECTORS["sitemap"](src(), fetcher(table), ctx(cfg, first_run=True))
    assert res.backlog is incomplete  # URL'er uden lastmod i det ulæste sitemap mangler i baseline
    assert ("baseline er ikke komplet" in diag(res)) is incomplete
    lst2 = "https://www.kilde.dk/da/arkiv/"
    res = COLLECTORS["html"](html_src(feeds=[LIST, lst2]), fetcher(html_routes(**{lst2: failure})), ctx(cfg))
    assert res.backlog is incomplete


SOFT_404 = (page("<title>Siden findes ikke</title>", "<h1>Siden findes ikke</h1>"), HTML)


@pytest.mark.parametrize(
    ("method", "table", "kw", "error"),
    [
        ("sitemap", {SITEMAP: SOFT_404}, {}, "ikke et sitemap"),
        ("sitemap", {SITEMAP: (P / "urlset.xml", XML)}, {"match": "/findes-ikke/"}, "0 matchende URL'er"),
        ("sitemap", {SITEMAP: (urlset([]), XML)}, {}, "tomt sitemap"),
        ("sitemap", {SITEMAP: (index([("https://fremmed.example/s.xml", "")]), XML)}, {}, "indeks uden"),
        ("sitemap", {SITEMAP: (P / "urlset.xml", XML), NEWS: 500}, {}, "alle 3 sidehentninger fejlede"),
        ("html", {LIST: (P / "list.html", HTML)}, {"select": "ul.gammel-liste a"}, "0 matchende links"),
        ("html", {LIST: (b'{"items": []}', "application/json")}, {}, "listesiden er ikke HTML"),
    ],
)
def test_content_errors_forget_the_etag_so_the_error_stays(cfg, method, table, kw, error):
    """En fejl i indholdet må ikke blive til "uændret (304)" ved næste kørsel og forsvinde fra sundheden."""
    source = src(**kw) if method == "sitemap" else html_src(**kw)
    doc = SITEMAP if method == "sitemap" else LIST
    cache: dict = {}
    cls = _fakes().make_fetcher_class(table, etags=True)
    for _ in range(3):
        cls.calls.clear()
        res = COLLECTORS[method](source, cls(None, cache, {}, NOW), ctx(cfg))
        assert error in res.error
        assert cls.calls[0] == (doc, True) and doc not in cache  # betinget, men ETag'en er glemt


def test_unreachable_or_invalid_sitemap_is_an_error(cfg):
    assert "HTTP 500" in COLLECTORS["sitemap"](src(), fetcher({SITEMAP: 500}), ctx(cfg)).error
    assert (
        "ikke et sitemap"
        in COLLECTORS["sitemap"](src(), fetcher({SITEMAP: (P / "list.html", HTML)}), ctx(cfg)).error
    )
    table = {SITEMAP: (P / "sitemap_index.xml", XML)}  # alle under-sitemaps giver 404
    assert "ingen under-sitemaps kunne hentes" in COLLECTORS["sitemap"](src(), fetcher(table), ctx(cfg)).error


def test_all_page_fetches_failing_is_an_error_partial_is_not(cfg):
    res = COLLECTORS["sitemap"](src(), fetcher(routes(**{ART1: 500, ART2: 500, ART4: 503})), ctx(cfg))
    assert res.error.startswith("alle 3 sidehentninger fejlede")
    c = ctx(cfg)
    f = fetcher(routes(**{ART2: 500}))
    res = COLLECTORS["sitemap"](src(), f, c)
    assert res.error is None and len(res.entries) == 2
    assert item_id(ART2) not in c.seen["kilde"]  # prøves igen næste gang
    assert SITEMAP not in f.http_cache


@pytest.mark.parametrize(
    ("failure", "permanent"),
    [
        (404, True),
        (410, True),
        (401, True),
        (403, True),
        ("robots", True),
        ("too_large", True),
        (500, False),
        (503, False),
        (429, False),
        ("timeout", False),
    ],
)
def test_permanent_page_errors_are_marked_transient_are_retried(cfg, failure, permanent):
    c = ctx(cfg)
    res = COLLECTORS["sitemap"](src(), fetcher(routes(**{ART1: failure})), c)
    assert res.error is None and {e.url for e in res.entries} == {ART2, ART4}
    assert (item_id(ART1) in c.seen["kilde"]) is permanent
    assert res.backlog is not permanent  # en forbigående fejl er en restkø
    f = fetcher(routes(**{ART1: failure}))
    COLLECTORS["sitemap"](src(), f, c)
    assert urls_called(f) == ([] if permanent else [ART1])  # en varig fejl prøves ikke ved hver kørsel


def test_one_page_that_cannot_be_extracted_does_not_fail_the_source(cfg, monkeypatch):
    real = pages.extract_page

    def extract(content, url, *args, **kw):
        if url == ART1:
            raise RuntimeError("fejl i udtrækket")
        return real(content, url, *args, **kw)

    monkeypatch.setattr(pages, "extract_page", extract)
    c = ctx(cfg)
    res = COLLECTORS["sitemap"](src(), fetcher(routes()), c)
    assert res.error is None and {e.url for e in res.entries} == {ART2, ART4}
    assert item_id(ART1) in c.seen["kilde"] and "1 kunne ikke udtrækkes" in diag(res)


def test_budget_stops_nicely(cfg):
    c = ctx(cfg)
    f = fetcher(routes(**{ART2: "budget"}))
    res = COLLECTORS["sitemap"](src(), f, c)
    assert res.error is None and [e.url for e in res.entries] == [ART1]
    assert urls_called(f) == [ART1, ART2]  # ART4 forsøges ikke
    assert set(c.seen["kilde"]) == {item_id(ART1)}
    assert "tidsbudgettet er brugt: 2 sider venter" in diag(res)


def test_robots_blocked_pages(cfg):
    c = ctx(cfg)
    res = COLLECTORS["sitemap"](src(), fetcher(routes(**{ART1: "robots"})), c)
    assert res.error is None and {e.url for e in res.entries} == {ART2, ART4}
    assert item_id(ART1) in c.seen["kilde"]  # robots.txt forbyder siden: prøves ikke ved hver kørsel
    res = COLLECTORS["sitemap"](
        src(), fetcher(routes(**{ART1: "robots", ART2: "robots", ART4: "robots"})), ctx(cfg)
    )
    assert res.error == "alle 3 sider er blokeret af robots.txt"


def test_non_html_page_is_skipped_but_marked_seen(cfg):
    c = ctx(cfg)
    res = COLLECTORS["sitemap"](src(), fetcher(routes(**{ART1: (b"%PDF-1.7", "application/pdf")})), c)
    assert res.error is None and {e.url for e in res.entries} == {ART2, ART4}
    assert item_id(ART1) in c.seen["kilde"]
    assert "1 ikke HTML" in diag(res)


# ── html-lister ─────────────────────────────────────────────


def html_routes(**extra) -> dict:
    return {
        LIST: (P / "list.html", HTML),
        LIST + "ny-genbrugsplads-aabner": (
            page("<title>Ny genbrugsplads åbner | Kildeforeningen</title>"),
            HTML,
        ),
        LIST + "affaldsgebyr-stiger": (P / "article_meta.html", HTML),
        LIST + "sommerfest-i-parken": (P / "article_plain.html", HTML),
        **extra,
    }


def test_html_list_select_match_base_href_and_list_dates(cfg):
    c = ctx(cfg)
    f = fetcher(html_routes())
    res = COLLECTORS["html"](html_src(), f, c)
    assert res.error is None
    # <base href>, fragment fjernet, dublet og fremmed vært sorteret fra, dokumentets rækkefølge
    assert urls_called(f) == [
        LIST + "ny-genbrugsplads-aabner",
        LIST + "affaldsgebyr-stiger",
        LIST + "sommerfest-i-parken",
    ]
    by_url = {e.url: e for e in res.entries}
    nyt = by_url[LIST + "ny-genbrugsplads-aabner"]
    assert nyt.title == "Ny genbrugsplads åbner"
    assert (
        nyt.published == datetime(2026, 10, 6, 22, 0, tzinfo=UTC) and nyt.date_quality == "liste"
    )  # listens dato
    gebyr = by_url[LIST + "affaldsgebyr-stiger"]
    assert (
        gebyr.published == datetime(2026, 10, 5, 12, 32, tzinfo=UTC) and gebyr.date_quality == "kilde"
    )  # siden vinder
    fest = by_url[LIST + "sommerfest-i-parken"]
    assert fest.published is None and fest.date_quality == "fundet"  # ingen dato i sit eget listepunkt
    assert len(c.seen["liste"]) == 3
    text = diag(res)
    assert (
        "liste https://www.kilde.dk/da/nyheder/: 12 links på siden, "
        "4 valgt af select 'ul.news li.item', 3 matcher '/nyheder/'"
    ) in text
    assert "alle links (eksempler):" in text and "matchende links (eksempler):" in text
    assert f"  {LIST}ny-genbrugsplads-aabner | Ny genbrugsplads åbner" in text


def test_html_strict_uses_link_text_or_slug(cfg):
    f = fetcher(html_routes())
    res = COLLECTORS["html"](html_src(filter="strict"), f, ctx(cfg))
    assert urls_called(f) == [LIST + "ny-genbrugsplads-aabner", LIST + "affaldsgebyr-stiger"]
    assert "1 sprunget over (strict)" in diag(res)


@pytest.mark.parametrize("select", ["ul.news li.item", None])
def test_link_text_is_the_longest_among_links_to_the_same_url(cfg, select):
    # Et kort med et billedlink før titellinket: billedlinkets tomme tekst må ikke vinde
    url = "https://www.kilde.dk/nyheder/nyhed-101"
    lst = page(
        body="<ul class='news'><li class='item'><a href='/nyheder/nyhed-101'><img src='a.jpg' alt=''></a>"
        "<h3><a href='/nyheder/nyhed-101'>Ny genbrugsplads åbner i Nordby</a></h3></li></ul>"
    )
    f = fetcher({LIST: (lst, HTML), url: (P / "article_plain.html", HTML)})
    res = COLLECTORS["html"](html_src(select=select, filter="strict"), f, ctx(cfg))
    assert urls_called(f) == [url]  # strict finder de stærke ord i linkteksten
    assert f"  {url} | Ny genbrugsplads åbner i Nordby" in diag(res)


def test_list_page_itself_is_never_an_article(cfg):
    lst_url = "https://www.kilde.dk/nyheder"
    lst = page(
        body="<nav><a href='/nyheder'>Nyheder</a> &gt; <a href='/nyheder/'>Alle nyheder</a></nav>"
        "<ul><li><a href='/nyheder/affald-1'>Affald 1</a></li></ul>"
    )
    f = fetcher({lst_url: (lst, HTML), lst_url + "/affald-1": (P / "article_plain.html", HTML)})
    res = COLLECTORS["html"](src(method="html", feeds=[lst_url], match="/nyheder"), f, ctx(cfg))
    assert res.error is None and urls_called(f, 0) == [lst_url, lst_url + "/affald-1"]


def test_unchanged_list_touches_seen(cfg):
    c = ctx(cfg, seen={"liste": {"a": "2026-01-01", "b": "2026-10-01"}})
    res = COLLECTORS["html"](html_src(), fetcher({LIST: 304}), c)
    assert res.error is None and res.entries == []
    assert c.seen["liste"] == {"a": "2026-10-07", "b": "2026-10-01"}


def test_html_at_most_30_links_and_15_pages_per_run(cfg):
    lst = "https://www.kilde.dk/liste"
    body = (
        "<ul>"
        + "".join(f'<li><a href="/nyheder/artikel-{i:02d}">Artikel {i}</a></li>' for i in range(35))
        + "</ul>"
    )
    table = {lst: (page(body=body), HTML), NEWS + "artikel-": (P / "article_plain.html", HTML)}
    c = ctx(cfg)
    runs = []
    backlog = []
    for _ in range(3):
        f = fetcher(table)
        res = COLLECTORS["html"](src(method="html", feeds=[lst]), f, c)
        assert res.error is None
        runs.append(urls_called(f))
        backlog.append(res.backlog)
    assert runs[0] == [NEWS + f"artikel-{i:02d}" for i in range(15)]
    assert runs[1] == [NEWS + f"artikel-{i:02d}" for i in range(15, 30)]
    assert runs[2] == []  # de sidste 5 er ud over de 30 links; ingen nye er ikke en fejl
    assert backlog == [True, False, False]


def test_html_errors(cfg):
    res = COLLECTORS["html"](html_src(select="div.findes-ikke a"), fetcher(html_routes()), ctx(cfg))
    assert res.error.startswith("0 matchende links på listesiden")
    assert "HTTP 404" in COLLECTORS["html"](html_src(), fetcher({LIST: 404}), ctx(cfg)).error
    not_html = fetcher({LIST: (b"%PDF-1.4", "application/pdf")})
    assert "ikke HTML" in COLLECTORS["html"](html_src(), not_html, ctx(cfg)).error


def test_invalid_select_is_rejected_by_the_model():
    with pytest.raises(ValidationError, match="CSS-selektor"):
        html_src(select="ul[[")


# ── seen-state på disk ──────────────────────────────────────


@pytest.fixture
def env(tmp_path, monkeypatch):
    return _fakes().setup_env(tmp_path, monkeypatch, sources=P / "sources.yaml")


def test_save_seen_prunes_sorts_and_skips_empty(env):
    path = paths.STATE_DIR / "seen.json"
    assert store.save_seen({"a": {}}, NOW, {"a"}, 120) is False and not path.exists()
    seen = {
        "b": {"z": "2026-10-07", "a": "2026-06-09", "gl": "2026-06-08"},
        "a": {"x": "2026-10-01"},
        "slettet": {"y": "2026-10-07"},
    }
    assert store.save_seen(seen, NOW, {"a", "b"}, 120) is True
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data == {"a": {"x": "2026-10-01"}, "b": {"a": "2026-06-09", "z": "2026-10-07"}}  # sorteret
    assert list(data["b"]) == ["a", "z"]
    assert store.save_seen(seen, NOW, {"a", "b"}, 120) is False  # uændret indhold skrives ikke
    assert store.load_seen() == data


# ── Gennem pipeline og check ────────────────────────────────

KOMMUNE = "https://www.testkommune.dk/nyheder"
KOMMUNE_ARTICLE = page(
    '<meta property="og:title" content="Testkommune">'
    "<title>Kommunen åbner for tekstilaffald - Testkommune</title>",
    "<main><h1>Kommunen åbner for tekstilaffald</h1><p>Publiceret 6. oktober 2026 kl. 13.45</p></main>",
)
RUN_ROUTES = {
    SITEMAP: (P / "sitemap_index.xml", XML),
    "https://www.kilde.dk/sitemap-": (P / "urlset.xml", XML),
    **ARTICLES,
    KOMMUNE: (P / "kommune_list.html", HTML),
    KOMMUNE + "/kommunen-aabner-for-tekstilaffald": (KOMMUNE_ARTICLE, HTML),
    KOMMUNE + "/2026/10/05/affaldsgebyret-stiger": (P / "article_plain.html", HTML),
}


def _run(monkeypatch, now: str, dry_run: bool = False, table: dict | None = None, only: str | None = None):
    fake = _fakes().make_fetcher_class(RUN_ROUTES if table is None else table, etags=True)
    monkeypatch.setattr(pipeline, "Fetcher", fake)
    code = pipeline.main_run(argparse.Namespace(only=only, dry_run=dry_run, now=now))
    return code, fake


def test_run_with_sitemap_and_html_sources(env, monkeypatch):
    code, fake = _run(monkeypatch, "2026-10-07T08:05:00Z")
    assert code == 0
    cands = {c.title: c for c in store.load_candidates()}
    assert set(cands) == {
        "Ny genbrugsplads åbner i Nordby",
        "Affaldsgebyret stiger i 2027",
        "Gammel nyhed om deponi",
        "Kommunen åbner for tekstilaffald",
    }
    assert all(c.baseline for c in cands.values())
    assert cands["Ny genbrugsplads åbner i Nordby"].source == "kilde-sitemap"
    tekstil = cands["Kommunen åbner for tekstilaffald"]
    assert tekstil.source == "testkommune" and tekstil.date_quality == "kilde"
    assert tekstil.published == datetime(2026, 10, 6, 11, 45, tzinfo=UTC)
    # Hentet og udtrukket, men afvist af forfiltret: står i seen, så den ikke hentes igen
    assert "Sommerfest i parken" in {r.title for r in store.load_rejected()}
    seen = json.loads((paths.STATE_DIR / "seen.json").read_text(encoding="utf-8"))
    assert set(seen) == {"kilde-sitemap", "testkommune"}
    assert set(seen["kilde-sitemap"]) == {item_id(u) for u in (ART1, ART2, ART3, ART4)}  # ART4 som baseline
    assert set(seen["testkommune"].values()) == {"2026-10-07"} and len(seen["testkommune"]) == 2
    states = store.load_source_states()
    assert states["kilde-sitemap"].first_run_done and states["testkommune"].health == "groen"
    first_pages = {u for u, _ in fake.calls if "/nyheder/" in u and not u.endswith("/nyheder")}
    # ETags for indeks, de fulgte under-sitemaps og listen gemmes; artikelsiders gemmes ikke
    http = store.load_http_cache()
    subs = http[SITEMAP]["sitemaps"]
    assert len(subs) == 5 and set(http) == {SITEMAP, KOMMUNE, *subs}

    # Næste kørsel (6 t senere): alt er uændret (304), også under-sitemaps; ingen kendte sider hentes
    before = (paths.STATE_DIR / "seen.json").read_bytes()
    code, fake = _run(monkeypatch, "2026-10-07T14:05:00Z")
    assert code == 0
    assert fake.calls == [(SITEMAP, True), *((u, True) for u in subs), (KOMMUNE, True)]
    assert fake.statuses == [(SITEMAP, 304), *((u, 304) for u in subs), (KOMMUNE, 304)]
    assert not first_pages & {u for u, _ in fake.calls}
    assert len(store.load_candidates()) == 4
    assert (paths.STATE_DIR / "seen.json").read_bytes() == before
    assert store.load_source_states()["kilde-sitemap"].health == "groen"


def test_first_run_continues_until_the_baseline_is_complete(env, monkeypatch):
    """Første kørsels restkø hentes som baseline (14 dage), og URL'er uden lastmod bliver baseline, også når et
    under-sitemap fejlede i første kørsel. Først når baseline er komplet, er kilden ude af første kørsel."""
    sub1, sub2 = "https://www.kilde.dk/sitemap-1.xml", "https://www.kilde.dk/sitemap-2.xml"
    now = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)
    rows = [(NEWS + f"affald-{i:02d}", (now - timedelta(hours=12 * i)).isoformat()) for i in range(20)]
    undated = [(NEWS + f"arkiv-{i}", None) for i in range(3)]
    table: dict = {
        SITEMAP: (index([(sub1, "2026-10-07"), (sub2, "2026-10-06")]), XML),
        sub1: (urlset(rows), XML),
        sub2: 500,  # forbigående fejl i første kørsel
    }
    for i, (url, lastmod) in enumerate(rows + [(NEWS + "ny-artikel", None)]):
        meta = f'<meta property="article:published_time" content="{lastmod}">' if lastmod else ""
        table[url] = (page(meta, f"<main><h1>Affaldsnyhed nummer {i}</h1></main>"), HTML)

    def run(at: str):
        code, fake = _run(monkeypatch, at, table=table, only="kilde-sitemap")
        assert code == 0
        pages_called = [u for u, _ in fake.calls if "/nyheder/" in u]
        return pages_called, store.load_source_states()["kilde-sitemap"], store.load_candidates()

    called, state, cands = run("2026-10-07T08:05:00Z")
    assert called == [u for u, _ in rows[:15]] and not state.first_run_done and state.health == "groen"
    assert all(c.baseline for c in cands)

    # 6 t senere: stadig første kørsel. De 5 sidste (op til 9,5 døgn gamle, uden for 3-dages-vinduet) hentes,
    # og under-sitemappets URL'er uden lastmod registreres som baseline uden at blive hentet
    table[sub2] = (urlset(undated), XML)
    called, state, cands = run("2026-10-07T14:05:00Z")
    assert called == [u for u, _ in rows[15:]] and state.first_run_done
    assert len(cands) == 20 and all(c.baseline for c in cands)
    seen = json.loads((paths.STATE_DIR / "seen.json").read_text(encoding="utf-8"))["kilde-sitemap"]
    assert {item_id(u) for u, _ in rows + undated} == set(seen)

    # Baseline er komplet: en ny URL uden lastmod er nu ny og hentes (ikke baseline)
    table[sub2] = (urlset(undated + [(NEWS + "ny-artikel", None)]), XML)
    called, state, cands = run("2026-10-07T20:05:00Z")
    assert called == [NEWS + "ny-artikel"]
    assert not next(c for c in cands if c.url == NEWS + "ny-artikel").baseline


def test_run_covers_the_downtime_since_the_last_successful_run(env, monkeypatch):
    table = {SITEMAP: (urlset([(NEWS + "arkiv", "2025-01-01")]), XML)}
    assert _run(monkeypatch, "2026-10-01T08:05:00Z", table=table, only="kilde-sitemap")[0] == 0
    _run(monkeypatch, "2026-10-04T08:05:00Z", table={SITEMAP: 500}, only="kilde-sitemap")  # nede
    during = NEWS + "skrevet-under-nedetiden"  # lastmod 4 dage før næste vellykkede kørsel
    table = {
        SITEMAP: (urlset([(during, "2026-10-03T09:00:00+02:00")]), XML),
        during: (P / "article_plain.html", HTML),
    }
    code, fake = _run(monkeypatch, "2026-10-07T08:05:00Z", table=table, only="kilde-sitemap")
    assert code == 0 and (during, False) in fake.calls


def test_seen_is_rolled_back_when_a_source_raises(env, monkeypatch):
    code, _ = _run(monkeypatch, "2026-10-07T08:05:00Z", table={**RUN_ROUTES, ART2: "raise"})
    assert code == 0
    # ART1 blev hentet og ART4 registreret som baseline før undtagelsen, men intet af det er behandlet
    seen = json.loads((paths.STATE_DIR / "seen.json").read_text(encoding="utf-8"))
    assert set(seen) == {"testkommune"}
    state = store.load_source_states()["kilde-sitemap"]
    assert state.last_error.startswith("RuntimeError") and not state.first_run_done
    assert SITEMAP not in store.load_http_cache()


def test_dry_run_does_not_write_seen(env, monkeypatch):
    code, fake = _run(monkeypatch, "2026-10-07T08:05:00Z", dry_run=True)
    assert code == 0 and any(u == ART1 for u, _ in fake.calls)
    assert not env.data.exists() or not any(p.is_file() for p in env.data.rglob("*"))


def test_check_fetch_explain_prints_diagnostics_and_writes_nothing(env, monkeypatch, capsys):
    fake = _fakes().make_fetcher_class(RUN_ROUTES)
    monkeypatch.setattr(fetchmod, "Fetcher", fake)
    assert main_check(argparse.Namespace(fetch="kilde-sitemap", explain=True)) == 0
    out = capsys.readouterr().out
    assert "DIAGNOSE" in out and "7 under-sitemaps, følger 5" in out
    assert "1 registreret som baseline" in out  # check --fetch er en første kørsel med tom seen
    assert "BEHOLDT" in out and "Gammel nyhed om deponi" in out
    assert main_check(argparse.Namespace(fetch="testkommune", explain=True)) == 0
    out = capsys.readouterr().out
    assert "alle links (eksempler):" in out and "Kommunen åbner for tekstilaffald" in out
    assert main_check(argparse.Namespace(fetch="testkommune", explain=False)) == 0
    assert "DIAGNOSE" not in capsys.readouterr().out
    assert not env.data.exists() or not any(env.data.rglob("*.*"))
