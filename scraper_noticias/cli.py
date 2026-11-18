"""Orquestación: descubrir -> descargar -> guardar -> filtrar al exportar."""
from __future__ import annotations

import argparse
import dataclasses
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path

from .almacen import Almacen
from .config import cargar
from .descubrir import Candidato, descubrir_fuente
from .extraer import extraer_url
from .red import Red, dominio
from .texto import FiltroTemas, norm, zona


def _args(argv=None):
    p = argparse.ArgumentParser(prog="scraper_noticias", description="Scraper de noticias por RSS y sitemaps.")
    p.add_argument("--medios", default="medios.toml", help="archivo de medios (TOML)")
    p.add_argument("--buscar", help='términos separados por coma; exporta solo lo que los mencione '
                                    '(--buscar "Primo Gay,Macho Viejo")')
    p.add_argument("--desde", help="YYYY-MM-DD; por defecto hoy menos --dias")
    p.add_argument("--hasta", help="YYYY-MM-DD; por defecto hoy")
    p.add_argument("--dias", type=int, help="ventana si no se dan fechas (por defecto, la del archivo)")
    p.add_argument("--solo", help="nombres de medios separados por coma")
    p.add_argument("--pais", help="códigos de país separados por coma (AR,CO)")
    p.add_argument("--categoria", help="categorías separadas por coma (generalista,mineria,energia...)")
    p.add_argument("--salida", default="datos", help="carpeta de la base y las exportaciones")
    p.add_argument("--solo-descubrir", action="store_true", help="cuenta candidatos por fuente y no descarga nada")
    p.add_argument("--listar", action="store_true", help="con --solo-descubrir, imprime cada candidato")
    p.add_argument("--sin-filtro", action="store_true", help="ignora el filtro [temas] del archivo")
    return p.parse_args(argv)


def main(argv=None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except Exception:
            pass
    a = _args(argv)
    cfg = cargar(a.medios)
    tz = zona(cfg.zona_horaria)
    hoy = datetime.now(tz).date()
    hasta = date.fromisoformat(a.hasta) if a.hasta else hoy
    desde = date.fromisoformat(a.desde) if a.desde else hasta - timedelta(days=a.dias or cfg.dias)
    if desde > hasta:
        print("ERROR: --desde es posterior a --hasta"); return 2

    # ------------------------------------------------------ selección de medios
    medios = cfg.medios
    if a.solo:
        pedidos = {norm(x) for x in a.solo.split(",")}
        medios = [m for m in medios if norm(m.nombre) in pedidos]
    if a.pais:
        pedidos = {x.strip().upper() for x in a.pais.split(",")}
        medios = [m for m in medios if m.pais.upper() in pedidos]
    if a.categoria:
        pedidos = {norm(x) for x in a.categoria.split(",")}
        medios = [m for m in medios if norm(m.categoria) in pedidos]

    # ------------------------------------------------------------------ filtro
    # --buscar manda: cualquier mención, en todos los medios. Si no, el [temas]
    # del archivo sobre los medios con filtrar=true. Si no hay ninguno, sin filtro.
    buscar = [t.strip() for t in (a.buscar or "").split(",") if t.strip()]
    filtro, filtrados, etiqueta = None, None, ""
    if buscar:
        filtro = FiltroTemas(buscar, 1, 0.0)
        etiqueta = re.sub(r"\s+", "-", norm(" ".join(buscar)))[:40]
    elif cfg.terminos and not a.sin_filtro:
        filtro = FiltroTemas(cfg.terminos, cfg.min_menciones, cfg.densidad_min)
        filtrados = {m.nombre for m in medios if m.filtrar}

    # Las fuentes gnews con '{buscar}' en la consulta solo existen cuando hay --buscar.
    consulta = " OR ".join(f'"{t}"' for t in buscar)
    armados = []
    for m in medios:
        fuentes = []
        for f in m.fuentes:
            if "{buscar}" in f.consulta:
                if not buscar:
                    continue
                f = dataclasses.replace(f, consulta=f.consulta.replace("{buscar}", consulta))
            fuentes.append(f)
        if fuentes:
            armados.append(dataclasses.replace(m, fuentes=fuentes))
    medios = armados
    if not medios:
        print("ERROR: la selección (--solo / --pais / --categoria) no deja ningún medio de", a.medios); return 2
    red = Red(cfg.user_agent, cfg.por_host, cfg.pausa, cfg.respetar_robots)

    # ------------------------------------------------------------ 1) descubrir
    print(f"=== PERIODO {desde} a {hasta} ({cfg.zona_horaria}) | {len(medios)} medios ===")
    print("\n=== DESCUBRIMIENTO ===")
    cand: dict[str, Candidato] = {}
    por_medio: Counter = Counter()
    tareas = [(m, f) for m in medios for f in m.fuentes]
    with ThreadPoolExecutor(max_workers=min(8, len(tareas))) as ex:
        for items, d in ex.map(lambda t: descubrir_fuente(t[0], t[1], red, desde, hasta, tz, cfg.pais_gnews), tareas):
            if d.error:
                print(f"  {d.medio:<18} {d.fuente:<54} ERROR {d.error}"); continue
            nuevos = 0
            for c in items:
                if c.url not in cand:
                    cand[c.url] = c; nuevos += 1
            por_medio[d.medio] += nuevos
            print(f"  {d.medio:<18} {d.fuente:<54} {d.leidos:>5} leídos | {d.en_periodo:>4} en periodo | +{nuevos}")
    vacios = [m.nombre for m in medios if not por_medio[m.nombre]]
    if vacios:
        print(f"  *** SIN CANDIDATOS: {', '.join(vacios)} -- revisar el feed, no asumir que no hubo noticias.")
    # mismo titular repetido dentro de un medio (rss + sitemap con URL distinta)
    vistos, candidatos = set(), []
    for c in cand.values():
        k = (c.medio, norm(c.titulo))
        if k[1] and k in vistos:
            continue
        vistos.add(k); candidatos.append(c)
    print(f"TOTAL candidatos: {len(candidatos)} | {dict(Counter(c.medio for c in candidatos))}")
    if a.solo_descubrir:
        if a.listar:
            for c in sorted(candidatos, key=lambda c: (c.medio, str(c.fecha)), reverse=True):
                print(f"  {c.fecha} {c.medio:<16} {c.titulo[:70]:<70} {c.url}")
        return 0

    # --------------------------------------------------------------- 2) descargar
    alm = Almacen(Path(a.salida) / "noticias.db")
    ya = alm.resueltas([c.url for c in candidatos])
    pendientes = [c for c in candidatos if c.url not in ya]
    print(f"\n=== EXTRACCIÓN === {len(pendientes)} por descargar ({len(ya)} ya resueltas en la base)")
    ahora = lambda: datetime.now(tz).isoformat(timespec="seconds")
    cuenta: Counter = Counter()
    fallos: dict[str, Counter] = {}
    ok_medio: Counter = Counter()

    def _base(c: Candidato) -> dict:
        return {"url": c.url, "medio": c.medio, "categoria": c.categoria, "pais": c.pais, "origen": c.origen,
                "titulo": c.titulo, "fecha": c.fecha.isoformat() if c.fecha else None,
                "fecha_publicacion": c.publicado.isoformat(timespec="seconds") if c.publicado else None,
                "descubierto": ahora()}

    def _procesar(c: Candidato):
        if c.origen == "GNEWS":
            return c, None
        return c, extraer_url(c.url, red, cfg.min_cuerpo, cfg.max_html, cfg.timeout)

    with ThreadPoolExecutor(max_workers=cfg.hilos) as ex:
        futuros = [ex.submit(_procesar, c) for c in pendientes]
        for n, fut in enumerate(as_completed(futuros), 1):
            c, e = fut.result()
            fila = _base(c)
            if e is None:
                fila.update(estado="solo_titular", motivo="sin acceso al cuerpo")
            elif e.motivo:
                fila.update(estado="sin_cuerpo", motivo=e.motivo)
                fallos.setdefault(e.motivo, Counter())[dominio(c.url)] += 1
            else:
                # El <lastmod> de un sitemap cambia al editar la nota: manda la fecha de la página.
                if not c.fecha_fiable and e.fecha:
                    fila["fecha"] = e.fecha
                if e.titulo and (c.origen == "SITEMAP" or not c.titulo):
                    fila["titulo"] = e.titulo
                fila.update(autor=e.autor, cuerpo=e.cuerpo, n_caracteres=len(e.cuerpo), extraido=ahora())
                if not (desde.isoformat() <= (fila["fecha"] or "") <= hasta.isoformat()):
                    fila.update(estado="fuera_periodo", cuerpo=None)
                else:
                    fila["estado"] = "ok"; ok_medio[c.medio] += 1
            cuenta[fila["estado"]] += 1
            alm.guardar(fila)
            if n % 100 == 0:
                alm.confirmar(); print(f"  ... {n}/{len(pendientes)}")
    alm.confirmar()

    # ---------------------------------------------------------------- 3) embudo
    print(f"\nEMBUDO: {len(pendientes)} descargas intentadas")
    print(f"  -{cuenta['sin_cuerpo']:>4} sin cuerpo utilizable")
    for motivo, doms in sorted(fallos.items(), key=lambda x: -sum(x[1].values())):
        print(f"        {motivo:<18} {sum(doms.values()):>4}  {doms.most_common(6)}")
    print(f"  -{cuenta['fuera_periodo']:>4} fuera del periodo según la fecha de la página")
    print(f"  ={cuenta['ok']:>4} artículos nuevos con cuerpo | {cuenta['solo_titular']} solo titular")
    print(f"  nuevos por medio: {dict(ok_medio)}")

    # -------------------------------------------------------------- 4) exportar
    pj, pc, n, fuera = alm.exportar(a.salida, desde.isoformat(), hasta.isoformat(),
                                    [m.nombre for m in medios], filtro, filtrados, etiqueta)
    if filtro is not None:
        que = f"--buscar {buscar}" if buscar else "[temas] del archivo"
        print(f"\nFILTRO ({que}): {n} pasan | {fuera} quedan en la base sin exportar")
    print(f"\nEXPORTADO: {n} noticias del periodo (acumulado de la base)\n  {pj}\n  {pc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
