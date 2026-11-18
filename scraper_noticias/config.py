"""Carga del archivo de medios (TOML)."""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .red import UA_DEFECTO

TIPOS = {"rss", "sitemap", "gnews"}


@dataclass
class Fuente:
    tipo: str
    url: str = ""
    consulta: str = ""                 # solo gnews
    paginas: int = 1                   # rss de WordPress: ?paged=2..N
    incluir: tuple[str, ...] = ()      # la URL debe contener alguna
    excluir: tuple[str, ...] = ()      # la URL no debe contener ninguna
    prioritarias: tuple[str, ...] = () # secciones que entran primero al tope
    tope: int = 200


@dataclass
class Medio:
    nombre: str
    categoria: str = ""
    filtrar: bool = False              # aplicar el filtro temático al cuerpo
    fuentes: list[Fuente] = field(default_factory=list)


@dataclass
class Config:
    medios: list[Medio]
    terminos: list[str]
    min_menciones: int = 3
    densidad_min: float = 2.0
    zona_horaria: str = "America/Argentina/Buenos_Aires"
    dias: int = 7
    user_agent: str = UA_DEFECTO
    respetar_robots: bool = True
    por_host: int = 3
    pausa: float = 0.3
    hilos: int = 12
    min_cuerpo: int = 300
    max_html: int = 3_000_000
    timeout: int = 20
    pais_gnews: str = "AR"


def cargar(ruta: str | Path) -> Config:
    with open(ruta, "rb") as f:
        d = tomllib.load(f)
    g, t = d.get("general", {}), d.get("temas", {})
    medios = []
    for m in d.get("medio", []):
        fuentes = []
        for f in m.get("fuente", []):
            if f.get("tipo") not in TIPOS:
                raise ValueError(f"{m.get('nombre')}: tipo de fuente desconocido {f.get('tipo')!r}")
            fuentes.append(Fuente(
                tipo=f["tipo"], url=f.get("url", ""), consulta=f.get("consulta", ""),
                paginas=int(f.get("paginas", 1)),
                incluir=tuple(f.get("incluir", ())), excluir=tuple(f.get("excluir", ())),
                prioritarias=tuple(f.get("prioritarias", ())), tope=int(f.get("tope", 200))))
        if not fuentes:
            raise ValueError(f"{m.get('nombre')}: sin fuentes")
        medios.append(Medio(nombre=m["nombre"], categoria=m.get("categoria", ""),
                            filtrar=bool(m.get("filtrar", False)), fuentes=fuentes))
    if not medios:
        raise ValueError("el archivo no define ningún [[medio]]")
    if any(m.filtrar for m in medios) and not t.get("terminos"):
        raise ValueError("hay medios con filtrar=true pero [temas].terminos está vacío")
    return Config(
        medios=medios, terminos=list(t.get("terminos", [])),
        min_menciones=int(t.get("min_menciones", 3)),
        densidad_min=float(t.get("densidad_min", 2.0)),
        **{k: g[k] for k in ("zona_horaria", "dias", "user_agent", "respetar_robots", "por_host",
                             "pausa", "hilos", "min_cuerpo", "max_html", "timeout", "pais_gnews")
           if k in g})
