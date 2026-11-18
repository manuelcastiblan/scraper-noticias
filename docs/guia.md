# Guía de instalación y uso

## 1. Requisitos

- Python 3.11 o superior (el archivo de medios se lee con `tomllib`, que no existe antes).
- Git, para clonar el repositorio.
- Conexión a internet. No hace falta ninguna cuenta ni clave.

Para comprobar la versión de Python:

```powershell
py --version
```

En Windows, si `python` responde «Python was not found», usa `py`: es el
lanzador que instala python.org. En macOS y Linux el comando es `python3`.

## 2. Instalación

### Windows (PowerShell)

```powershell
git clone https://github.com/manuelcastiblan/scraper-noticias.git
cd scraper-noticias
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

### macOS y Linux

```bash
git clone https://github.com/manuelcastiblan/scraper-noticias.git
cd scraper-noticias
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

De aquí en adelante los ejemplos usan la ruta de Windows,
`.venv\Scripts\python`. En macOS y Linux es `.venv/bin/python`.

No hace falta activar el entorno virtual: basta con llamar a su Python por la
ruta. Los comandos se corren siempre desde la carpeta del repositorio, que es
donde están `medios.toml` y el paquete `scraper_noticias`.

Alternativa: `pip install -e .` en vez de `-r requirements.txt` instala además
el comando `scraper-noticias`, equivalente a `python -m scraper_noticias`.

### Comprobar que quedó bien

```powershell
.venv\Scripts\python -m unittest discover -s tests
```

Deben pasar las 21 pruebas. No usan la red.

## 3. Primera corrida

Conviene empezar por algo pequeño. Esto lista cuántas notas hay disponibles en
dos medios, sin descargar nada:

```powershell
.venv\Scripts\python -m scraper_noticias --solo "El Tiempo,Semana" --solo-descubrir
```

Y esto las descarga:

```powershell
.venv\Scripts\python -m scraper_noticias --solo "El Tiempo,Semana"
```

Al terminar hay tres archivos en `datos/`: la base `noticias.db` y la
exportación del periodo en `.jsonl` (con el cuerpo) y `.csv` (sin cuerpo, para
abrir en Excel).

Sin ninguna opción, el scraper recorre los 62 medios del catálogo: unas 6.000
descargas cada dos días. Funciona, pero casi siempre es mejor acotar.

## 4. Ejemplos de uso

Buscar un tema en los medios de un país:

```powershell
.venv\Scripts\python -m scraper_noticias --pais CO --buscar "Primo Gay"
```

Varios términos (basta con que aparezca uno) y un periodo explícito:

```powershell
.venv\Scripts\python -m scraper_noticias --pais AR --buscar "litio,cobre" --desde 2026-11-10 --hasta 2026-11-18
```

Solo los medios especializados en minería y energía, completos:

```powershell
.venv\Scripts\python -m scraper_noticias --categoria mineria,energia --dias 7
```

Un perfil con filtro fijo:

```powershell
.venv\Scripts\python -m scraper_noticias --medios perfiles/mineria_energia_ar.toml
```

Guardar una investigación en su propia carpeta, con su propia base:

```powershell
.venv\Scripts\python -m scraper_noticias --pais CO --buscar "Primo Gay" --salida datos\primo_gay
```

Sobre `--buscar`:

- Casa palabras o frases completas, sin distinguir tildes ni mayúsculas:
  `"mineria"` encuentra «Minería».
- Un asterisco final casa como prefijo: `"miner*"` encuentra minería, minera, mineros.
- La base guarda todo lo descargado, casara o no. Repetir el comando con otros
  términos no descarga de nuevo: solo reexporta con el filtro nuevo.

## 5. Cómo leer lo que imprime

```
=== DESCUBRIMIENTO ===
  Semana   rss:https://www.semana.com/arc/outboundfeeds/rss/   100 leídos |  100 en periodo | +100
```

Por cada fuente: cuántas entradas trae el feed, cuántas caen en el periodo y
cuántas son nuevas respecto de las otras fuentes.

```
=== EXTRACCIÓN === 1132 por descargar (0 ya resueltas en la base)
EMBUDO: 1132 descargas intentadas
  -   0 sin cuerpo utilizable
  -   0 fuera del periodo según la fecha de la página
  =1032 artículos nuevos con cuerpo | 100 solo titular
FILTRO (--buscar ['Primo Gay']): 146 pasan | 986 quedan en la base sin exportar
```

- **ya resueltas**: notas que estaban en la base de una corrida anterior; no se vuelven a pedir.
- **sin cuerpo utilizable**: la descarga falló. Debajo sale el motivo por sitio
  (`bloqueado`, `http_404`, `cuerpo_corto`, `robots`). Se reintentan en la corrida siguiente.
- **solo titular**: entradas de Google News, que no traen el texto.
- **FILTRO**: cuántas de las notas del periodo casan con la búsqueda.

## 6. Columnas de la salida

| Columna | Contenido |
|---|---|
| `medio`, `pais`, `categoria` | Los del archivo de medios |
| `titulo`, `url`, `autor` | Tomados de la página cuando existen |
| `fecha` | Fecha de publicación en la zona horaria configurada |
| `fecha_publicacion` | Fecha y hora completas |
| `origen` | `RSS`, `SITEMAP` o `GNEWS` |
| `estado` | `ok` (con cuerpo) o `solo_titular` |
| `n_caracteres`, `cuerpo` | El texto del artículo (`cuerpo` solo en el `.jsonl`) |
| `extracto` | Primeros 300 caracteres (solo en el `.csv`) |
| `terminos`, `menciones`, `densidad`, `en_titulo` | Solo cuando hay filtro: qué términos aparecen, cuántas veces, cuántas por cada 1000 caracteres y si alguno está en el título |

El `.csv` se guarda en UTF-8 con marca de orden de bytes, así Excel muestra
bien las tildes al abrirlo con doble clic.

Para consultar la base directamente:

```powershell
.venv\Scripts\python -c "import sqlite3; print(sqlite3.connect('datos/noticias.db').execute('select medio, count(*) from noticias group by 1 order by 2 desc').fetchall())"
```

## 7. Correrlo todos los días

Los feeds de la mayoría de los medios solo cubren uno o dos días. Para tener
cobertura continua hay que correr el scraper a diario: cada corrida suma a la
base lo que aún no tiene.

### Windows: Programador de tareas

Crea una tarea diaria a las 7:00. Ajusta la ruta a donde clonaste el repositorio:

```powershell
schtasks /Create /TN "scraper-noticias" /SC DAILY /ST 07:00 /TR "cmd /c cd /d C:\ruta\a\scraper-noticias && .venv\Scripts\python -m scraper_noticias --pais CO >> datos\corrida.log 2>&1"
```

Para probarla sin esperar, y para quitarla:

```powershell
schtasks /Run /TN "scraper-noticias"
```

```powershell
schtasks /Delete /TN "scraper-noticias" /F
```

El equipo tiene que estar encendido a esa hora. La carpeta `datos` debe existir
antes de la primera corrida programada, porque ahí se escribe el registro; se
crea sola al correr el scraper una vez a mano.

### macOS y Linux: cron

Abre el editor con `crontab -e` y agrega:

```
0 7 * * * cd /ruta/a/scraper-noticias && .venv/bin/python -m scraper_noticias --pais CO >> datos/corrida.log 2>&1
```

## 8. Agregar o quitar medios

Cada medio es un bloque de `medios.toml`. Para quitar uno, borra su bloque o
déjalo fuera con `--solo`, `--pais` o `--categoria`. Para agregar:

```toml
[[medio]]
nombre = "Mi Medio"
pais = "CO"
categoria = "regional"
  [[medio.fuente]]
  tipo = "rss"
  url = "https://ejemplo.com/feed/"
```

Cómo encontrar la fuente de un medio nuevo:

1. Abre `https://sitio/robots.txt` y busca las líneas `Sitemap:`. Si alguna
   dice `news`, es un news-sitemap: úsala con `tipo = "sitemap"`.
2. Si no, prueba `https://sitio/feed/` (WordPress), `/rss` o `/rss.xml`.
3. En sitios hechos con Arc, `/arc/outboundfeeds/rss/?outputType=xml`.

Después compruébalo:

```powershell
.venv\Scripts\python -m scraper_noticias --solo "Mi Medio" --solo-descubrir --listar
```

Debe mostrar notas con fecha reciente. Si salen cero «en periodo» con muchas
leídas, el feed está abandonado o no trae fechas.

Opciones de una fuente:

| Clave | Para qué |
|---|---|
| `paginas = 5` | En feeds de WordPress, recorre `?paged=2..5` hasta salir del periodo |
| `incluir = ["/economia/"]` | Solo URLs que contengan alguna de esas subcadenas |
| `excluir = ["/videos/"]` | Descarta las que contengan alguna |
| `prioritarias = ["/judicial/"]` | Esas secciones entran primero cuando se llega al tope |
| `tope = 200` | Máximo de notas por corrida para esa fuente |

## 9. Problemas frecuentes

**`URLError ... getaddrinfo failed` en una fuente.** Fallo pasajero de DNS, más
común en Windows cuando se consultan muchos sitios a la vez. El scraper ya
reintenta tres veces; si persiste, vuelve a correr: lo ya descargado no se repite.

**`*** SIN CANDIDATOS: ...`.** Ese medio no trajo ninguna nota del periodo.
Puede ser un medio de publicación lenta con una ventana corta (prueba con
`--dias 7`) o un feed que cambió de dirección. Compruébalo con `--solo-descubrir`.

**`HTTP Error 403` o motivo `bloqueado`.** El sitio rechaza clientes
automáticos. El scraper no intenta saltarse esos controles. Si el medio importa,
la opción es una fuente `gnews` con `consulta = "site:dominio.com"`, que da solo titulares.

**`HTTP Error 520`, `502` o `504`.** Error del servidor del medio. Suele
resolverse solo; reintenta más tarde.

**Motivo `robots`.** El `robots.txt` del sitio no permite esa URL. Se respeta.
Se puede desactivar con `respetar_robots = false` en `[general]`, bajo tu responsabilidad.

**La búsqueda no encuentra notas de hace una semana.** Es el alcance de los
feeds, no un error: solo hay cuerpo de lo publicado en los últimos uno o dos
días, o de lo que la base ya venía acumulando. Los titulares de Google News sí
llegan más atrás.

**Quiero empezar de cero.** Borra la carpeta `datos/`. La base se crea de nuevo
en la siguiente corrida.

## 10. Uso responsable

El scraper limita a tres descargas simultáneas por sitio, hace una pausa entre
pedidos y respeta `robots.txt`. El texto de los artículos pertenece a cada
medio: `datos/` queda fuera del control de versiones y sirve para análisis
propio, no para republicar.
