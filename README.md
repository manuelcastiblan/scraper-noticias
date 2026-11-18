# scraper-noticias

Scraper de noticias por RSS y sitemaps: descubre los artículos de un periodo,
descarga el cuerpo completo, aplica un filtro temático a los medios generalistas
y deja todo en una base local más un JSONL y un CSV por periodo.

Sale del flujo de respaldo de Noticias de `fuentes-publicas-noticias`
(`DF_NB_300_GOLD_NOTICIAS_GDELT`), sin Fabric, Spark ni IA: se quedó el
descubrimiento (RSS + sitemaps con cuota por sección), la extracción reforzada
(trafilatura, respaldo por párrafos, detección de muros) y la ventana de fechas
por parámetro. La geolocalización por municipio y la interpretación con modelo
no están aquí.

## Uso

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m scraper_noticias
```

Sin argumentos toma los últimos 7 días y `medios.toml`. Opciones:

| Opción | Qué hace |
|---|---|
| `--desde` / `--hasta` | Periodo `YYYY-MM-DD` |
| `--dias N` | Ventana cuando no se dan fechas |
| `--medios ARCHIVO` | Otro archivo de medios (p. ej. `perfiles/colombia_seguridad.toml`) |
| `--solo "Clarín,Infobae"` | Solo esos medios |
| `--solo-descubrir` | Lista los candidatos y no descarga nada |
| `--sin-filtro` | Guarda todo, sin filtro temático |
| `--salida CARPETA` | Dónde van la base y las exportaciones (`datos/`) |

Salida en `datos/`:

- `noticias.db` — base SQLite acumulativa, una fila por URL.
- `noticias_<desde>_a_<hasta>.jsonl` — el periodo, con el cuerpo completo.
- `noticias_<desde>_a_<hasta>.csv` — lo mismo sin cuerpo (con un extracto), para hoja de cálculo.

Columnas: `medio`, `categoria`, `titulo`, `url`, `fecha` (local), `fecha_publicacion`,
`autor`, `origen` (RSS / SITEMAP / GNEWS), `terminos`, `menciones`, `densidad`,
`en_titulo`, `estado`, `n_caracteres`, `cuerpo`.

## Hay que correrlo a diario

Los feeds de los medios grandes cubren poco: el news-sitemap de Clarín y los RSS
de El Cronista e Infobae llegan a uno o dos días hacia atrás. La semana completa
solo existe si el scraper corre todos los días y la base va acumulando. Cada
corrida descarga únicamente lo que no está resuelto y reexporta el periodo.

## Medios incluidos (`medios.toml`)

Medido el 2026-11-18 sobre la ventana 11 al 18 de noviembre:

| Medio | Vía | Alcance del feed | Resultado |
|---|---|---|---|
| Panorama Minero | sitemap, sección `/es/news/` | histórico completo | 4 notas, todas con cuerpo |
| Huella Minera | RSS de WordPress, paginado | histórico | 7 |
| EconoJournal | RSS de WordPress, paginado | histórico | 38 |
| Más Energía | RSS + news-sitemap | ~5 días | 23 |
| Forbes Argentina | news-sitemap + filtro | ~2 días | 2 de 71 |
| Infobae | RSS de Economía + filtro | ~2 días | 7 de 100 |
| El Cronista | 3 RSS de sección + filtro | ~2 días | 15 de 128 |
| Página/12 | RSS de Economía y portada + filtro | ~3 días | 1 de 30 |
| Clarín | news-sitemap (economía, política, rural) + filtro | ~2 días | 4 de 171 |
| Salta Mining | **solo titulares** vía Google News | — | 45 titulares, sin cuerpo |

Ninguna de las 572 descargas falló ni fue bloqueada.

**Salta Mining no se puede scrapear directo.** `saltamining.com` responde con un
desafío anti-bot de Cloudflare (403) a cualquier cliente automático, incluido su
`robots.txt`. No se intenta pasarlo. Queda cubierto a nivel de titular, fecha y
enlace de Google News (`estado = solo_titular`); el enlace es el de Google, no
la URL del sitio.

**Forbes no tiene un feed de minería.** No hay sección ni RSS propios de minería
en `forbesargentina.com`, así que entra como generalista con filtro temático.

## Filtro temático

Los especializados entran completos. Los que tienen `filtrar = true` pasan si
algún término de `[temas]` está en el título, o si el cuerpo tiene al menos
`min_menciones` apariciones y `densidad_min` por cada 1000 caracteres.

El umbral de densidad sale de medir 500 notas de los generalistas sin filtrar:
contar menciones no alcanza, porque una nota larga de macroeconomía junta cinco
o diez sueltas («energía», «YPF» en una lista de acciones) sin tratar del
sector. Con densidad, el ruido queda por debajo de 1 y las notas del sector por
encima de 2. Sigue siendo un filtro de palabras: las notas de inflación
mayorista pasan porque hablan mucho de petróleo. `menciones`, `densidad` y
`en_titulo` quedan en cada fila para ajustar el corte después sin volver a
descargar.

## Agregar un medio

Un bloque en el TOML:

```toml
[[medio]]
nombre = "Mi Medio"
categoria = "energia"
filtrar = false
  [[medio.fuente]]
  tipo = "rss"            # rss | sitemap | gnews
  url = "https://ejemplo.com/feed/"
  paginas = 5             # WordPress: recorre ?paged=2..5 hasta salir del periodo
```

En `sitemap` valen además `incluir` / `excluir` (subcadenas de la URL),
`prioritarias` (secciones que entran primero al `tope`) y `{AAAAMM}` en la URL
para sitemaps mensuales. Conviene probar con `--solo "Mi Medio" --solo-descubrir`.

Si un medio configurado no trae ningún candidato, la corrida lo avisa en
mayúsculas: casi siempre es el feed roto, no falta de noticias.

## Comportamiento frente a los sitios

Respeta `robots.txt`, limita a 3 descargas simultáneas por sitio con una pausa
entre pedidos, y no intenta evadir muros ni desafíos anti-bot: lo que no se deja
leer queda como `sin_cuerpo` con su motivo y se reintenta en la siguiente corrida.

El cuerpo de los artículos es de cada medio. `datos/` está fuera del control de
versiones; sirve para análisis propio, no para republicar.

## Pruebas

```powershell
.venv\Scripts\python -m unittest discover -s tests
```

Son sin red: fechas y zona horaria, filtro, lectura de RSS y sitemaps, base local.

## Licencia

MIT, ver `LICENSE`. Cubre el código; el contenido de los artículos es de cada medio.
