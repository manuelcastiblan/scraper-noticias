"""Descarga del artículo y extracción del cuerpo."""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from html import unescape

import trafilatura

from .red import Red

# Señales de muro anti-bot. Solo se consultan cuando NO salió un cuerpo utilizable.
BLOQUEO_RX = re.compile(
    r"rate exceeded|checking your browser|are you a robot|just a moment|"
    r"habilit\w* javascript|enable javascript|acceso denegado|403 forbidden|captcha", re.I)


@dataclass
class Extraccion:
    cuerpo: str | None = None
    titulo: str | None = None
    autor: str | None = None
    fecha: str | None = None      # YYYY-MM-DD según los metadatos de la página
    motivo: str | None = None     # por qué no hay cuerpo


_LD_RX = re.compile(r'"articleBody"\s*:\s*"((?:[^"\\]|\\.)*)"')


def cuerpo_jsonld(html: str) -> str:
    """El texto que el propio medio declara en sus datos estructurados (schema.org)."""
    mejor = ""
    for m in _LD_RX.finditer(html):
        try:
            t = json.loads('"' + m.group(1) + '"')
        except Exception:
            continue
        t = re.sub(r"<[^>]+>", " ", unescape(t)).strip()
        if len(t) > len(mejor):
            mejor = t
    return mejor


def extraer_html(html: str, min_cuerpo: int = 300) -> Extraccion:
    """trafilatura con metadatos; contraste con el articleBody de la página y,
    si no hay cuerpo, respaldo juntando los <p>."""
    ex = _extraer_base(html, min_cuerpo)
    # trafilatura a veces se queda con el primer bloque (medido: una nota de
    # Semana con 623 caracteres de 2.181). Si el medio declara un articleBody
    # claramente más largo, ese es el artículo completo.
    ld = cuerpo_jsonld(html)
    if len(ld) >= min_cuerpo and len(ld) > 1.25 * len(ex.cuerpo or ""):
        ex.cuerpo = ld
    return ex


def _extraer_base(html: str, min_cuerpo: int) -> Extraccion:
    ex = Extraccion()
    try:
        crudo = trafilatura.extract(html, output_format="json", with_metadata=True,
                                    include_comments=False, include_tables=False, favor_recall=True)
        if crudo:
            j = json.loads(crudo)
            ex.cuerpo = (j.get("text") or j.get("raw_text") or "").strip() or None
            ex.titulo = (j.get("title") or "").strip() or None
            ex.autor = (j.get("author") or "").strip() or None
            f = (j.get("date") or "")[:10]
            ex.fecha = f if re.match(r"^\d{4}-\d{2}-\d{2}$", f) else None
    except Exception:
        pass
    if ex.cuerpo and len(ex.cuerpo) >= min_cuerpo:
        return ex
    ps = re.findall(r"<p[^>]*>(.*?)</p>", html, re.S | re.I)
    limpios = [re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", p))).strip() for p in ps]
    alt = "\n".join(p for p in limpios if len(p) > 40)
    if len(alt) > len(ex.cuerpo or ""):
        ex.cuerpo = alt
    return ex


def extraer_url(url: str, red: Red, min_cuerpo: int = 300, max_html: int = 3_000_000,
                timeout: int = 20) -> Extraccion:
    if not red.permitido(url):
        return Extraccion(motivo="robots")
    for intento in range(2):
        try:
            html = red.get(url, timeout=timeout, html=True)
        except Exception as e:
            if intento == 0:
                time.sleep(2)
                continue
            cod = getattr(e, "code", None)
            return Extraccion(motivo=f"http_{cod}" if cod else f"red_{type(e).__name__}")
        if len(html) > max_html:
            return Extraccion(motivo="html_gigante")   # portadas y liveblogs
        ex = extraer_html(html, min_cuerpo)
        if ex.cuerpo and len(ex.cuerpo) >= min_cuerpo:
            return ex
        bloqueado = bool(BLOQUEO_RX.search(ex.cuerpo or "")) or bool(BLOQUEO_RX.search(html[:4000]))
        if bloqueado and intento == 0:
            time.sleep(5)
            continue
        return Extraccion(motivo="bloqueado" if bloqueado else "cuerpo_corto")
    return Extraccion(motivo="agotado")
