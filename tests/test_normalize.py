from __future__ import annotations

import hashlib

import pytest

from affaldsfeed.normalize import (
    clean_text,
    host_of,
    item_id,
    normalize_title,
    normalize_url,
    strip_publisher_suffix,
)

# ── normalize_url ──────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("http://www.Example.dk/a/b/?utm_source=x&b=2&a=1#top", "https://example.dk/a/b?a=1&b=2"),
        ("https://arc.dk", "https://arc.dk/"),
        ("https://arc.dk/", "https://arc.dk/"),
        ("https://arc.dk/nyheder/", "https://arc.dk/nyheder"),
        ("https://arc.dk/nyheder//", "https://arc.dk/nyheder"),
        ("https://x.dk/a?fbclid=1&gclid=2&ref=rss&mc_cid=3&mc_eid=4&UTM_Medium=e", "https://x.dk/a"),
        ("https://x.dk/a?side=2&id=7", "https://x.dk/a?id=7&side=2"),
        ("https://x.dk:443/a", "https://x.dk/a"),
        ("http://x.dk:8080/a", "https://x.dk:8080/a"),
        ("  arc.dk/nyheder/  ", "https://arc.dk/nyheder"),
        ("//www.arc.dk/x", "https://arc.dk/x"),
        ("https://x.dk/Sti/MED/Store", "https://x.dk/Sti/MED/Store"),
        ("", ""),
    ],
)
def test_normalize_url(url, expected):
    assert normalize_url(url) == expected


def test_normalize_url_keeps_blank_params_and_is_idempotent():
    u = normalize_url("https://x.dk/s?q=affald+gebyr&tom=")
    assert u == normalize_url(u)
    assert "tom=" in u


def test_item_id_is_sha1_of_normalized_url():
    url = "http://www.arc.dk/nyheder/ny-ordning/?utm_campaign=x"
    expected = hashlib.sha1(b"https://arc.dk/nyheder/ny-ordning").hexdigest()[:12]
    assert item_id(url) == expected
    assert len(item_id(url)) == 12
    assert item_id(url) == item_id("https://arc.dk/nyheder/ny-ordning#kommentarer")


# ── host_of ────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://WWW.Arc.dk/nyheder", "arc.dk"),
        ("http://nyheder.ku.dk/x?y=1", "nyheder.ku.dk"),
        ("arc.dk/x", "arc.dk"),
        ("https://www.dr.dk:443/", "dr.dk"),
        ("", ""),
    ],
)
def test_host_of(url, expected):
    assert host_of(url) == expected


# ── clean_text ─────────────────────────────────────────────


def test_clean_text_strips_html_and_entities():
    s = "<p>Affald &amp; genbrug</p><script>alert(1)</script>\n\n <b>nu</b>&nbsp;også"
    assert clean_text(s, 0) == "Affald & genbrug nu også"


def test_clean_text_handles_double_escaped_html():
    assert clean_text("&lt;p&gt;Nyt gebyr&lt;/p&gt;", 300) == "Nyt gebyr"


def test_clean_text_none_and_empty():
    assert clean_text(None, 100) == ""
    assert clean_text("   ", 100) == ""


def test_clean_text_truncates_at_word():
    s = "Affaldsgebyret stiger markant i fjorten kommuner næste år"
    out = clean_text(s, 30)
    assert len(out) <= 30
    assert out == "Affaldsgebyret stiger markant…"


def test_clean_text_truncates_long_word():
    out = clean_text("a" * 50, 10)
    assert out == "a" * 9 + "…"


def test_clean_text_short_text_untouched():
    assert clean_text("Kort tekst", 300) == "Kort tekst"


def test_clean_text_removes_trailing_punctuation_before_ellipsis():
    out = clean_text("Første del, anden del og tredje del af teksten", 13)
    assert out == "Første del…"


# ── normalize_title ────────────────────────────────────────


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Affaldsgebyret stiger i 14 kommuner - TV 2 Lorry", "affaldsgebyret stiger i 14 kommuner"),
        ("Ny aftale om affald | Altinget", "ny aftale om affald"),
        ("Ny aftale om affald – DR", "ny aftale om affald"),
        ("Nyt gebyr på affald - avisen.dk", "nyt gebyr på affald"),
        ("Titel om affald - Lokalavisen | Sjællandske", "titel om affald"),
        ("“Skraldebilen kommer ikke!”, siger borger", "skraldebilen kommer ikke siger borger"),
        ("CO2-afgift på  affaldsforbrænding", "co2 afgift på affaldsforbrænding"),
    ],
)
def test_normalize_title(title, expected):
    assert normalize_title(title) == expected


def test_normalize_title_keeps_sentence_after_dash():
    # Halen er ikke et kildenavn (små bogstaver), så den bevares
    assert normalize_title("Affald stiger - men gebyrer falder") == "affald stiger men gebyrer falder"


def test_normalize_title_needs_head():
    assert normalize_title("Debat | Altinget") == "debat altinget"


def test_normalize_title_same_story_from_two_sources():
    a = normalize_title("Kommuner skal sortere tekstiler fra nytår - Ritzau")
    b = normalize_title("Kommuner skal sortere tekstiler fra nytår | Avisen.dk")
    assert a == b


# ── strip_publisher_suffix ────────────────────────────────


@pytest.mark.parametrize(
    ("title", "publisher", "expected"),
    [
        ("Affaldsgebyret stiger - DR", "DR", "Affaldsgebyret stiger"),
        ("Affaldsgebyret stiger | dr", "DR", "Affaldsgebyret stiger"),
        ("Affaldsgebyret stiger – TV 2 Lorry", "tv 2 lorry", "Affaldsgebyret stiger"),
        ("Affaldsgebyret stiger - DR", None, "Affaldsgebyret stiger - DR"),
        ("Affaldsgebyret stiger - DR", "Altinget", "Affaldsgebyret stiger - DR"),
        ("Nyt fra Køge-Avisen", "Avisen", "Nyt fra Køge-Avisen"),
        ("- DR", "DR", "- DR"),
    ],
)
def test_strip_publisher_suffix(title, publisher, expected):
    assert strip_publisher_suffix(title, publisher) == expected
