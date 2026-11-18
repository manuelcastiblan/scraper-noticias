"""Normalización de texto, fechas y filtro temático."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


def norm(t: str | None) -> str:
    """Minúsculas, sin tildes, solo [a-z0-9 ] con espacios simples."""
    if not t:
        return ""
    t = unicodedata.normalize("NFKD", str(t).lower().strip())
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()


def zona(nombre: str):
    """Zona horaria por nombre; si no hay base tz instalada cae a UTC-3 fijo."""
    if ZoneInfo is not None:
        try:
            return ZoneInfo(nombre)
        except Exception:
            pass
    return timezone(timedelta(hours=-3))


_FRAC = re.compile(r"\.\d+")


def a_datetime(s: str | None, tz) -> datetime | None:
    """Convierte una fecha RFC 822 (RSS) o ISO 8601 (sitemaps) a datetime en `tz`.

    Una fecha sin hora ni zona ('2026-11-18') se toma como fecha local.
    """
    if not s:
        return None
    s = s.strip()
    if not s:
        return None
    dt = None
    if re.match(r"^\d{4}-\d{2}-\d{2}", s):
        iso = _FRAC.sub("", s).replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(iso)
        except ValueError:
            try:
                dt = datetime.fromisoformat(iso[:10])
            except ValueError:
                return None
        if dt.tzinfo is None:
            return dt.replace(tzinfo=tz)
    else:
        try:
            dt = parsedate_to_datetime(s)
        except Exception:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(tz)


def en_periodo(d: date | None, desde: date, hasta: date) -> bool:
    return d is not None and desde <= d <= hasta


def titulo_de_slug(url: str) -> str:
    s = url.rstrip("/").split("/")[-1]
    s = re.sub(r"\.html?$", "", s)
    s = re.sub(r"(_\d+_[A-Za-z0-9_-]+|-n\d+|-[a-z0-9]{6})$", "", s)
    return s.replace("-", " ").strip().capitalize()


class FiltroTemas:
    """Filtro de recall por términos, sobre texto normalizado.

    Cada término casa como palabra o frase completa ('gas' no casa en 'gasto');
    con asterisco final casa como prefijo ('miner*' -> minería, minera, mineros).
    Un artículo pasa si algún término está en el título, o si el cuerpo tiene al
    menos `min_menciones` apariciones Y una densidad de `densidad_min` por cada
    1000 caracteres. El conteo solo no sirve: medido sobre 500 notas de
    generalistas, una nota larga de macroeconomía junta 5-10 menciones sueltas
    ('energía', 'YPF' en una lista de acciones) sin tratar del sector; lo que
    separa es la densidad (ruido < 1, notas del sector > 2).
    """

    def __init__(self, terminos: list[str], min_menciones: int = 3, densidad_min: float = 2.0):
        self.min_menciones = max(1, int(min_menciones))
        self.densidad_min = float(densidad_min)
        self.patrones: list[tuple[str, re.Pattern]] = []
        for t in terminos:
            prefijo = t.strip().endswith("*")
            n = norm(t)
            if not n:
                continue
            rx = r"\b" + r"\s+".join(map(re.escape, n.split())) + (r"\w*" if prefijo else r"\b")
            self.patrones.append((t.strip().rstrip("*"), re.compile(rx)))

    def evaluar(self, titulo: str, cuerpo: str) -> "Relevancia":
        t, c = norm(titulo), norm(cuerpo)
        en_titulo, conteo = [], {}
        for nombre, rx in self.patrones:
            if rx.search(t):
                en_titulo.append(nombre)
            n = len(rx.findall(c))
            if n:
                conteo[nombre] = n
        terminos = sorted(set(en_titulo) | set(conteo), key=lambda k: -conteo.get(k, 0))
        menciones = sum(conteo.values())
        densidad = round(menciones * 1000 / max(1, len(c)), 2)
        pasa = bool(en_titulo) or (menciones >= self.min_menciones and densidad >= self.densidad_min)
        return Relevancia(pasa, terminos, menciones, densidad, bool(en_titulo))


class Relevancia:
    __slots__ = ("pasa", "terminos", "menciones", "densidad", "en_titulo")

    def __init__(self, pasa: bool, terminos: list[str], menciones: int, densidad: float, en_titulo: bool):
        self.pasa, self.terminos, self.menciones = pasa, terminos, menciones
        self.densidad, self.en_titulo = densidad, en_titulo
