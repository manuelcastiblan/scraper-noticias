"""Base local (SQLite) y exportación del periodo.

La base es acumulativa: los feeds de los medios grandes cubren uno o dos días,
así que la semana completa solo existe si se corre a diario y se va sumando.
También evita volver a descargar lo que ya se resolvió.
"""
from __future__ import annotations

import csv
import hashlib
import json
import sqlite3
from pathlib import Path

ESQUEMA = """
CREATE TABLE IF NOT EXISTS noticias (
  url TEXT PRIMARY KEY, id TEXT, medio TEXT, categoria TEXT, origen TEXT, titulo TEXT,
  fecha TEXT, fecha_publicacion TEXT, autor TEXT, terminos TEXT,
  menciones INTEGER, densidad REAL, en_titulo INTEGER,
  estado TEXT, motivo TEXT, n_caracteres INTEGER, cuerpo TEXT,
  descubierto TEXT, extraido TEXT);
CREATE INDEX IF NOT EXISTS ix_fecha ON noticias(fecha);
"""
COLUMNAS = ["url", "id", "medio", "categoria", "origen", "titulo", "fecha", "fecha_publicacion",
            "autor", "terminos", "menciones", "densidad", "en_titulo", "estado", "motivo", "n_caracteres", "cuerpo", "descubierto", "extraido"]
# Estados que no se reintentan. 'sin_cuerpo' sí: un bloqueo puede ser pasajero.
RESUELTOS = ("ok", "solo_titular", "descartado_tema", "fuera_periodo")
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

    def periodo(self, desde: str, hasta: str) -> list[dict]:
        marcas = ",".join("?" * len(PUBLICABLES))
        cur = self.db.execute(
            f"SELECT {','.join(COLUMNAS)} FROM noticias WHERE estado IN ({marcas}) "
            "AND fecha BETWEEN ? AND ? ORDER BY fecha DESC, medio, titulo", (*PUBLICABLES, desde, hasta))
        return [dict(zip(COLUMNAS, r)) for r in cur]

    def exportar(self, carpeta: str | Path, desde: str, hasta: str) -> tuple[Path, Path, int]:
        """JSONL con el cuerpo completo y CSV liviano (sin cuerpo) para hoja de cálculo."""
        carpeta = Path(carpeta)
        carpeta.mkdir(parents=True, exist_ok=True)
        filas = self.periodo(desde, hasta)
        base = carpeta / f"noticias_{desde}_a_{hasta}"
        pj, pc = base.with_suffix(".jsonl"), base.with_suffix(".csv")
        with open(pj, "w", encoding="utf-8") as f:
            for r in filas:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        cols = [c for c in COLUMNAS if c not in ("cuerpo", "motivo", "descubierto")] + ["extracto"]
        with open(pc, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
            w.writeheader()
            for r in filas:
                w.writerow({**r, "extracto": " ".join((r.get("cuerpo") or "").split())[:300]})
        return pj, pc, len(filas)
