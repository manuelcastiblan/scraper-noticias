"""Acceso HTTP: cabeceras, cortesía por host y robots.txt."""
from __future__ import annotations

import ssl
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

UA_DEFECTO = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0 Safari/537.36")


def contexto_ssl() -> ssl.SSLContext:
    """Verificación de certificados con el almacén del sistema más el de certifi.

    En macOS el Python de python.org no trae certificados raíz y toda conexión
    HTTPS falla con CERTIFICATE_VERIFY_FAILED hasta correr «Install
    Certificates.command». Sumar el paquete de certifi lo evita sin tocar la
    máquina. La verificación nunca se desactiva.
    """
    ctx = ssl.create_default_context()
    try:
        import certifi
        ctx.load_verify_locations(cafile=certifi.where())
    except Exception:
        pass
    return ctx


def dominio(u: str) -> str:
    try:
        return urllib.parse.urlparse(u).netloc.replace("www.", "")
    except Exception:
        return "?"


class Red:
    def __init__(self, user_agent: str = UA_DEFECTO, por_host: int = 3,
                 pausa: float = 0.3, respetar_robots: bool = True):
        self.ua = user_agent
        self.por_host = por_host
        self.pausa = pausa
        self.respetar_robots = respetar_robots
        self._sem: dict[str, threading.Semaphore] = {}
        self._robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self._lock = threading.Lock()
        self._ssl = contexto_ssl()

    def _semaforo(self, host: str) -> threading.Semaphore:
        with self._lock:
            return self._sem.setdefault(host, threading.Semaphore(self.por_host))

    def get(self, url: str, timeout: int = 25, html: bool = False,
            referer: str | None = None, max_bytes: int = 30_000_000) -> str:
        """Descarga `url` como texto. Lanza la excepción de urllib si falla."""
        h = {"User-Agent": self.ua, "Accept-Language": "es-AR,es;q=0.9,en;q=0.8"}
        if html:
            h["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            h["Cache-Control"] = "no-cache"
            h["Referer"] = referer or f"https://{urllib.parse.urlparse(url).netloc}/"
        else:
            h["Accept"] = "*/*"
        host = dominio(url)
        with self._semaforo(host):
            try:
                for intento in range(3):
                    try:
                        with urllib.request.urlopen(urllib.request.Request(url, headers=h), timeout=timeout,
                                                    context=self._ssl) as r:
                            crudo = r.read(max_bytes)
                            cs = r.headers.get_content_charset() or "utf-8"
                        break
                    except urllib.error.HTTPError:
                        raise                      # el servidor respondió: no es un fallo de red
                    except (urllib.error.URLError, TimeoutError, ConnectionError):
                        # fallos pasajeros de DNS/conexión (frecuentes con muchos hilos en Windows)
                        if intento == 2:
                            raise
                        time.sleep(1.5 * (intento + 1))
            finally:
                if self.pausa:
                    time.sleep(self.pausa)
        try:
            return crudo.decode(cs, "replace")
        except LookupError:
            return crudo.decode("utf-8", "replace")

    def permitido(self, url: str) -> bool:
        """robots.txt del host, reglas de '*'. Si no se puede leer, se permite."""
        if not self.respetar_robots:
            return True
        p = urllib.parse.urlparse(url)
        base = f"{p.scheme}://{p.netloc}"
        with self._lock:
            conocido = base in self._robots
            rp = self._robots.get(base)
        if not conocido:
            rp = None
            try:
                txt = self.get(base + "/robots.txt", timeout=15)
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(txt.splitlines())
            except Exception:
                rp = None
            with self._lock:
                self._robots[base] = rp
        return True if rp is None else rp.can_fetch("*", url)
