"""Descubrimiento de artículos: RSS, sitemaps y titulares de Google News."""
from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import unescape

import feedparser

from .config import Fuente, Medio
from .red import Red
from .texto import a_datetime, en_periodo, titulo_de_slug


@dataclass
class Candidato:
    url: str
    titulo: str
    medio: str
    categoria: str
    origen: str                    # RSS | SITEMAP | GNEWS
    publicado: datetime | None
    fecha_fiable: bool = True      # False si viene de <lastmod> (cambia al editar la nota)
    pais: str = ""

    @property
    def fecha(self) -> date | None:
        return self.publicado.date() if self.publicado else None


@dataclass
class Diagnostico:
    medio: str
    fuente: str
    leidos: int = 0
    en_periodo: int = 0
    elegidos: int = 0
    error: str | None = None


def _cdata(s: str) -> str:
    s = s.strip()
    m = re.match(r"^<!\[CDATA\[(.*)\]\]>$", s, re.S)
    return unescape((m.group(1) if m else s).strip())


def _etq(bloque: str, nombre: str) -> str | None:
    m = re.search(rf"<{nombre}(?:\s[^>]*)?>(.*?)</{nombre}>", bloque, re.S)
    return _cdata(m.group(1)) if m else None


def _pasa_url(u: str, f: Fuente) -> bool:
    if f.incluir and not any(s in u for s in f.incluir):
        return False
    return not any(s in u for s in f.excluir)


def _elegir(items: list[Candidato], f: Fuente) -> list[Candidato]:
    """Cuota: primero las secciones prioritarias, después se rellena por fecha."""
    orden = lambda c: c.publicado.timestamp() if c.publicado else 0.0
    items = sorted(items, key=orden, reverse=True)
    if f.prioritarias:
        prio = [c for c in items if any(s in c.url for s in f.prioritarias)]
        resto = [c for c in items if c not in prio]
        items = prio + resto
    return items[:f.tope]


def leer_rss(xml: str, tz) -> list[tuple[str, str, datetime | None]]:
    out = []
    for e in feedparser.parse(xml).entries:
        u = e.get("link")
        if not u:
            continue
        out.append((u.strip(), (e.get("title") or "").strip(),
                    a_datetime(e.get("published") or e.get("updated"), tz)))
    return out


def leer_sitemap(xml: str, tz) -> tuple[list[tuple[str, str, datetime | None, bool]], list[str]]:
    """Devuelve (urls, sitemaps_hijos). Cada url: (loc, titulo, fecha, fecha_fiable)."""
    if "<sitemapindex" in xml:
        return [], [_cdata(l) for l in re.findall(r"<loc>(.*?)</loc>", xml, re.S)]
    out = []
    for b in re.findall(r"<url>(.*?)</url>", xml, re.S):
        loc = _etq(b, "loc")
        if not loc:
            continue
        pub, mod = _etq(b, "news:publication_date"), _etq(b, "lastmod")
        out.append((loc, _etq(b, "news:title") or "", a_datetime(pub or mod, tz), bool(pub)))
    return out, []


def _meses(desde: date, hasta: date) -> list[str]:
    out, d = [], desde.replace(day=1)
    while d <= hasta:
        out.append(d.strftime("%Y%m"))
        d = (d + timedelta(days=32)).replace(day=1)
    return out


def descubrir_fuente(m: Medio, f: Fuente, red: Red, desde: date, hasta: date, tz,
                     pais: str = "AR") -> tuple[list[Candidato], Diagnostico]:
    diag = Diagnostico(m.nombre, f"{f.tipo}:{(f.url or f.consulta)[-48:]}")
    crudos: list[Candidato] = []
    try:
        if f.tipo == "rss":
            for pag in range(1, max(1, f.paginas) + 1):
                u = f.url if pag == 1 else f.url + ("&" if "?" in f.url else "?") + f"paged={pag}"
                try:
                    filas = leer_rss(red.get(u), tz)
                except Exception:
                    if pag == 1:
                        raise
                    break
                if not filas:
                    break
                for link, tit, pub in filas:
                    crudos.append(Candidato(link, tit, m.nombre, m.categoria, "RSS", pub, True, m.pais))
                fechas = [p.date() for _, _, p in filas if p]
                if fechas and min(fechas) < desde:   # ya salimos del periodo
                    break
        elif f.tipo == "sitemap":
            # '{AAAAMM}' en la URL se expande a cada mes del periodo.
            urls = ([f.url.replace("{AAAAMM}", ym) for ym in _meses(desde, hasta)]
                    if "{AAAAMM}" in f.url else [f.url])
            vistos = 0
            while urls and vistos < 12:
                u = urls.pop(0); vistos += 1
                filas, hijos = leer_sitemap(red.get(u, timeout=90), tz)
                urls.extend(hijos)
                for loc, tit, pub, fiable in filas:
                    crudos.append(Candidato(loc, tit or titulo_de_slug(loc), m.nombre, m.categoria,
                                            "SITEMAP", pub, fiable, m.pais))
        elif f.tipo == "gnews":
            # Solo titulares: Google News no entrega la URL real del artículo y el
            # sitio de origen no admite clientes automáticos, así que no hay cuerpo.
            q = f"{f.consulta} after:{desde.isoformat()} before:{(hasta + timedelta(days=1)).isoformat()}"
            u = ("https://news.google.com/rss/search?q=" + urllib.parse.quote(q)
                 + f"&hl=es-419&gl={pais}&ceid={pais}:es-419")
            for link, tit, pub in leer_rss(red.get(u, timeout=30), tz):
                tit = re.sub(rf"\s+-\s+{re.escape(m.nombre)}\s*$", "", tit, flags=re.I)
                crudos.append(Candidato(link, tit, m.nombre, m.categoria, "GNEWS", pub, True, m.pais))
    except Exception as e:
        diag.error = f"{type(e).__name__} {str(e)[:60]}"
        return [], diag
    diag.leidos = len(crudos)
    dentro = [c for c in crudos if _pasa_url(c.url, f) and en_periodo(c.fecha, desde, hasta)]
    diag.en_periodo = len(dentro)
    elegidos = _elegir(dentro, f)
    diag.elegidos = len(elegidos)
    return elegidos, diag
