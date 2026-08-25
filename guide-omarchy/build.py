#!/usr/bin/env python3
"""
Génération du PDF « Omarchy, le guide de mise en route ».

Chaîne : src/guide.html + src/guide.css  ->  Chromium (Playwright)  ->  PDF A4,
puis deux passes supplémentaires :

  1. les numéros de page du sommaire sont relevés dans le PDF de la 1re passe
     (recherche du marqueur « CHAPITRE n » / « ANNEXE X » dans le texte extrait),
     réinjectés dans le HTML, et le PDF est régénéré ;
  2. les signets (volet latéral du lecteur PDF) sont ajoutés avec pypdf.

Le sommaire lui-même est construit à partir du document : chaque
<div class="part"> et chaque <section class="chapter"> y entre automatiquement,
il n'y a donc rien à tenir à jour à la main.

Prérequis : pip install playwright pypdf   (Chromium doit déjà être présent ;
dans cet environnement il l'est via PLAYWRIGHT_BROWSERS_PATH).

Usage : python3 build.py
"""

from __future__ import annotations

import html
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src" / "guide.html"
OUT = ROOT / "guide-omarchy-fr.pdf"

# Les marges sont dans la règle @page de guide.css : une règle @page l'emporte
# sur le paramètre `margin` de page.pdf(), on ne le passe donc pas ici.
PDF_OPTS = dict(
    format="A4",
    print_background=True,
    display_header_footer=True,
    header_template="<div></div>",
    footer_template=(
        '<div style="width:100%;font-family:Liberation Sans,sans-serif;font-size:7pt;'
        'color:#8b98a5;padding:0 20mm 6mm;display:flex;justify-content:space-between;">'
        '<span>Omarchy&nbsp;4 &middot; guide de mise en route</span>'
        '<span class="pageNumber"></span></div>'
    ),
)

# --------------------------------------------------------------------------
# 1. lecture du document et extraction de sa structure
# --------------------------------------------------------------------------

PART_RE = re.compile(
    r'<div class="part">\s*<div class="kicker">(?P<kicker>.*?)</div>\s*'
    r'<h1 class="part-title">(?P<title>.*?)</h1>',
    re.S,
)
CHAP_RE = re.compile(
    r'<h2><span class="chapno">(?P<no>.*?)</span>(?P<title>.*?)</h2>', re.S
)


def strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ").strip()


def collapse(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def nospace(s: str) -> str:
    return re.sub(r"\s+", "", s)


def outline(doc: str) -> list[dict]:
    """Structure du document, dans l'ordre : parties et chapitres."""
    items = []
    for m in PART_RE.finditer(doc):
        items.append(
            {
                "kind": "part",
                "pos": m.start(),
                "kicker": collapse(strip_tags(m.group("kicker"))),
                "title": collapse(strip_tags(m.group("title")).replace("  ", " ")),
            }
        )
    for m in CHAP_RE.finditer(doc):
        no = collapse(strip_tags(m.group("no")))
        items.append(
            {
                "kind": "chapter",
                "pos": m.start(),
                "no": no,
                # marqueur recherché dans le texte du PDF (la CSS le met en capitales)
                "marker": no.upper(),
                "title": collapse(strip_tags(m.group("title"))),
            }
        )
    items.sort(key=lambda it: it["pos"])
    return items


def short_no(no: str) -> str:
    """« Chapitre 12 » -> « 12 » ; « Annexe A » -> « A » ; sinon rien."""
    m = re.search(r"(?:Chapitre|Annexe)\s+(\S+)", no, re.I)
    return m.group(1) if m else ""


def build_toc(items: list[dict], pages: dict[str, int] | None) -> str:
    """Le corps HTML du sommaire, avec les numéros de page s'ils sont connus."""
    rows = []
    for it in items:
        if it["kind"] == "chapter" and it["marker"].startswith("TABLE DES"):
            continue
        if it["kind"] == "part":
            rows.append(
                f'<div class="toc-part">{html.escape(it["kicker"])} &middot; '
                f'{html.escape(it["title"])}</div>'
            )
            continue
        n = short_no(it["no"])
        p = "" if pages is None else str(pages.get(it["marker"], ""))
        rows.append(
            '<div class="toc-row">'
            f'<span class="n">{html.escape(n)}</span>'
            f'<span class="t">{html.escape(it["title"])}</span>'
            '<span class="dots"></span>'
            f'<span class="p">{p}</span>'
            "</div>"
        )
    return "\n".join(rows)


TOC_BODY_RE = re.compile(r'(<div id="toc-body">).*?(</div>)', re.S)


def inject_toc(doc: str, body: str) -> str:
    new, n = TOC_BODY_RE.subn(lambda m: m.group(1) + body + m.group(2), doc, count=1)
    if not n:
        sys.exit('build: repère <div id="toc-body"> introuvable dans guide.html')
    return new


# --------------------------------------------------------------------------
# 2. rendu
# --------------------------------------------------------------------------


def chromium_path() -> str | None:
    """Chromium fourni par l'environnement, si la version épinglée par
    Playwright n'est pas celle qui est installée."""
    for cand in (
        Path("/opt/pw-browsers/chromium"),
        *sorted(Path("/opt/pw-browsers").glob("chromium-*/chrome-linux/chrome"), reverse=True),
    ):
        if cand.exists():
            return str(cand)
    return None


def render(doc: str, work: Path, pdf_path: Path) -> list[str]:
    """Écrit `doc` à côté de la CSS, l'imprime en PDF, renvoie les avertissements."""
    from playwright.sync_api import sync_playwright

    work.write_text(doc, encoding="utf-8")
    warnings: list[str] = []
    launch: dict = {"args": ["--no-sandbox"]}
    exe = chromium_path()
    if exe:
        launch["executable_path"] = exe

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch)
        page = browser.new_page()
        page.goto(work.as_uri(), wait_until="load")
        page.wait_for_timeout(400)

        # aucune image ne doit être cassée : c'est l'erreur qui passe le plus
        # facilement inaperçue dans un PDF de 80 pages
        broken = page.evaluate(
            "() => [...document.images]"
            ".filter(i => !i.complete || i.naturalWidth === 0)"
            ".map(i => i.getAttribute('src'))"
        )
        if broken:
            warnings.append("images cassées : " + ", ".join(broken))

        page.emulate_media(media="print")
        page.pdf(path=str(pdf_path), **PDF_OPTS)
        browser.close()

    return warnings


def page_numbers(pdf_path: Path, items: list[dict]) -> dict[str, int]:
    """Numéro de page de chaque chapitre, relevé dans le PDF déjà produit."""
    from pypdf import PdfReader

    reader = PdfReader(str(pdf_path))
    # le titre de chapitre est crénelé par la CSS (letter-spacing), ce que
    # l'extraction rend par « C H A P I T R E  7 » : on compare donc des
    # chaînes dont tous les blancs ont été retirés.
    texts = [nospace(pg.extract_text() or "") for pg in reader.pages]

    found: dict[str, int] = {}
    for it in items:
        if it["kind"] != "chapter":
            continue
        marker = nospace(it["marker"])
        for idx, text in enumerate(texts):
            # « CHAPITRE7 » ne doit pas être trouvé dans « CHAPITRE17 »
            if re.search(rf"{re.escape(marker)}(?!\d)", text):
                found[it["marker"]] = idx + 1
                break
    return found


def add_bookmarks(pdf_path: Path, items: list[dict], pages: dict[str, int]) -> None:
    from pypdf import PdfReader, PdfWriter

    reader = PdfReader(str(pdf_path))
    writer = PdfWriter()
    writer.append_pages_from_reader(reader)

    parent = None
    for it in items:
        if it["kind"] == "part":
            # une partie s'ouvre sur la page qui précède son premier chapitre
            first = next(
                (
                    pages.get(c["marker"])
                    for c in items
                    if c["kind"] == "chapter" and c["pos"] > it["pos"]
                ),
                None,
            )
            if not first:
                continue
            target = max(first - 2, 0)
            parent = writer.add_outline_item(f'{it["kicker"]} — {it["title"]}', target)
        else:
            p = pages.get(it["marker"])
            if not p:
                continue
            label = f'{short_no(it["no"])}. {it["title"]}' if short_no(it["no"]) else it["title"]
            writer.add_outline_item(label, p - 1, parent=parent)

    with open(pdf_path, "wb") as fh:
        writer.write(fh)


# --------------------------------------------------------------------------

def main() -> int:
    doc = SRC.read_text(encoding="utf-8")
    items = outline(doc)
    chapters = [i for i in items if i["kind"] == "chapter"]
    parts = [i for i in items if i["kind"] == "part"]
    print(f"structure : {len(parts)} parties, {len(chapters)} chapitres")

    work = SRC.with_name("_build.html")

    # passe 1 — sommaire sans numéros, pour relever la pagination
    pass1 = inject_toc(doc, build_toc(items, None))
    warnings = render(pass1, work, OUT)
    pages = page_numbers(OUT, items)

    missing = [c["marker"] for c in chapters if c["marker"] not in pages]
    if missing:
        warnings.append("chapitres non localisés dans le PDF : " + ", ".join(missing))

    # passe 2 — sommaire paginé (la largeur des numéros est fixe : pas de reflux)
    pass2 = inject_toc(doc, build_toc(items, pages))
    warnings += render(pass2, work, OUT)

    # la pagination a pu bouger d'un cheveu si le sommaire lui-même a changé
    # de longueur ; on la relève à nouveau pour les signets, qui, eux, sont
    # ajoutés après coup et ne déplacent rien.
    pages = page_numbers(OUT, items)
    add_bookmarks(OUT, items, pages)

    work.unlink(missing_ok=True)

    from pypdf import PdfReader

    n = len(PdfReader(str(OUT)).pages)
    size = OUT.stat().st_size / 1024 / 1024
    print(f"écrit : {OUT.name} — {n} pages, {size:.1f} Mo")

    for w in dict.fromkeys(warnings):
        print(f"  avertissement : {w}", file=sys.stderr)
    return 1 if warnings else 0


if __name__ == "__main__":
    raise SystemExit(main())
