#!/usr/bin/env python3
"""Generador del Centro de Documentacion de OpsForge (BJJ Vetusta / Asturkon).

Fuente unica: los ficheros Markdown de docs-site/content/ (con front matter).
Salidas (ambas desde la MISMA fuente, nunca mantenidas a mano por separado):
  1) Sitio estatico HTML  -> <repo>/nginx/conf.d/docs-site/  (lo sirve nginx)
  2) PDFs                 -> <repo>/nginx/conf.d/docs-site/*.pdf

Uso:
  python3 build.py            # construye todo
  python3 build.py --quiet

No usa red, no escribe fuera del directorio de salida, no toca contenedores.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
from datetime import datetime
import sys
import unicodedata
from pathlib import Path

import markdown
from fpdf import FPDF, FontFace

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
CONTENT = HERE / "content"
ASSETS = HERE / "assets"
OUT = REPO / "nginx" / "conf.d" / "docs-site"
SITE_TITLE = "Centro de documentacion OpsForge"
SITE_SUB = "BJJ Vetusta / Asturkon"

MD_EXTENSIONS = ["extra", "sane_lists", "toc"]
PDF_SAFE = {
    "\u2014": "-", "\u2013": "-", "\u2192": "->", "\u2190": "<-", "\u201c": '"',
    "\u201d": '"', "\u2018": "'", "\u2019": "'", "\u2026": "...", "\u00a0": " ",
    "\u2022": "-", "\u2265": ">=", "\u2264": "<=", "\u00b7": "-",
}


# ---------------------------------------------------------------- front matter
def parse_doc(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8")
    meta: dict[str, str] = {}
    body = raw
    if raw.startswith("---"):
        end = raw.find("\n---", 3)
        if end != -1:
            for line in raw[3:end].strip().splitlines():
                if ":" in line:
                    key, _, value = line.partition(":")
                    meta[key.strip()] = value.strip()
            body = raw[end + 4 :].lstrip("\n")
    doc = {
        "source": path.relative_to(CONTENT).as_posix(),
        "meta": meta,
        "body": body,
        "title": meta.get("title", path.stem),
        "short": meta.get("short", meta.get("title", path.stem)),
        "slug": meta.get("slug", path.stem),
        "version": meta.get("version", "v0.1"),
        "date": meta.get("date", ""),
        "project": meta.get("project", SITE_SUB),
        "state": meta.get("state", "Draft"),
        "order": int(meta.get("order", 99)),
        "a4": meta.get("a4", "").lower() == "true",
        "pdf": meta.get("pdf", ""),
        "is_index": path.name == "index.md",
    }
    doc["url"] = "/" if doc["is_index"] else f"/bjj/{doc['slug']}/"
    section = path.relative_to(CONTENT).parts[0]
    doc["section"] = "" if doc["is_index"] else section
    doc["html"] = markdown.markdown(doc["body"], extensions=MD_EXTENSIONS)
    doc["sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return doc


def load_docs() -> list[dict]:
    docs = [parse_doc(p) for p in sorted(CONTENT.rglob("*.md"))]
    return sorted(docs, key=lambda d: (d["is_index"] is False, d["section"], d["order"], d["title"]))


# ---------------------------------------------------------------------- layout
CSS_HREF = "/assets/style.css"


def nav(docs: list[dict], current: dict) -> str:
    items = []
    for doc in docs:
        if doc["is_index"]:
            continue
        active = ' class="active"' if doc["source"] == current["source"] else ""
        items.append(f'<li><a href="{doc["url"]}"{active}>{html.escape(doc["short"])}</a></li>')
    return "\n".join(items)


def badge(state: str) -> str:
    css = {"Draft": "draft", "Validated": "validated", "Published": "published"}.get(state, "draft")
    return f'<span class="badge badge-{css}">{html.escape(state)}</span>'


def page(docs: list[dict], doc: dict) -> str:
    pdf_link = ""
    if doc["pdf"]:
        pdf_link = f'<p class="pdflink">PDF: <a href="/{doc["pdf"]}">{doc["pdf"]}</a></p>'
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(doc['title'])} - {html.escape(SITE_TITLE)}</title>
<link rel="stylesheet" href="{CSS_HREF}">
</head>
<body>
<header class="top">
  <div class="wrap">
    <a class="brand" href="/">{html.escape(SITE_TITLE)}</a>
    <span class="sub">{html.escape(SITE_SUB)}</span>
  </div>
</header>
<div class="wrap layout">
  <nav class="side">
    <p class="navtitle">Manuales</p>
    <ul>
{nav(docs, doc)}
    </ul>
    <p class="navtitle">Ficheros</p>
    <ul>
      <li><a href="/#descargas">PDFs</a></li>
    </ul>
  </nav>
  <main class="content">
    <div class="docmeta">
      <span class="m"><b>Version</b> {html.escape(doc['version'])}</span>
      <span class="m"><b>Fecha</b> {html.escape(doc['date'])}</span>
      <span class="m"><b>Proyecto</b> {html.escape(doc['project'])}</span>
      <span class="m"><b>Estado</b> {badge(doc['state'])}</span>
    </div>
    {pdf_link}
    {doc['html']}
    <p class="footer">Generado desde <code>{html.escape(doc['source'])}</code>
    (sha256 {doc['sha256']}) por <code>docs-site/build.py</code>.</p>
  </main>
</div>
</body>
</html>
"""


def section_index(docs: list[dict], section: str) -> str:
    items = [d for d in docs if d["section"] == section and not d["is_index"]]
    lis = "\n".join(
        f'<li><a href="{d["url"]}">{html.escape(d["title"])}</a> {badge(d["state"])}'
        f' <span class="muted">{html.escape(d["version"])} - {html.escape(d["date"])}</span></li>'
        for d in items
    )
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(section)} - {html.escape(SITE_TITLE)}</title>
<link rel="stylesheet" href="{CSS_HREF}">
</head>
<body>
<header class="top"><div class="wrap"><a class="brand" href="/">{html.escape(SITE_TITLE)}</a>
<span class="sub">{html.escape(SITE_SUB)}</span></div></header>
<div class="wrap layout"><main class="content">
<h1>{html.escape(section.upper())}</h1>
<p>Documentacion de la seccion <b>{html.escape(section)}</b>.</p>
<ul>{lis}</ul>
</main></div>
</body>
</html>
"""


# ------------------------------------------------------------------------- PDFs
def pdf_safe(text: str) -> str:
    for src, dst in PDF_SAFE.items():
        text = text.replace(src, dst)
    out = []
    for ch in text:
        try:
            ch.encode("latin-1")
        except UnicodeEncodeError:
            out.append(unicodedata.normalize("NFKD", ch).encode("ascii", "ignore").decode() or "?")
        else:
            out.append(ch)
    return "".join(out)


def strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", fragment)


# Etiquetas que fpdf2.write_html entiende de forma fiable. El resto se retiran
# (se conserva el texto) para no degradar el resultado.
PDF_KEEP = {"p", "h1", "h2", "h3", "h4", "h5", "h6", "ul", "ol", "li", "table",
            "thead", "tbody", "tr", "td", "th", "b", "i", "u", "a", "br",
            "blockquote", "hr"}


def pdf_html(fragment: str) -> str:
    """Adapta el HTML del sitio al subconjunto que entiende write_html."""
    frag = fragment.replace("<code>", "").replace("</code>", "")
    frag = frag.replace("<strong>", "<b>").replace("</strong>", "</b>")
    frag = frag.replace("<em>", "<i>").replace("</em>", "</i>")
    # Los esquemas (SVG) viven solo en la version online: fpdf2 no los renderiza de
    # forma fiable. La leyenda en cursiva se conserva como nota.
    frag = re.sub(r"<img[^>]*>", "", frag)
    return drop_tags(frag, PDF_KEEP)


def drop_tags(fragment: str, keep: set[str]) -> str:
    """Retira las etiquetas que no esten en `keep` conservando su contenido."""
    def repl(match: re.Match) -> str:
        return match.group(0) if match.group(1).lower() in keep else ""
    return re.sub(r"<\s*/?\s*([a-zA-Z][a-zA-Z0-9]*)", repl, fragment)


def _pdf_shell(doc: dict) -> tuple[FPDF, float]:
    # La guia rapida debe caber en UNA cara A4: margenes y cuerpo mas ajustados.
    m = 9 if doc["a4"] else 13
    mt = 8 if doc["a4"] else 12
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_auto_page_break(auto=True, margin=mt)
    pdf.set_margins(m, mt, m)
    # Fecha de creacion fija (la del front matter) para que el PDF sea reproducible
    # byte a byte: sin esto, fpdf2 sella la hora del build y cada rebuild ensucia git.
    yyyy, mm, dd = (int(x) for x in doc["date"].split("-"))
    pdf.set_creation_date(datetime(yyyy, mm, dd, 0, 0, 0))
    pdf.set_title(pdf_safe(doc["title"]))
    pdf.set_author(pdf_safe(doc["project"]))
    pdf.set_creator("docs-site/build.py")
    pdf.add_page()
    size_head = 15 if not doc["a4"] else 12
    size_body = 10 if not doc["a4"] else 7.8
    # Cabecera comun: version, fecha, proyecto, estado (el titulo ya va aqui, asi
    # que el h1 del Markdown no se repite).
    pdf.set_font("helvetica", "B", size_head)
    pdf.multi_cell(0, 7 if not doc["a4"] else 6, pdf_safe(doc["title"]),
                   new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("helvetica", "", 8)
    pdf.set_text_color(90, 90, 90)
    pdf.multi_cell(0, 4.6, pdf_safe(
        f"{doc['project']}  |  Version {doc['version']}  |  {doc['date']}  |  Estado: {doc['state']}"),
        new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)
    # write_html usa el tamano de fuente actual como base: se fija el cuerpo.
    pdf.set_font("helvetica", "", size_body)
    return pdf, size_body


def _plain_cells(fragment: str) -> str:
    """Aplana el formato inline dentro de las celdas de tabla.

    fpdf2 rechaza cualquier etiqueta anidada dentro de <td>/<th> ("Unsupported
    nested HTML tags inside <td> element"), asi que las celdas quedan en texto.
    """
    def clean(match: re.Match) -> str:
        inner = re.sub(r"</?(?:b|i|u|a|span|small|code|br)(?:\s[^>]*)?>", " ", match.group(2))
        return match.group(1) + inner + match.group(3)
    return re.sub(r"(<t[hd][^>]*>)(.*?)(</t[hd]>)", clean, fragment, flags=re.S)


def _pdf_body_html(doc: dict) -> str:
    body = pdf_safe(pdf_html(doc["html"]))
    # El titulo ya esta en la cabecera del PDF.
    return re.sub(r"<h1>.*?</h1>", "", body, count=1, flags=re.S)


def build_pdf(doc: dict, dest: Path, quiet: bool) -> dict:
    """PDF desde la misma fuente Markdown (via su HTML, sin contenido duplicado).

    Estrategias en orden: HTML con celdas aplanadas -> HTML minimo -> texto plano.
    Cada intento parte de un PDF nuevo, de modo que un fallo no deja restos.
    """
    body = _pdf_body_html(doc)
    strategies = [
        ("celdas-planas", _plain_cells(body)),
        ("html-minimo", drop_tags(_plain_cells(body), {"p", "h1", "h2", "h3", "h4",
                                                       "ul", "ol", "li", "table",
                                                       "tr", "td", "th", "br"})),
    ]
    pdf: FPDF | None = None
    last_exc: Exception | None = None
    # La guia A4 necesita cabeceras mas compactas para caber en una sola cara.
    heading_styles = None
    if doc["a4"]:
        heading_styles = {tag: FontFace(size_pt=size) for tag, size in
                          (("h1", 11), ("h2", 9.2), ("h3", 8.2), ("h4", 7.8))}
    for name, html_body in strategies:
        try:
            pdf, _ = _pdf_shell(doc)
            pdf.write_html(html_body, font_family="helvetica", table_line_separators=False,
                           tag_styles=heading_styles)
            break
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            pdf = None
            if not quiet:
                print(f"  ! PDF estrategia '{name}' fallo: {exc}")
    if pdf is None:
        if not quiet:
            print(f"  ! PDF: se usa texto plano ({last_exc})")
        pdf, size_body = _pdf_shell(doc)
        pdf.set_font("helvetica", "", size_body)
        for chunk in re.split(r"\n{2,}", strip_tags(body)):
            text = " ".join(pdf_safe(chunk).split())
            if text:
                pdf.multi_cell(0, 4.8, text, new_x="LMARGIN", new_y="NEXT")
    dest.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(dest))
    return {"file": dest.name, "pages": pdf.pages_count, "bytes": dest.stat().st_size}


# ------------------------------------------------------------------------ main
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    quiet = args.quiet
    log = (lambda *a: None) if quiet else print

    if not CONTENT.is_dir():
        print(f"ERROR: no existe {CONTENT}", file=sys.stderr)
        return 2
    docs = load_docs()
    if not docs:
        print("ERROR: no hay documentos en content/", file=sys.stderr)
        return 2

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "assets").mkdir(parents=True, exist_ok=True)
    for asset in sorted(ASSETS.glob("*")):
        if asset.is_file():
            target = OUT / "assets" / asset.name
            target.write_bytes(asset.read_bytes())
            log(f"  asset  /assets/{asset.name}")

    for doc in docs:
        dest_dir = OUT / doc["url"].strip("/") if doc["url"] != "/" else OUT
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "index.html").write_text(page(docs, doc), encoding="utf-8")
        log(f"  html   {doc['url']}  <- {doc['source']}")

    for section in sorted({d["section"] for d in docs if d["section"]}):
        dest_dir = OUT / section
        dest_dir.mkdir(parents=True, exist_ok=True)
        (dest_dir / "index.html").write_text(section_index(docs, section), encoding="utf-8")
        log(f"  html   /{section}/  (indice de seccion)")

    manifest = {"site": SITE_TITLE, "docs": []}
    for doc in docs:
        entry = {
            "title": doc["title"], "url": doc["url"], "version": doc["version"],
            "date": doc["date"], "state": doc["state"], "source": doc["source"],
            "sha256": doc["sha256"], "pdf": doc["pdf"] or None,
        }
        if doc["pdf"]:
            info = build_pdf(doc, OUT / doc["pdf"], quiet)
            entry["pdf_pages"] = info["pages"]
            entry["pdf_bytes"] = info["bytes"]
            log(f"  pdf    /{info['file']}  ({info['pages']} pags, {info['bytes']} B)")
        manifest["docs"].append(entry)
    try:
        rev = subprocess.run(["git", "-C", str(REPO), "rev-parse", "--short", "HEAD"],
                             capture_output=True, text=True, timeout=10).stdout.strip()
    except Exception:  # noqa: BLE001
        rev = ""
    manifest["built_from_commit"] = rev or "unknown"
    (OUT / "docs-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    log(f"  manifest docs-manifest.json  (commit {manifest['built_from_commit']})")
    log(f"OK: {len(docs)} documentos -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
