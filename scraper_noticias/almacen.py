"""Base local (SQLite) y exportación del periodo.

La base guarda TODO lo descargado, sin filtrar: el filtro temático se aplica al
exportar. Así la misma base sirve para cualquier búsqueda posterior sin volver
a descargar nada.

Es acumulativa: los feeds de los medios grandes cubren uno o dos días, así que
la semana completa solo existe si se corre a diario y se va sumando.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS noticias (
  url TEXT PRIMARY KEY, id TEXT, medio TEXT, categoria TEXT, pais TEXT, origen TEXT, titulo TEXT,
  fecha TEXT, fecha_publicacion TEXT, autor TEXT,
  estado TEXT, motivo TEXT, n_caracteres INTEGER, cuerpo TEXT,
  descubierto TEXT, extraido TEXT);
CREATE INDEX IF NOT EXISTS ix_fecha ON noticias(fecha);
"""
COLUMNAS = ["url", "id", "medio", "categoria", "pais", "origen", "titulo", "fecha", "fecha_publicacion",
            "autor", "estado", "motivo", "n_caracteres", "cuerpo", "descubierto", "extraido"]
# Estados que no se reintentan. 'sin_cuerpo' sí: un bloqueo puede ser pasajero.
RESUELTOS = ("ok", "solo_titular", "fuera_periodo")
PUBLICABLES = ("ok", "solo_titular")


def id_noticia(url: str) -> str:
    return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]


class Almacen:
    def __init__(self, ruta: str | Path):
        Path(ruta).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(ruta))
        self.db.executescript(ESQUEMA)

    def resueltas(self, urls: list[str]) -> set[str]:
        out: set[str] = set()
        marcas = ",".join("?" * len(RESUELTOS))
        for i in range(0, len(urls), 500):
            lote = urls[i:i + 500]
            q = (f"SELECT url FROM noticias WHERE estado IN ({marcas}) "
                 f"AND url IN ({','.join('?' * len(lote))})")
            out.update(r[0] for r in self.db.execute(q, (*RESUELTOS, *lote)))
        return out

    def guardar(self, fila: dict) -> None:
        fila = {**fila, "id": id_noticia(fila["url"])}
        self.db.execute(
            f"INSERT OR REPLACE INTO noticias ({','.join(COLUMNAS)}) VALUES ({','.join('?' * len(COLUMNAS))})",
            [fila.get(c) for c in COLUMNAS])

    def confirmar(self) -> None:
        self.db.commit()

    def periodo(self, desde: str, hasta: str, medios: list[str] | None = None) -> list[dict]:
        marcas = ",".join("?" * len(PUBLICABLES))
        q = (f"SELECT {','.join(COLUMNAS)} FROM noticias WHERE estado IN ({marcas}) "
             "AND fecha BETWEEN ? AND ?")
        args = [*PUBLICABLES, desde, hasta]
        if medios is not None:
            q += f" AND medio IN ({','.join('?' * len(medios))})"
            args += medios
        cur = self.db.execute(q + " ORDER BY fecha DESC, medio, titulo", args)
        return [dict(zip(COLUMNAS, r)) for r in cur]

    def exportar(self, carpeta: str | Path, desde: str, hasta: str, medios: list[str] | None = None,
                 filtro=None, filtrados: set[str] | None = None,
                 etiqueta: str = "") -> tuple[Path, Path, int, int]:
        """JSONL con el cuerpo completo y CSV liviano (sin cuerpo) para hoja de cálculo.

        `filtro` (FiltroTemas) descarta de la exportación lo que no casa, en los
        medios de `filtrados` (None = en todos). Con filtro, cada fila lleva
        además terminos / menciones / densidad / en_titulo.
        Devuelve (jsonl, csv, exportadas, descartadas_por_filtro).
        """
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        filas, fuera = [], 0
        for r in self.periodo(desde, hasta, medios):
            if filtro is not None:
                rel = filtro.evaluar(r["titulo"] or "", r["cuerpo"] or "")
                r.update(terminos=", ".join(rel.terminos[:8]), menciones=rel.menciones,
                         densidad=rel.densidad, en_titulo=int(rel.en_titulo))
                if (filtrados is None or r["medio"] in filtrados) and not rel.pasa:
                    fuera += 1
                    continue
            filas.append(r)
        base = str(carpeta / f"noticias_{desde}_a_{hasta}") + (f"_{etiqueta}" if etiqueta else "")
        pj, pc = Path(base + ".jsonl"), Path(base + ".csv")
        with open(pj, "w", encoding="utf-8") as f:
            for r in filas:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        extra = ["terminos", "menciones", "densidad", "en_titulo"] if filtro is not None else []
        cols = [c for c in COLUMNAS if c not in ("cuerpo", "motivo", "descubierto")] + extra + ["extracto"]
        with open(pc, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in filas:
                w.writerow({**r, "extracto": " ".join((r.get("cuerpo") or "").split())[:300]})
        return pj, pc, len(filas), fuera
