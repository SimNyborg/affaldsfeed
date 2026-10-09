"""Tjek af kategorifarverne i config/categories.yaml.

- Kontrast mindst 3:1: `color` mod #FFFFFF (lys) og `color_dark` mod #1A201D (mørk).
- CIEDE2000 mindst 20 mellem alle par i hver tilstand.
- Simuleret deuteranopi og protanopi (Machado, Oliveira & Fernandes 2009, grad 1,0):
  par under 10 rapporteres.
- Kategorier med samme farve i begge tilstande er bevidste søskende (fx nationale medier og
  lokalmedier). Ikonet skiller dem ad, så de måles som én farve.
- Kategorier, der afventer (`pending: true`), vises gråt i menuen og tjekkes ikke.

Brug: python tools/check_colors.py [--file STI] [--strict]
Exit 1 ved kontrastfejl (med --strict også ved for små farveafstande).
"""

import argparse
import contextlib
import itertools
import math
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from affaldsfeed.paths import CONFIG_DIR  # noqa: E402

LIGHT_BG = "#FFFFFF"
DARK_BG = "#1A201D"
MIN_CONTRAST = 3.0
MIN_DELTA_E = 20.0
MIN_DELTA_E_CVD = 10.0

# Machado 2009, grad 1,0. Anvendes på lineær RGB.
MACHADO: dict[str, tuple[tuple[float, float, float], ...]] = {
    "deuteranopi": (
        (0.367322, 0.860646, -0.227968),
        (0.280085, 0.672501, 0.047413),
        (-0.011820, 0.042940, 0.968881),
    ),
    "protanopi": (
        (0.152286, 1.052583, -0.204868),
        (0.114503, 0.786281, 0.099216),
        (-0.003882, -0.048116, 1.051998),
    ),
}

# sRGB (D65) → XYZ og referencehvid D65
_RGB_TO_XYZ = (
    (0.4124564, 0.3575761, 0.1804375),
    (0.2126729, 0.7151522, 0.0721750),
    (0.0193339, 0.1191920, 0.9503041),
)
_WHITE = (0.95047, 1.0, 1.08883)

RGB = tuple[float, float, float]
Lab = tuple[float, float, float]


# ── Farveregning ─────────────────────────────────────────────


def hex_to_rgb(value: str) -> RGB:
    """'#1F5FA8' → (r, g, b) i 0..1 (gammakodet sRGB)."""
    h = value.strip().lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"ugyldig farve: {value!r}")
    try:
        r, g, b = (int(h[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError as exc:
        raise ValueError(f"ugyldig farve: {value!r}") from exc
    return r, g, b


def rgb_to_hex(rgb: RGB) -> str:
    return "#" + "".join(f"{round(min(1.0, max(0.0, c)) * 255):02X}" for c in rgb)


def srgb_to_linear(c: float) -> float:
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def linear_to_srgb(c: float) -> float:
    c = min(1.0, max(0.0, c))
    return 12.92 * c if c <= 0.0031308 else 1.055 * c ** (1 / 2.4) - 0.055


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(a: str, b: str) -> float:
    """WCAG-kontrastforhold mellem to hex-farver."""
    la, lb = relative_luminance(hex_to_rgb(a)), relative_luminance(hex_to_rgb(b))
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def rgb_to_lab(rgb: RGB) -> Lab:
    lin = [srgb_to_linear(c) for c in rgb]
    xyz = [sum(m * c for m, c in zip(row, lin, strict=True)) for row in _RGB_TO_XYZ]
    eps = (6 / 29) ** 3

    def f(t: float) -> float:
        return t ** (1 / 3) if t > eps else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = (f(v / w) for v, w in zip(xyz, _WHITE, strict=True))
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def hex_to_lab(value: str) -> Lab:
    return rgb_to_lab(hex_to_rgb(value))


def _hue_deg(b: float, a: float) -> float:
    if a == 0 and b == 0:
        return 0.0
    return math.degrees(math.atan2(b, a)) % 360


def ciede2000(lab1: Lab, lab2: Lab, k_l: float = 1.0, k_c: float = 1.0, k_h: float = 1.0) -> float:
    """CIEDE2000 farveafstand (Sharma, Wu & Dalal 2005)."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2
    c1 = math.hypot(a1, b1)
    c2 = math.hypot(a2, b2)
    c_bar7 = ((c1 + c2) / 2) ** 7
    g = 0.5 * (1 - math.sqrt(c_bar7 / (c_bar7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)
    h1p, h2p = _hue_deg(b1, a1p), _hue_deg(b2, a2p)

    d_lp = l2 - l1
    d_cp = c2p - c1p
    if c1p * c2p == 0:
        d_hp = 0.0
    else:
        d_hp = h2p - h1p
        if d_hp > 180:
            d_hp -= 360
        elif d_hp < -180:
            d_hp += 360
    d_big_hp = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(d_hp / 2))

    l_barp = (l1 + l2) / 2
    c_barp = (c1p + c2p) / 2
    if c1p * c2p == 0:
        h_barp = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        h_barp = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        h_barp = (h1p + h2p + 360) / 2
    else:
        h_barp = (h1p + h2p - 360) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(h_barp - 30))
        + 0.24 * math.cos(math.radians(2 * h_barp))
        + 0.32 * math.cos(math.radians(3 * h_barp + 6))
        - 0.20 * math.cos(math.radians(4 * h_barp - 63))
    )
    d_theta = 30 * math.exp(-(((h_barp - 275) / 25) ** 2))
    c_barp7 = c_barp**7
    r_c = 2 * math.sqrt(c_barp7 / (c_barp7 + 25**7))
    s_l = 1 + 0.015 * (l_barp - 50) ** 2 / math.sqrt(20 + (l_barp - 50) ** 2)
    s_c = 1 + 0.045 * c_barp
    s_h = 1 + 0.015 * c_barp * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c

    dl = d_lp / (k_l * s_l)
    dc = d_cp / (k_c * s_c)
    dh = d_big_hp / (k_h * s_h)
    return math.sqrt(dl * dl + dc * dc + dh * dh + r_t * dc * dh)


def delta_e_hex(a: str, b: str) -> float:
    return ciede2000(hex_to_lab(a), hex_to_lab(b))


def simulate(value: str, kind: str) -> str:
    """Simulér farveblindhed (Machado 2009) og returnér den sete farve som hex."""
    matrix = MACHADO[kind]
    lin = [srgb_to_linear(c) for c in hex_to_rgb(value)]
    out = tuple(linear_to_srgb(sum(m * c for m, c in zip(row, lin, strict=True))) for row in matrix)
    return rgb_to_hex(out)  # type: ignore[arg-type]


# ── Tjek ─────────────────────────────────────────────────────


def load_palette(path: Path) -> list[dict]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(f"{path.name}: forventede en liste")
    palette = []
    for row in data:
        if not isinstance(row, dict) or not {"id", "color", "color_dark"} <= row.keys():
            raise ValueError(f"{path.name}: hver kategori skal have id, color og color_dark")
        hex_to_rgb(str(row["color"]))
        hex_to_rgb(str(row["color_dark"]))
        palette.append({
            "id": str(row["id"]), "color": str(row["color"]), "color_dark": str(row["color_dark"]),
            "pending": row.get("pending") is True,
        })
    return palette


def pair_distances(colors: dict[str, str]) -> list[tuple[str, str, float]]:
    """Alle par (a, b, ΔE00), sorteret efter afstand."""
    pairs = [(a, b, delta_e_hex(colors[a], colors[b])) for a, b in itertools.combinations(colors, 2)]
    return sorted(pairs, key=lambda p: p[2])


def check_palette(palette: list[dict]) -> dict:
    """Kør alle tjek og returnér et resultat-dict (bruges af main og tests).

    Søskende med samme farve i begge tilstande måles som én farve (den første i paletten).
    Kategorier, der afventer, springes over.
    """
    unique: dict[tuple[str, str], dict] = {}
    siblings: list[tuple[str, str]] = []
    for p in palette:
        if p.get("pending"):
            continue
        key = (p["color"].upper(), p["color_dark"].upper())
        if key in unique:
            siblings.append((unique[key]["id"], p["id"]))
        else:
            unique[key] = p
    modes = {
        "lys": ({p["id"]: p["color"] for p in unique.values()}, LIGHT_BG),
        "mørk": ({p["id"]: p["color_dark"] for p in unique.values()}, DARK_BG),
    }
    result: dict = {
        "contrast": [], "contrast_fail": [], "delta_e": {}, "delta_e_low": {}, "cvd_low": {}, "siblings": siblings,
        "pending": [p["id"] for p in palette if p.get("pending")],
    }
    for mode, (colors, bg) in modes.items():
        for cid, color in colors.items():
            ratio = contrast_ratio(color, bg)
            row = (mode, cid, color, bg, ratio)
            result["contrast"].append(row)
            if ratio < MIN_CONTRAST:
                result["contrast_fail"].append(row)
        pairs = pair_distances(colors)
        result["delta_e"][mode] = pairs
        result["delta_e_low"][mode] = [p for p in pairs if p[2] < MIN_DELTA_E]
        for kind in MACHADO:
            seen = {cid: simulate(c, kind) for cid, c in colors.items()}
            low = [p for p in pair_distances(seen) if p[2] < MIN_DELTA_E_CVD]
            result["cvd_low"][(mode, kind)] = low
    return result


def _fmt_pairs(pairs: list[tuple[str, str, float]]) -> str:
    return ", ".join(f"{a}/{b} {d:.1f}" for a, b, d in pairs)


def print_report(result: dict, path: Path) -> None:
    print(f"Kategorifarver fra {path}")
    print()
    if result["siblings"]:
        names = ", ".join(f"{a}/{b}" for a, b in result["siblings"])
        print(f"Søskende med samme farve, skilt ad af ikonet: {names}")
        print()
    if result["pending"]:
        print(f"Afventer og vises gråt, så farven tjekkes ikke: {', '.join(result['pending'])}")
        print()
    print(f"Kontrast (mindst {MIN_CONTRAST:.0f}:1)")
    for mode, cid, color, bg, ratio in result["contrast"]:
        status = "ok" if ratio >= MIN_CONTRAST else "FEJL"
        print(f"  {mode:<5} {cid:<13} {color} mod {bg}  {ratio:5.2f}:1  {status}")
    print()
    print(f"CIEDE2000 mellem par (mindst {MIN_DELTA_E:.0f})")
    for mode, pairs in result["delta_e"].items():
        a, b, d = pairs[0]
        print(f"  {mode}: mindste afstand {d:.1f} ({a}/{b})")
        low = result["delta_e_low"][mode]
        if low:
            print(f"    under {MIN_DELTA_E:.0f}: {_fmt_pairs(low)}")
    print()
    print(f"Farveblindhed, Machado 2009 (par under {MIN_DELTA_E_CVD:.0f})")
    for (mode, kind), low in result["cvd_low"].items():
        text = _fmt_pairs(low) if low else "ingen"
        print(f"  {mode}, {kind}: {text}")
    print()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_colors", description="Tjek kategorifarverne.")
    parser.add_argument("--file", type=Path, default=CONFIG_DIR / "categories.yaml", help="categories.yaml")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="exit 1 også ved par under 20 (CIEDE2000) eller farveblind-par under 10",
    )
    args = parser.parse_args(argv)
    with contextlib.suppress(AttributeError, ValueError):
        sys.stdout.reconfigure(errors="replace")  # type: ignore[union-attr]

    try:
        palette = load_palette(args.file)
    except (OSError, ValueError, yaml.YAMLError) as exc:
        print(f"FEJL: {exc}", file=sys.stderr)
        return 1
    if sum(not p["pending"] for p in palette) < 2:
        print("FEJL: mindst to kategorier, der ikke afventer, kræves", file=sys.stderr)
        return 1

    result = check_palette(palette)
    print_report(result, args.file)

    n_contrast = len(result["contrast_fail"])
    n_delta = sum(len(v) for v in result["delta_e_low"].values())
    n_cvd = sum(len(v) for v in result["cvd_low"].values())
    print(
        f"Resultat: {n_contrast} kontrastfejl, {n_delta} par under {MIN_DELTA_E:.0f} (CIEDE2000), "
        f"{n_cvd} par under {MIN_DELTA_E_CVD:.0f} ved farveblindhed."
    )
    if n_contrast:
        return 1
    if args.strict and (n_delta or n_cvd):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
