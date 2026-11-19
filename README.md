# scraper-noticias

Scraper de noticias de tema libre, por RSS y sitemaps. Descubre lo que publicó
cada medio en un periodo, descarga el cuerpo completo y lo guarda todo en una
base local. El tema se elige después, al exportar: la misma base responde
cualquier búsqueda sin volver a descargar.

Trae un catálogo de 62 medios de Argentina y Colombia (generalistas, economía,
regionales, radio y TV, investigación, y especializados en minería y energía).

Sale del flujo de respaldo de Noticias de `fuentes-publicas-noticias`, sin
Fabric, Spark ni IA: se quedó el descubrimiento (RSS + sitemaps con cuota por
sección), la extracción reforzada (trafilatura, respaldo por párrafos,
detección de muros) y la ventana de fechas por parámetro.

La [guía de instalación y uso](docs/guia.md) tiene el paso a paso: instalación
en Windows, macOS y Linux, ejemplos, cómo programar la corrida diaria, cómo
agregar medios y los problemas frecuentes.

## Uso

Windows:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m scraper_noticias --pais CO --buscar "Primo Gay"
```

macOS y Linux:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e .
.venv/bin/python -m scraper_noticias --pais CO --buscar "Primo Gay"
```

Si no quieres instalar el paquete, alcanza con las dependencias:
`python -m pip install -r requirements.txt` y correrlo desde la carpeta del repo.

| Opción | Qué hace |
|---|---|
| `--buscar "a,b"` | Exporta solo lo que mencione alguno de los términos (título o cuerpo) |
| `--pais AR,CO` | Solo medios de esos países |
| `--categoria mineria,energia` | Solo esas categorías |
| `--solo "Clarín,Infobae"` | Solo esos medios |
| `--desde` / `--hasta` | Periodo `YYYY-MM-DD` |
| `--dias N` | Ventana cuando no se dan fechas (2 en el catálogo general) |
| `--medios ARCHIVO` | Otro archivo de medios (un perfil de `perfiles/`) |
| `--solo-descubrir` | Cuenta candidatos por fuente y no descarga nada (`--listar` los imprime) |
| `--sin-filtro` | Ignora el filtro `[temas]` de un perfil |
| `--salida CARPETA` | Dónde van la base y las exportaciones (`datos/`) |

Los términos casan como palabra o frase completa, sin distinguir tildes ni
mayúsculas; un asterisco final casa como prefijo (`miner*`).

Salida en `datos/`:

- `noticias.db` — base SQLite acumulativa, una fila por URL, con todo lo descargado.
- `noticias_<desde>_a_<hasta>[_<búsqueda>].jsonl` — el periodo, con el cuerpo completo.
- `noticias_<desde>_a_<hasta>[_<búsqueda>].csv` — lo mismo para hoja de cálculo, también con el cuerpo completo en la columna `cuerpo`.

Con `--buscar` o con un perfil filtrado, cada fila lleva además `terminos`,
`menciones`, `densidad` (menciones por cada 1000 caracteres) y `en_titulo`.

## Dos límites que conviene conocer

**Los feeds llegan poco hacia atrás.** Los de los medios grandes cubren uno o
dos días. Una semana completa solo existe si el scraper corre a diario y la
base acumula; cada corrida descarga únicamente lo que no está resuelto. Para un
hecho de hace varios días, los artículos con cuerpo serán solo los recientes.

**Google News da titulares, no cuerpos.** Con `--buscar` se suma una consulta a
Google News, que sí llega más atrás, pero entrega título, fecha y medio con un
enlace propio de Google, no la URL del artículo (`estado = solo_titular`).

Ejemplo medido (2026-11-18, `--buscar "Primo Gay"` del 12 al 18 de noviembre,
sobre siete medios colombianos): 1.032 artículos descargados sin un solo fallo,
49 mencionan el alias, 47 de ellos del 17 y 18; los días de la captura (14 y 15)
quedaron cubiertos casi solo por los 97 titulares de Google News.

## Catálogo (`medios.toml`)

Verificado el 2026-11-18: 61 de las 62 fuentes respondieron con notas del día.

| País | Categoría | Medios |
|---|---|---|
| AR | generalista | Infobae, Clarín, La Nación, Página/12, Perfil, TN, Noticias Argentinas |
| AR | economia | El Cronista, Ámbito, iProfesional, El Economista, Forbes Argentina |
| AR | regional | Los Andes, LM Neuquén, Diario Río Negro, Diario de Cuyo, El Tribuno, Tiempo de San Juan |
| AR | mineria | Panorama Minero, Huella Minera, Minería y Desarrollo, Rumbo Minero, Salta Mining (solo titulares) |
| AR | energia | EconoJournal, Más Energía, Mejor Energía, Surtidores, Dinamicarg |
| CO | generalista | El Tiempo, El Espectador, Semana, Infobae Colombia, Cambio, Pulzo, Publimetro, Kienyke, Las2orillas, El Nuevo Siglo |
| CO | investigacion | La Silla Vacía, Vorágine, Verdad Abierta, InSight Crime, INDEPAZ |
| CO | radio_tv | Caracol Radio, Blu Radio, La FM, Noticias RCN, NTN24, Telemedellín |
| CO | regional | El Colombiano, Minuto30, El País Cali, El Heraldo, El Universal, Vanguardia, La Opinión, La Patria, El Nuevo Día, La Nación (Huila) |
| CO | economia | Portafolio, La República, Valora Analitik |

Sin acceso, comprobado:

- **Salta Mining** y **Minería Sustentable** responden 403 a clientes automáticos
  (desafío anti-bot). No se intenta pasarlo; Salta Mining queda con titulares.
- **Rumbo Minero** respondió bien en el sondeo y con error 520 del servidor en la validación: intermitente.
- Sin feed ni news-sitemap utilizable: Noticias Caracol, RCN Radio, Teleantioquia,
  Q'hubo, Canal 1, Mining Press, EnerNews, Energía Estratégica, BAE Negocios,
  La Política Online, Reporte Minero. W Radio tiene feed pero con una sola nota.

El catálogo completo son unas 6.000 notas cada dos días: conviene acotar con
`--pais`, `--categoria` o `--solo`.

## Perfiles (`perfiles/`)

Un perfil es un archivo de medios con su propio filtro `[temas]`, para un
seguimiento fijo. Los medios con `filtrar = true` solo se exportan si casan.

- `mineria_energia_ar.toml` — minería, petróleo y energía en Argentina: los
  especializados completos y cuatro generalistas filtrados.
- `colombia_seguridad.toml` — seguridad y orden público en Colombia, con los
  feeds y términos del proyecto de origen.

El filtro de perfil pasa una nota si algún término está en el título, o si el
cuerpo tiene `min_menciones` apariciones y `densidad_min` por cada 1000
caracteres. El umbral de densidad sale de medir 500 notas de generalistas
argentinos: contar menciones no alcanza, porque una nota larga de macroeconomía
junta cinco o diez sueltas sin tratar del sector. Sigue siendo un filtro de
palabras: las notas de inflación mayorista pasan porque hablan mucho de petróleo.

## Agregar un medio

```toml
[[medio]]
nombre = "Mi Medio"
pais = "CO"
categoria = "regional"
  [[medio.fuente]]
  tipo = "rss"            # rss | sitemap | gnews
  url = "https://ejemplo.com/feed/"
  paginas = 5             # WordPress: recorre ?paged=2..5 hasta salir del periodo
```

En `sitemap` valen además `incluir` / `excluir` (subcadenas de la URL),
`prioritarias` (secciones que entran primero al `tope`) y `{AAAAMM}` en la URL
para sitemaps mensuales. Conviene probar con `--solo "Mi Medio" --solo-descubrir`.

Si un medio no trae ningún candidato, la corrida lo avisa: puede ser el feed
roto o simplemente un medio de cadencia lenta dentro de una ventana corta.

## Comportamiento frente a los sitios

Respeta `robots.txt`, limita a 3 descargas simultáneas por sitio con una pausa
entre pedidos, y no intenta evadir muros ni desafíos anti-bot: lo que no se deja
leer queda como `sin_cuerpo` con su motivo y se reintenta en la siguiente corrida.

El cuerpo de los artículos es de cada medio. `datos/` está fuera del control de
versiones; sirve para análisis propio, no para republicar.

## Pruebas

Windows:

```powershell
.venv\Scripts\python -m unittest discover -s tests
```

macOS y Linux:

```bash
.venv/bin/python -m unittest discover -s tests
```

Son sin red: fechas y zona horaria, filtro, lectura de RSS y sitemaps, base local.

## Licencia

MIT, ver `LICENSE`. Cubre el código; el contenido de los artículos es de cada medio.
