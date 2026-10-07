"""Normalisering af URL'er, id'er, tekst og titler (KONTRAKTER §5.2)."""

from __future__ import annotations

import hashlib
import html
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

# Sporingsparametre, der fjernes fra URL'er
_TRACKING_KEYS = {"fbclid", "gclid", "ref", "mc_cid", "mc_eid"}

# æøå som i URL-slugs ("affaldsloesning")
TRANSLIT = str.maketrans({"æ": "ae", "ø": "oe", "å": "aa", "Æ": "AE", "Ø": "OE", "Å": "AA"})

_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG_RE = re.compile(r"<!--.*?-->|</?[a-zA-Z][^<>]*>", re.DOTALL)
_ZERO_WIDTH_RE = re.compile("[​‌‍⁠﻿­]")
_WS_RE = re.compile(r"\s+")
_PUNCT_RE = re.compile(r"[\W_]+")

# Separator før en kildehale: " | ", " - ", " – ", " — "
_TAIL_SEP_RE = re.compile(r"\s+([|\-–—])\s+")
_DOMAIN_TAIL_RE = re.compile(r"[\w.-]+\.(dk|com|net|org|eu|se|no|de|info|nu)", re.IGNORECASE)
_TRUNC_STRIP = " ,;:–—-·|/"


def normalize_url(url: str) -> str:
    """https, uden www., fragment, afsluttende / og sporingsparametre; øvrige parametre sorteret."""
    u = (url or "").strip()
    if not u:
        return ""
    if u.startswith("//"):
        u = "https:" + u
    elif "://" not in u:
        u = "https://" + u
    try:
        parts = urlsplit(u)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return u
    if parts.scheme.lower() not in ("http", "https") or not host:
        return u

    host = host.rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    netloc = host if port in (None, 80, 443) else f"{host}:{port}"

    path = parts.path or "/"
    if path != "/":
        path = path.rstrip("/") or "/"

    params = [
        (k, v)
        for k, v in parse_qsl(parts.query, keep_blank_values=True)
        if not k.lower().startswith("utm_") and k.lower() not in _TRACKING_KEYS
    ]
    params.sort()
    query = urlencode(params, quote_via=quote, safe="/:@!$'()*,;~") if params else ""
    return urlunsplit(("https", netloc, path, query, ""))


def item_id(url: str) -> str:
    """Stabilt id: de første 12 hex-tegn af sha1 over den normaliserede URL."""
    return hashlib.sha1(normalize_url(url).encode("utf-8")).hexdigest()[:12]


def host_of(url: str) -> str:
    """Værtsnavn med små bogstaver og uden www. ("" hvis URL'en ikke har en vært)."""
    u = (url or "").strip()
    if not u:
        return ""
    if "://" not in u and not u.startswith("//"):
        u = "//" + u
    try:
        host = urlsplit(u).hostname or ""
    except ValueError:
        return ""
    host = host.rstrip(".")
    return host[4:] if host.startswith("www.") else host


def clean_text(s: str | None, max_len: int) -> str:
    """Fjern HTML, afkod entiteter, saml whitespace og afkort ved ord med "…" (max_len ≤ 0 = ingen grænse)."""
    if not s:
        return ""
    t = _SCRIPT_RE.sub(" ", s)
    t = _TAG_RE.sub(" ", t)
    t = html.unescape(t)
    # Dobbelt-escapet HTML ("&lt;p&gt;") bliver først til tags efter unescape
    t = _TAG_RE.sub(" ", t)
    t = _ZERO_WIDTH_RE.sub("", t)
    t = unicodedata.normalize("NFC", t)
    t = _WS_RE.sub(" ", t).strip()
    if max_len > 0 and len(t) > max_len:
        cut = t[: max_len - 1]
        if not t[len(cut)].isspace():
            space = cut.rfind(" ")
            if space >= max_len // 2:
                cut = cut[:space]
        t = cut.rstrip(_TRUNC_STRIP) + "…"
    return t


def _looks_like_name(tail: str) -> bool:
    """Ligner halen et kildenavn ("DR", "TV 2 Lorry", "avisen.dk")?"""
    if _DOMAIN_TAIL_RE.fullmatch(tail):
        return True
    words = tail.split()
    return 0 < len(words) <= 4 and all(w[0].isupper() or w[0].isdigit() for w in words)


def _squash(s: str) -> str:
    """Kun bogstaver og tal, små bogstaver ("Amager Ressourcecenter" → "amagerressourcecenter")."""
    return "".join(ch for ch in unicodedata.normalize("NFKC", s).casefold() if ch.isalnum())


def _name_keys(names: Iterable[str]) -> list[str]:
    return [k for k in dict.fromkeys(_squash(n) for n in names) if len(k) >= 3]


def _is_name(text: str, keys: list[str]) -> bool:
    """Er teksten et af navnene eller en del af et af dem ("MST" i "Miljøstyrelsen (MST)")?"""
    sq = _squash(text)
    return len(sq) >= 3 and any(sq == k or sq in k for k in keys)


def matches_name(text: str, names: Iterable[str]) -> bool:
    """Er teksten præcis et af navnene (fx et og:title, der kun er sidens navn)?"""
    return _squash(text) in _name_keys(names)


def _strip_tail(title: str, keys: list[str]) -> str:
    """Fjern én kildehale (" | Altinget", " - DR") hvis den ligner et kildenavn eller er et af keys."""
    matches = list(_TAIL_SEP_RE.finditer(title))
    if not matches:
        return title
    m = matches[-1]
    head, tail = title[: m.start()].strip(), title[m.end() :].strip()
    if len(head.split()) < 2 or not tail:
        return title
    if keys and _is_name(tail, keys):
        return head
    if len(tail) > 40:
        return title
    if m.group(1) == "|":
        return head if len(tail.split()) <= 5 else title
    return head if _looks_like_name(tail) else title


def strip_site_tail(title: str, names: Iterable[str] = ()) -> str:
    """Fjern op til to kildehaler sidst i en titel. names (kildens navn og vært) fjernes uanset længde."""
    keys = _name_keys(names)
    t = title
    for _ in range(2):
        stripped = _strip_tail(t, keys)
        if stripped == t:
            break
        t = stripped
    return t


def normalize_title(title: str) -> str:
    """Små bogstaver uden tegnsætning og kildehaler. Bruges til historier og dedupe."""
    t = unicodedata.normalize("NFKC", title or "")
    t = strip_site_tail(_WS_RE.sub(" ", t).strip())
    t = _PUNCT_RE.sub(" ", t.casefold())
    return _WS_RE.sub(" ", t).strip()


def strip_publisher_suffix(title: str, publisher: str | None) -> str:
    """Fjern " - Udgiver", " | Udgiver" eller " – Udgiver" sidst i titlen (uanset store/små bogstaver)."""
    t = (title or "").strip()
    name = (publisher or "").strip()
    if not t or not name:
        return t
    name_rx = r"\s+".join(re.escape(w) for w in name.split())
    rx = re.compile(rf"\s+[-|–—]\s+{name_rx}\s*$", re.IGNORECASE)
    stripped = rx.sub("", t).strip()
    return stripped or t
