"""Test af collect/oda.py (Folketingets åbne data) med fixtures. Ingen netværkskald."""

from __future__ import annotations

import argparse
import importlib.util
import sys
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import unquote

import pytest

from affaldsfeed import paths, pipeline, store
from affaldsfeed.collect import COLLECTORS, CollectContext
from affaldsfeed.collect.oda import build_url, entry_from_doc, file_url, lookback_days, published_of
from affaldsfeed.config import load_config, load_sources, publisher_lookup
from affaldsfeed.models import OdaSettings, Source

FIXTURES = Path(__file__).resolve().parent / "fixtures"
NOW = datetime(2026, 10, 7, 8, 5, tzinfo=UTC)
JSON = "application/json; charset=utf-8"
FIRST = "https://oda.ft.dk/api/Dokument?$filter"
NEXT = "https://oda.ft.dk/api/Dokument?$skiptoken=100"
ROUTES = {FIRST: ("oda/side1.json", JSON), NEXT: ("oda/side2.json", JSON)}

ODA_SOURCE = """\
- id: folketinget-oda
  name: Folketinget
  category: myndighed
  homepage: https://www.ft.dk
  method: oda
  feeds: https://oda.ft.dk/api/
  domains: [oda.ft.dk]
  filter: none
  genre: folketing
  basis: offentlig
  checked: 2026-10-07
"""


def _fakes():
    name = "affaldsfeed_test_fakes"
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, FIXTURES / "fakes.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return sys.modules[name]


@pytest.fixture
def env(tmp_path, monkeypatch):
    sources = tmp_path / "oda_sources.yaml"
    sources.write_text(ODA_SOURCE, encoding="utf-8")
    return _fakes().setup_env(tmp_path, monkeypatch, sources=sources)


@pytest.fixture
def ctx(env):
    sources = load_sources(env.sources)
    cfg = load_config(env.config)
    return CollectContext(config=cfg, sources=sources, now=NOW, publisher_lookup=publisher_lookup(sources, cfg.publishers))


def _source(ctx) -> Source:
    return next(s for s in ctx.sources if s.id == "folketinget-oda")


def _fetcher(routes=None):
    return _fakes().make_fetcher_class(ROUTES if routes is None else routes)(None, {}, {}, NOW)


# ── Adresse og vindue ──────────────────────────────────────


def test_build_url_filters_title_date_and_public_documents():
    url = build_url("https://oda.ft.dk/api", ["affald", "cirkulær økonomi", "o'k", " "], datetime(2026, 10, 4, 10, 5), 100)
    assert url.startswith("https://oda.ft.dk/api/Dokument?$filter=")
    text = unquote(url)
    assert "(substringof('affald',titel) or substringof('cirkulær økonomi',titel) or substringof('o''k',titel))" in text
    assert "opdateringsdato gt datetime'2026-10-04T10:05:00'" in text
    assert "offentlighedskode eq 'O'" in text
    assert "&$orderby=opdateringsdato desc&$top=100&$expand=Dokumenttype,Fil&$format=json" in text
    assert " " not in url  # mellemrum er kodet


def test_lookback_days(ctx):
    cfg = OdaSettings(days=3, first_run_days=14)
    ctx.first_run = True
    assert lookback_days(ctx, cfg) == 14
    ctx.first_run = False
    ctx.last_ok = None
    assert lookback_days(ctx, cfg) == 14
    ctx.last_ok = date(2026, 10, 7)
    assert lookback_days(ctx, cfg) == 3
    ctx.last_ok = date(2026, 9, 27)
    assert lookback_days(ctx, cfg) == 11
    ctx.last_ok = date(2026, 8, 1)
    assert lookback_days(ctx, cfg) == 14


# ── Dokumenter ─────────────────────────────────────────────


def test_published_is_release_time_in_copenhagen():
    assert published_of({"frigivelsesdato": "2026-10-02T10:59:40", "dato": "2026-10-02T00:00:00"}) == (
        datetime(2026, 10, 2, 8, 59, 40, tzinfo=UTC),
        "kilde",
    )
    assert published_of({"frigivelsesdato": "2026-12-01T10:00:00.123"})[0] == datetime(2026, 12, 1, 9, 0, 0, 123000, tzinfo=UTC)


def test_published_falls_back_to_the_day_then_found():
    assert published_of({"frigivelsesdato": None, "dato": "2026-08-31T00:00:00"}) == (
        datetime(2026, 8, 30, 22, 0, tzinfo=UTC),
        "liste",
    )
    assert published_of({"frigivelsesdato": "ikke en dato", "dato": ""}) == (None, "fundet")
    assert published_of({}) == (None, "fundet")


def test_file_url_prefers_the_pdf_variant():
    files = [
        {"filurl": "https://www.ft.dk/a.docx", "variantkode": "O"},
        {"filurl": "https://www.ft.dk/a.pdf", "variantkode": "P"},
    ]
    assert file_url(files) == "https://www.ft.dk/a.pdf"
    assert file_url([{"filurl": "https://www.ft.dk/b.docx", "variantkode": "O"}]) == "https://www.ft.dk/b.docx"
    assert file_url([{"filurl": "", "variantkode": "P"}, {"variantkode": "P"}]) is None
    assert file_url(None) is None


def test_entry_from_doc_skips_excluded_private_and_fileless(ctx):
    src = _source(ctx)
    base = {"Dokumenttype": {"type": "Spørgsmål"}, "offentlighedskode": "O", "titel": "Spm. om affald",
            "Fil": [{"filurl": "https://www.ft.dk/x.pdf", "variantkode": "P"}], "frigivelsesdato": "2026-10-01T09:00:00"}
    entry, why = entry_from_doc(base, src, {"dagsorden"})
    assert why == "" and entry.url == "https://www.ft.dk/x.pdf" and entry.categories == ["Spørgsmål"]
    assert entry_from_doc({**base, "Dokumenttype": {"type": "Dagsorden"}}, src, {"dagsorden"}) == (None, "type")
    assert entry_from_doc({**base, "offentlighedskode": "F"}, src, set()) == (None, "ikke offentlig")
    assert entry_from_doc({**base, "Fil": []}, src, set()) == (None, "uden fil")
    assert entry_from_doc({**base, "titel": "  "}, src, set()) == (None, "uden titel")


# ── Indsamling ─────────────────────────────────────────────


def test_collect_follows_next_link_and_maps_documents(ctx):
    src = _source(ctx)
    fetcher = _fetcher()
    res = COLLECTORS["oda"](src, fetcher, ctx)
    assert res.error is None
    calls = [u for u, _ in type(fetcher).calls]
    assert calls[0].startswith(FIRST) and calls[1] == NEXT
    assert all(conditional is False for _, conditional in type(fetcher).calls)
    assert all(accept == "application/json" for _, accept in type(fetcher).accepts)  # ellers svarer ODA med Atom
    by_url = {e.url: e for e in res.entries}
    assert set(by_url) == {
        "https://www.ft.dk/samling/20252/almdel/beu/spm/240/3195008.pdf",
        "https://www.ft.dk/samling/20252/almdel/mof/spm/476/3193672.pdf",
        "https://www.ft.dk/samling/20252/almdel/mof/spm/141/svar/2160001/3180001.pdf",
        "https://www.ft.dk/samling/20261/kommissionsforslag/kom(2026)0512/forslag/2233740/3192716.pdf",
    }
    asbest = by_url["https://www.ft.dk/samling/20252/almdel/beu/spm/240/3195008.pdf"]
    assert asbest.title.startswith("Spm. om, i hvor mange af landets 98 kommuner")
    assert asbest.published == datetime(2026, 10, 2, 8, 59, 40, tzinfo=UTC)
    assert asbest.date_quality == "kilde"
    assert asbest.source_id == "folketinget-oda" and asbest.lang == "da" and asbest.found_via == "feed"
    kartoner = by_url["https://www.ft.dk/samling/20252/almdel/mof/spm/476/3193672.pdf"]
    assert "\n" not in kartoner.title and "  " not in kartoner.title
    assert kartoner.teaser == "Vil ministeren oplyse, hvor stor en andel af kartonerne der blev genanvendt?"
    svar = by_url["https://www.ft.dk/samling/20252/almdel/mof/spm/141/svar/2160001/3180001.pdf"]
    assert svar.date_quality == "liste" and svar.categories == ["Svar"]
    diag = " ".join(res.diagnostics)
    assert "2 sider, 8 dokumenter, 4 indslag" in diag
    assert "1 dublet" in diag and "1 ikke offentlig" in diag and "1 type" in diag and "1 uden fil" in diag


def test_collect_stops_at_max_pages(ctx):
    src = _source(ctx)
    ctx.config.settings.oda.max_pages = 1
    res = COLLECTORS["oda"](src, _fetcher(), ctx)
    assert len(res.entries) == 2
    assert "flere sider venter" in " ".join(res.diagnostics)


def test_collect_errors(ctx):
    src = _source(ctx)
    assert COLLECTORS["oda"](src, _fetcher({FIRST: 503}), ctx).error == "ODA: HTTP 503"
    assert COLLECTORS["oda"](src, _fetcher({FIRST: (b"<feed/>", "application/atom+xml")}), ctx).error == (
        "ODA svarede ikke med gyldig JSON (application/atom+xml)"
    )
    assert COLLECTORS["oda"](src, _fetcher({FIRST: (b'{"fejl": 1}', JSON)}), ctx).error == "ODA-svaret mangler value"
    # Fejler en senere side, beholdes den første, og kilden fejler ikke
    res = COLLECTORS["oda"](src, _fetcher({FIRST: ("oda/side1.json", JSON), NEXT: 500}), ctx)
    assert res.error is None and len(res.entries) == 2


def test_collect_without_feeds_is_an_error(ctx):
    src = _source(ctx).model_copy(update={"feeds": []})
    assert COLLECTORS["oda"](src, _fetcher(), ctx).error == "mangler feeds (ODA's adresse)"


# ── Hele kørslen ───────────────────────────────────────────


def test_run_gives_folketing_candidates_and_vetoes_radioactive_waste(env, monkeypatch):
    fake = _fakes().make_fetcher_class(ROUTES)
    monkeypatch.setattr(pipeline, "Fetcher", fake)
    args = argparse.Namespace(only=None, dry_run=False, now="2026-10-07T08:05:00Z")
    assert pipeline.main_run(args) == 0
    cands = {c.title: c for c in store.load_candidates()}
    asbest = next(c for t, c in cands.items() if "asbestaffald" in t)
    assert asbest.genre == "folketing" and asbest.source == "folketinget-oda"
    assert asbest.why.decision == "vis"
    assert not any("radioaktivt affald" in t for t in cands)  # veto i forfiltret
    rejected = [r for r in store.load_rejected() if "radioaktivt affald" in r.title]
    assert rejected and rejected[0].why.reason.startswith("veto")
    assert paths.STATE_DIR.joinpath("sources.json").exists()
