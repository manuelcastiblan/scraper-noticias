"""Pruebas sin red: fechas, filtro temático, lectura de feeds y base local."""
import tempfile
import unittest
from datetime import date
from pathlib import Path

from scraper_noticias.almacen import Almacen
from scraper_noticias.config import Fuente, cargar
from scraper_noticias.descubrir import Candidato, _elegir, _meses, _pasa_url, leer_rss, leer_sitemap
from scraper_noticias.extraer import extraer_html
from scraper_noticias.texto import FiltroTemas, a_datetime, norm, titulo_de_slug, zona

TZ = zona("America/Argentina/Buenos_Aires")
RAIZ = Path(__file__).resolve().parent.parent


class Fechas(unittest.TestCase):
    def test_rfc822_cruza_medianoche_a_hora_local(self):
        # 01:30 UTC del 18 es todavía el 17 en Buenos Aires (UTC-3)
        self.assertEqual(a_datetime("Wed, 18 Nov 2026 01:30:00 +0000", TZ).date(), date(2026, 11, 17))

    def test_iso_con_milisegundos_y_z(self):
        self.assertEqual(a_datetime("2026-11-18T21:37:22.66Z", TZ).date(), date(2026, 11, 18))

    def test_iso_con_offset(self):
        self.assertEqual(a_datetime("2026-11-18T17:30:00-03:00", TZ).hour, 17)

    def test_fecha_sola_es_local(self):
        self.assertEqual(a_datetime("2026-11-18", TZ).date(), date(2026, 11, 18))

    def test_basura(self):
        self.assertIsNone(a_datetime("ayer", TZ))
        self.assertIsNone(a_datetime("", TZ))


class Filtro(unittest.TestCase):
    def setUp(self):
        self.f = FiltroTemas(["miner*", "gas natural", "litio", "energía"], min_menciones=3, densidad_min=2.0)

    def test_palabra_completa(self):
        self.assertFalse(self.f.evaluar("El gasto público y el gasoil", "").pasa)

    def test_prefijo_y_tildes_en_titulo(self):
        r = self.f.evaluar("La MINERÍA crece en San Juan", "")
        self.assertTrue(r.pasa and r.en_titulo)
        self.assertEqual(r.terminos, ["miner"])

    def test_frase(self):
        self.assertTrue(self.f.evaluar("Sube el gas  natural", "").pasa)

    def test_mencion_suelta_en_nota_larga_no_pasa(self):
        r = self.f.evaluar("Dólar hoy", "energía " + "relleno " * 800 + "minera litio")
        self.assertEqual(r.menciones, 3)
        self.assertFalse(r.pasa)          # 3 menciones pero densidad < 2 por mil

    def test_nota_densa_pasa_sin_termino_en_titulo(self):
        r = self.f.evaluar("Un anuncio esperado", "La minera anunció litio y más litio. " * 3)
        self.assertTrue(r.pasa and not r.en_titulo)


class Feeds(unittest.TestCase):
    def test_rss(self):
        xml = ("<rss><channel><item><title><![CDATA[Uno]]></title><link>https://x.com/a</link>"
               "<pubDate>Wed, 18 Nov 2026 20:21:20 +0000</pubDate></item></channel></rss>")
        (u, t, d), = leer_rss(xml, TZ)
        self.assertEqual((u, t, d.date()), ("https://x.com/a", "Uno", date(2026, 11, 18)))

    def test_news_sitemap_prefiere_fecha_de_publicacion(self):
        xml = ("<urlset><url><loc>https://x.com/n1</loc><lastmod>2026-11-18T10:00:00Z</lastmod>"
               "<news:news><news:publication_date>2026-11-10T10:00:00Z</news:publication_date>"
               "<news:title><![CDATA[T&iacute;tulo]]></news:title></news:news></url>"
               "<url><loc>https://x.com/n2</loc><lastmod>2026-11-15T05:43:30.171Z</lastmod></url></urlset>")
        filas, hijos = leer_sitemap(xml, TZ)
        self.assertEqual(hijos, [])
        self.assertEqual(filas[0][1], "Título")
        self.assertEqual((filas[0][2].date(), filas[0][3]), (date(2026, 11, 10), True))
        self.assertEqual((filas[1][2].date(), filas[1][3]), (date(2026, 11, 15), False))

    def test_sitemap_indice(self):
        filas, hijos = leer_sitemap("<sitemapindex><sitemap><loc>https://x.com/s1.xml</loc></sitemap></sitemapindex>", TZ)
        self.assertEqual((filas, hijos), ([], ["https://x.com/s1.xml"]))

    def test_incluir_excluir(self):
        f = Fuente("sitemap", incluir=("/economia/",), excluir=("/videos/",))
        self.assertTrue(_pasa_url("https://x.com/economia/a", f))
        self.assertFalse(_pasa_url("https://x.com/deportes/a", f))
        self.assertFalse(_pasa_url("https://x.com/economia/videos/a", f))

    def test_cuota_prioritarias_antes_que_recientes(self):
        c = lambda u, d: Candidato(u, u, "m", "", "SITEMAP", a_datetime(d, TZ))
        items = [c("https://x.com/politica/1", "2026-11-18"), c("https://x.com/economia/2", "2026-11-12"),
                 c("https://x.com/politica/3", "2026-11-17")]
        sel = _elegir(items, Fuente("sitemap", prioritarias=("/economia/",), tope=2))
        self.assertEqual([x.url[-1] for x in sel], ["2", "1"])

    def test_meses_del_periodo(self):
        self.assertEqual(_meses(date(2026, 10, 28), date(2026, 12, 2)), ["202610", "202611", "202612"])

    def test_titulo_de_slug(self):
        self.assertEqual(titulo_de_slug("https://x.com/gas/canos-argentina-lng-n1261575"), "Canos argentina lng")


class Extraccion(unittest.TestCase):
    def test_respaldo_por_parrafos(self):
        html = "<html><body>" + "".join(f"<div><p>Párrafo número {i} con texto suficiente para contar como cuerpo real.</p></div>"
                                        for i in range(12)) + "</body></html>"
        ex = extraer_html(html, 300)
        self.assertGreaterEqual(len(ex.cuerpo), 300)


class Base(unittest.TestCase):
    def test_guardar_resolver_exportar(self):
        with tempfile.TemporaryDirectory() as d:
            alm = Almacen(Path(d) / "n.db")
            comun = {"medio": "M", "fecha": "2026-11-18"}
            alm.guardar({**comun, "url": "u1", "titulo": "A", "estado": "ok", "cuerpo": "x" * 400})
            alm.guardar({**comun, "url": "u2", "titulo": "B", "estado": "sin_cuerpo", "motivo": "bloqueado"})
            alm.guardar({**comun, "url": "u3", "titulo": "C", "estado": "fuera_periodo"})
            alm.confirmar()
            # 'sin_cuerpo' se reintenta; lo demás no
            self.assertEqual(alm.resueltas(["u1", "u2", "u3", "u4"]), {"u1", "u3"})
            pj, pc, n, fuera = alm.exportar(d, "2026-11-12", "2026-11-18")
            self.assertEqual((n, fuera), (1, 0))
            self.assertIn('"titulo": "A"', pj.read_text(encoding="utf-8"))
            self.assertNotIn("xxxxxxxxxx" * 35, pc.read_text(encoding="utf-8-sig"))   # CSV sin cuerpo completo
            alm.db.close()

    def test_el_filtro_se_aplica_al_exportar_y_no_borra_nada(self):
        with tempfile.TemporaryDirectory() as d:
            alm = Almacen(Path(d) / "n.db")
            f = {"fecha": "2026-11-18", "estado": "ok"}
            alm.guardar({**f, "url": "u1", "medio": "A", "titulo": "Capturan a alias Primo Gay", "cuerpo": "texto"})
            alm.guardar({**f, "url": "u2", "medio": "A", "titulo": "Otra cosa", "cuerpo": "el primo gay aparece aquí"})
            alm.guardar({**f, "url": "u3", "medio": "A", "titulo": "Fútbol", "cuerpo": "nada que ver"})
            alm.guardar({**f, "url": "u4", "medio": "B", "titulo": "Fútbol", "cuerpo": "nada que ver"})
            alm.confirmar()
            busca = FiltroTemas(["Primo Gay"], 1, 0.0)
            pj, _, n, fuera = alm.exportar(d, "2026-11-18", "2026-11-18", filtro=busca, etiqueta="primo-gay")
            self.assertEqual((n, fuera), (2, 2))
            self.assertTrue(pj.name.endswith("_primo-gay.jsonl"))
            # filtro solo sobre el medio A: lo de B pasa entero
            self.assertEqual(alm.exportar(d, "2026-11-18", "2026-11-18", filtro=busca, filtrados={"A"})[2:], (3, 1))
            # selección de medios, y la base sigue completa para otra búsqueda
            self.assertEqual(alm.exportar(d, "2026-11-18", "2026-11-18", medios=["B"])[2], 1)
            self.assertEqual(alm.exportar(d, "2026-11-18", "2026-11-18")[2], 4)
            alm.db.close()


class Configuracion(unittest.TestCase):
    def test_archivos_de_medios_cargan(self):
        for ruta in [RAIZ / "medios.toml", *sorted((RAIZ / "perfiles").glob("*.toml"))]:
            cfg = cargar(ruta)
            self.assertTrue(cfg.medios, ruta)
            self.assertEqual(norm("Página/12"), "pagina 12")


if __name__ == "__main__":
    unittest.main()
