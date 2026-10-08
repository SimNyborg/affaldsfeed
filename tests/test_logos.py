"""Kildernes logoer (logos.py, KONTRAKTER §6.4) med falsk Fetcher. Ingen netværk."""

from __future__ import annotations

import base64
import struct
import zlib
from datetime import timedelta
from types import SimpleNamespace

import pytest

from affaldsfeed import logos, paths
from affaldsfeed.models import LogoSettings
from affaldsfeed.timeutil import parse_iso
from tests.fixtures.fakes import make_fetcher_class

NOW = parse_iso("2026-10-08T06:00:00Z")
HTML = "text/html; charset=utf-8"


def png(w: int = 32, h: int = 32) -> bytes:
    """Et gyldigt, gennemsigtigt PNG på w × h pixels."""
    raw = b"".join(b"\x00" + b"\x00\x00\x00\x00" * w for _ in range(h))

    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def ico(*sizes: int) -> bytes:
    """En ICO-fil med et PNG pr. størrelse (0 i kataloget betyder 256)."""
    images = [png(s, s) for s in sizes]
    offset = 6 + 16 * len(sizes)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    entries = b""
    for s, img in zip(sizes, images, strict=True):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(img), offset)
        offset += len(img)
    return head + entries + b"".join(images)


SVG = b'<svg xmlns="http://www.w3.org/2000/svg"><script>alert(1)</script></svg>'


@pytest.fixture
def state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(paths, "STATE_DIR", tmp_path / "state")
    return tmp_path / "state"


def fetcher(routes: dict):
    cls = make_fetcher_class(routes)
    cls.calls = []
    return cls, cls(None, {}, {}, NOW)


# ── Hvilke logoer ───────────────────────────────────────────


def test_site_domains_are_other_sites_than_the_homepage():
    assert logos.site_domains("https://www.tv2nord.dk", ["tvsyd.dk", "www.tv2fyn.dk", "TVSYD.dk", " "]) == [
        "tvsyd.dk", "tv2fyn.dk"]
    assert logos.site_domains("https://nyheder.tv2.dk", ["tv2.dk"]) == []  # overdomæne: samme site
    assert logos.site_domains("https://www.ft.dk", ["oda.ft.dk"]) == []  # underdomæne: samme site
    assert logos.site_domains(None, ["a.dk"]) == ["a.dk"]
    assert logos.domain_key("tv2-regionerne", "tvsyd.dk") == "tv2-regionerne--tvsyd-dk"


def test_logo_targets_cover_each_sender_once_and_the_other_sites_of_sources():
    def info(sid, homepage, via_search=False):
        return SimpleNamespace(id=sid, homepage=homepage, via_search=via_search)

    tv2 = info("tv2-regionerne", "https://www.tv2nord.dk")
    known = {"tv2-regionerne": tv2, "tv2-gammel": tv2, "folketinget": info("folketinget", "https://www.ft.dk"),
             "jv-dk": info("jv-dk", "https://jv.dk", True)}
    sources = [
        SimpleNamespace(id="tv2-regionerne", homepage="https://www.tv2nord.dk", domains=["tvsyd.dk"]),
        SimpleNamespace(id="folketinget", homepage="https://www.ft.dk", domains=["oda.ft.dk"]),  # samme site
        SimpleNamespace(id="planlagt", homepage="https://p.dk", domains=["q.dk"]),  # ikke aktiv: ikke i known
    ]
    assert logos.logo_targets(known, sources) == [
        ("tv2-regionerne", "tv2-regionerne", "https://www.tv2nord.dk"),
        ("tv2-regionerne--tvsyd-dk", "tv2-regionerne", "https://tvsyd.dk/"),
        ("folketinget", "folketinget", "https://www.ft.dk"),
        ("jv-dk", "jv-dk", "https://jv.dk"),
    ]


# ── Billeder ────────────────────────────────────────────────


def test_sniff_and_size():
    assert logos.sniff(png()) == "png" and logos.pixel_size(png(48, 32), "png") == 48
    assert logos.sniff(ico(16, 48)) == "ico" and logos.pixel_size(ico(16, 48), "ico") == 48
    assert logos.pixel_size(ico(256), "ico") == 256  # 0 i kataloget er 256
    assert logos.sniff(b"GIF89a" + struct.pack("<HH", 32, 32) + b"\x00" * 60) == "gif"
    assert logos.sniff(b"\xff\xd8\xff\xe0" + b"\x00" * 80) == "jpg"
    assert logos.sniff(b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 80) == "webp"
    assert logos.sniff(SVG) is None
    assert logos.sniff(b"<!doctype html><title>Siden findes ikke</title>") is None


def test_acceptable_rejects_tiny_large_and_unknown():
    assert logos.acceptable(png(32, 32), 200_000) == "png"
    assert logos.acceptable(png(1, 1), 200_000) is None  # pladsholder på 1 × 1
    assert logos.acceptable(png(64, 64), 50) is None  # over loftet
    assert logos.acceptable(b"\x89PNG\r\n\x1a\n", 200_000) is None  # afkortet
    assert logos.acceptable(SVG * 10, 200_000) is None
    assert logos.acceptable(None, 200_000) is None


# ── Kandidater på forsiden ──────────────────────────────────


def test_icon_links_ranks_best_first_and_skips_svg():
    page = b"""<html><head>
      <link rel="icon" href="/favicon-16.png" sizes="16x16">
      <link rel="icon" href="/favicon-32.png" sizes="32x32" type="image/png">
      <link rel="apple-touch-icon" href="/apple.png">
      <link rel="mask-icon" href="/mask.svg" color="#000">
      <link rel="icon" href="/icon.svg" type="image/svg+xml">
      <link rel="shortcut icon" href="https://cdn.example.com/fav.ico">
      <link rel="stylesheet" href="/s.css">
    </head><body></body></html>"""
    urls = [link.url for link in logos.icon_links(page, "https://www.example.dk/", HTML)]
    assert urls == [
        "https://www.example.dk/favicon-32.png",
        "https://cdn.example.com/fav.ico",
        "https://www.example.dk/apple.png",
        "https://www.example.dk/favicon-16.png",
    ]


def test_icon_links_resolve_against_base_and_final_url():
    page = b'<head><base href="/assets/"><link rel="icon" href="icons/f.png" sizes="48x48"></head>'
    assert [x.url for x in logos.icon_links(page, "https://www.example.dk/forside", HTML)] == [
        "https://www.example.dk/assets/icons/f.png"]
    assert logos.favicon_urls("https://nyheder.example.dk/", "https://example.dk") == [
        "https://nyheder.example.dk/favicon.ico", "https://example.dk/favicon.ico"]


def test_icon_links_handles_junk():
    assert logos.icon_links(b"", "https://x.dk/", HTML) == []
    assert logos.icon_links(b"<link rel='icon' href='javascript:alert(1)'>", "https://x.dk/", HTML) == []


# ── Hentning ────────────────────────────────────────────────


def test_fetch_logo_uses_best_icon():
    page = b'<head><link rel="icon" href="/f32.png" sizes="32x32"><link rel="icon" href="/f16.png" sizes="16x16"></head>'
    cls, f = fetcher({
        "https://www.example.dk/": (page, HTML),
        "https://www.example.dk/f32.png": (png(32, 32), "image/png"),
        "https://www.example.dk/favicon.ico": 404,
    })
    res = logos.fetch_logo(f, "https://www.example.dk/", 200_000)
    assert res.ext == "png" and res.src == "https://www.example.dk/f32.png" and res.error is None
    assert [u for u, _ in cls.calls] == ["https://www.example.dk/", "https://www.example.dk/f32.png"]
    assert all(conditional is False for _, conditional in cls.calls)


def test_fetch_logo_falls_back_to_favicon_ico():
    _, f = fetcher({
        "https://www.example.dk/": 404,
        "https://www.example.dk/favicon.ico": (ico(16, 32), "image/x-icon"),
    })
    res = logos.fetch_logo(f, "https://www.example.dk/", 200_000)
    assert res.ext == "ico" and res.src == "https://www.example.dk/favicon.ico"


def test_fetch_logo_never_keeps_svg_or_html():
    page = b'<head><link rel="icon" href="/soft404.png"></head>'
    _, f = fetcher({
        "https://www.example.dk/": (page, HTML),
        "https://www.example.dk/soft404.png": (b"<!doctype html><p>Siden findes ikke</p>" * 3, HTML),
        "https://www.example.dk/favicon.ico": (SVG, "image/svg+xml"),
    })
    res = logos.fetch_logo(f, "https://www.example.dk/", 200_000)
    assert res.data is None and res.ext is None and "brugbart billede" in res.error


def test_fetch_logo_reads_data_uri_without_request():
    uri = "data:image/png;base64," + base64.b64encode(png(32, 32)).decode()
    cls, f = fetcher({"https://www.example.dk/": (f'<link rel="icon" href="{uri}">'.encode(), HTML)})
    res = logos.fetch_logo(f, "https://www.example.dk/", 200_000)
    assert res.ext == "png" and res.src == "data:" and [u for u, _ in cls.calls] == ["https://www.example.dk/"]


def test_fetch_logo_skips_icons_robots_txt_forbids_without_using_tries():
    """Som HOFOR: alle ikoner ligger i en mappe, robots.txt forbyder, men /favicon.ico er tilladt."""
    page = b"".join(
        f'<link rel="icon" href="/wp-content/uploads/ikon-{s}.png" sizes="{s}x{s}">'.encode() for s in (32, 48, 180, 192)
    )
    cls, f = fetcher({
        "https://www.example.dk/forside": (page, HTML),  # ruterne matcher også på præfiks
        "https://www.example.dk/wp-content/uploads/": "robots",
        "https://www.example.dk/favicon.ico": (ico(16, 32), "image/x-icon"),
    })
    res = logos.fetch_logo(f, "https://www.example.dk/forside", 200_000)
    assert res.ext == "ico" and res.src == "https://www.example.dk/favicon.ico"
    assert len(cls.calls) == 1 + 4 + 1  # forsiden, fire forbudte ikoner og /favicon.ico


def test_fetch_logo_tries_at_most_three_images():
    page = b"".join(f'<link rel="icon" href="/ikon-{s}.png" sizes="{s}x{s}">'.encode() for s in (32, 48, 64, 96))
    cls, f = fetcher({"https://www.example.dk/forside": (page, HTML)})  # alt andet svarer 404
    res = logos.fetch_logo(f, "https://www.example.dk/forside", 200_000)
    assert res.data is None and res.error == "HTTP 404"
    assert len(cls.calls) == 1 + logos.MAX_TRIES  # forsiden og tre billeder, ikke /favicon.ico


def test_fetch_logo_tells_lasting_failures_from_passing_ones():
    # Som Folketinget: forsiden svarer 403 (Cloudflare, som aldrig omgås), og /favicon.ico findes ikke
    _, f = fetcher({"https://www.example.dk/": 403, "https://www.example.dk/favicon.ico": 404})
    res = logos.fetch_logo(f, "https://www.example.dk/", 200_000)
    assert res.error == "HTTP 404" and res.permanent

    _, f = fetcher({"https://www.example.dk/": "timeout", "https://www.example.dk/favicon.ico": 404})
    assert not logos.fetch_logo(f, "https://www.example.dk/", 200_000).permanent  # forsiden svarede ikke

    _, f = fetcher({
        "https://www.example.dk/forside": (b'<link rel="icon" href="/f.png" sizes="32x32">', HTML),
        "https://www.example.dk/f.png": 502,
        "https://www.example.dk/favicon.ico": 404,
    })
    assert not logos.fetch_logo(f, "https://www.example.dk/forside", 200_000).permanent


def test_fetch_logo_stops_on_budget():
    _, f = fetcher({"https://www.example.dk/": "budget"})
    assert logos.fetch_logo(f, "https://www.example.dk/", 200_000).budget


# ── Plan og state ───────────────────────────────────────────


def site(name: str, icon: bytes | int = 404) -> dict:
    base = f"https://www.{name}.dk/"
    return {base: (b'<link rel="icon" href="/f.png" sizes="32x32">', HTML), f"{base}f.png": (icon, "image/png")
            if isinstance(icon, bytes) else icon, f"{base}favicon.ico": 404}


def test_refresh_saves_logo_and_waits_until_due(state_dir):
    routes = site("tv2", png(32, 32))
    cls, f = fetcher(routes)
    settings = LogoSettings()
    counts = logos.refresh_logos([("tv2", "https://www.tv2.dk/")], f, NOW, settings)
    assert counts == {"hentet": 1, "fejl": 0, "venter": 0}
    assert (state_dir / "logos" / "tv2.png").read_bytes() == png(32, 32)
    entry = logos.load_state()["tv2"]
    assert entry == {"file": "tv2.png", "src": "https://www.tv2.dk/f.png", "checked": "2026-10-08T06:00:00Z",
                     "error": None}
    assert logos.logo_files() == {"tv2": "tv2.png"}

    cls.calls.clear()
    logos.refresh_logos([("tv2", "https://www.tv2.dk/")], f, NOW + timedelta(days=29), settings)
    assert cls.calls == []  # ikke på tur før refresh_days
    logos.refresh_logos([("tv2", "https://www.tv2.dk/")], f, NOW + timedelta(days=30), settings)
    assert cls.calls  # nu igen


def test_refresh_saves_a_logo_for_another_site_under_its_own_id(state_dir):
    _, f = fetcher(site("tvsyd", png(32, 32)))
    key = logos.domain_key("tv2-regionerne", "tvsyd.dk")
    logos.refresh_logos([(key, "https://www.tvsyd.dk/")], f, NOW, LogoSettings())
    assert logos.logo_files() == {key: f"{key}.png"}
    assert (state_dir / "logos" / "tv2-regionerne--tvsyd-dk.png").read_bytes() == png(32, 32)


def test_refresh_drops_an_old_logo_after_a_lasting_failure(state_dir):
    cls, f = fetcher(site("ft", png(32, 32)))
    settings = LogoSettings()
    logos.refresh_logos([("ft", "https://www.ft.dk/")], f, NOW, settings)
    assert logos.logo_files() == {"ft": "ft.png"}
    cls.routes.update(site("ft", 404))  # ikonet er væk, og /favicon.ico findes ikke
    counts = logos.refresh_logos([("ft", "https://www.ft.dk/")], f, NOW + timedelta(days=30), settings)
    assert counts["fejl"] == 1 and logos.logo_files() == {}
    assert not (state_dir / "logos" / "ft.png").exists()
    assert logos.load_state()["ft"] == {"file": None, "src": None, "checked": "2026-11-07T06:00:00Z", "error": "HTTP 404"}


def test_refresh_failure_keeps_old_logo_and_retries_after_retry_days(state_dir):
    cls, f = fetcher(site("tv2", png(32, 32)))
    settings = LogoSettings()
    logos.refresh_logos([("tv2", "https://www.tv2.dk/")], f, NOW, settings)
    cls.routes.update(site("tv2", 500))
    later = NOW + timedelta(days=30)
    counts = logos.refresh_logos([("tv2", "https://www.tv2.dk/")], f, later, settings)
    assert counts["fejl"] == 1
    entry = logos.load_state()["tv2"]
    assert entry["file"] == "tv2.png" and entry["error"] == "HTTP 500"  # det gamle logo bevares
    assert (state_dir / "logos" / "tv2.png").is_file()

    cls.calls.clear()
    logos.refresh_logos([("tv2", "https://www.tv2.dk/")], f, later + timedelta(days=6), settings)
    assert cls.calls == []  # et logo, der findes, tjekkes efter refresh_days, også efter en fejl
    nolog_cls, nolog = fetcher(site("ny"))
    logos.refresh_logos([("tv2", "https://www.tv2.dk/"), ("ny", "https://www.ny.dk/")], nolog, later, settings)
    nolog_cls.calls.clear()
    logos.refresh_logos([("tv2", "https://www.tv2.dk/"), ("ny", "https://www.ny.dk/")], nolog,
                        later + timedelta(days=6), settings)
    assert nolog_cls.calls == []  # en kilde uden logo prøves først igen efter retry_days
    logos.refresh_logos([("tv2", "https://www.tv2.dk/"), ("ny", "https://www.ny.dk/")], nolog,
                        later + timedelta(days=7), settings)
    assert "https://www.ny.dk/" in {u for u, _ in nolog_cls.calls}


def test_refresh_priority_max_per_run_and_force(state_dir):
    routes = {**site("a", png()), **site("b", png()), **site("c", png())}
    cls, f = fetcher(routes)
    targets = [("a", "https://www.a.dk/"), ("b", "https://www.b.dk/"), ("c", "https://www.c.dk/")]
    counts = logos.refresh_logos(targets, f, NOW, LogoSettings(max_per_run=2), priority={"c": 5})
    assert counts == {"hentet": 2, "fejl": 0, "venter": 1}
    assert set(logos.logo_files()) == {"c", "a"}  # kilder i feedet først, derefter efter id

    cls.calls.clear()
    logos.refresh_logos(targets, f, NOW + timedelta(days=1), LogoSettings(), force={"a"})
    assert {u for u, _ in cls.calls} == {"https://www.a.dk/", "https://www.a.dk/f.png"}  # kun den tvungne


def test_refresh_stops_on_budget_and_skips_bad_ids(state_dir):
    cls, f = fetcher({"https://www.a.dk/": "budget"})
    counts = logos.refresh_logos([("a", "https://www.a.dk/"), ("b", "https://www.b.dk/"), ("../x", "https://x.dk/"),
                                  ("c", None)], f, NOW, LogoSettings())
    assert counts["hentet"] == 0 and counts["venter"] == 2
    assert [u for u, _ in cls.calls] == ["https://www.a.dk/"]
    assert logos.load_state() == {}


def test_refresh_removes_old_sources_and_stray_files(state_dir):
    _, f = fetcher({**site("a", png()), **site("gammel", png())})
    logos.refresh_logos([("a", "https://www.a.dk/"), ("gammel", "https://www.gammel.dk/")], f, NOW, LogoSettings())
    (state_dir / "logos" / "a.ico").write_bytes(ico(32))  # en gammel fil med en anden endelse
    logos.refresh_logos([("a", "https://www.a.dk/")], f, NOW + timedelta(days=1), LogoSettings())
    assert set(logos.load_state()) == {"a"}
    assert sorted(p.name for p in (state_dir / "logos").iterdir()) == ["a.png"]


def test_logo_files_only_trusts_expected_names(state_dir):
    folder = state_dir / "logos"
    folder.mkdir(parents=True)
    (folder / "a.png").write_bytes(png())
    (state_dir / "secret.txt").write_text("hemmelig", encoding="utf-8")
    logos.save_state({
        "a": {"file": "a.png", "checked": "2026-10-08T06:00:00Z"},
        "b": {"file": "../secret.txt", "checked": "2026-10-08T06:00:00Z"},
        "c": {"file": "a.png", "checked": "2026-10-08T06:00:00Z"},  # en anden kildes fil
    })
    assert logos.logo_files() == {"a": "a.png"}
