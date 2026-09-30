# -*- coding: utf-8 -*-
"""La página de la hoja de ruta: un servidor chiquito que corre en tu compu.

    python app.py                 levanta http://127.0.0.1:8765 y te abre el navegador
    python app.py --no-abrir      lo mismo, sin abrir nada
    python app.py --puerto 9000   si el 8765 está ocupado

Solo usa la biblioteca estándar de Python (más yt-dlp para leer el canal, y Laya si lo tenés).
Escucha SOLO en tu compu (127.0.0.1). La clave de OpenRouter que pegás en la página se usa en memoria
para hablar con OpenRouter: no se guarda en ningún archivo ni se escribe en ningún registro.
"""
import argparse
import importlib.util
import json
import re
import sys
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI))
import canal  # noqa: E402
import motor  # noqa: E402
import ruta   # noqa: E402

WEB = AQUI / "web"
CANAL_POR_DEFECTO = "https://www.youtube.com/@facundocorengia"
TIPOS = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".js": "text/javascript; charset=utf-8", ".json": "application/json; charset=utf-8",
         ".woff2": "font/woff2", ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}
HOSTS = {"127.0.0.1", "localhost", "[::1]"}   # los únicos nombres con los que se habla (corta el DNS rebinding)

if sys.stdout is not None:   # con pythonw no hay consola
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass


# ── Laya: se carga UNA vez (tarda unos segundos y ocupa la placa) y se reusa en todas las rutas ──
class _Laya:
    def __init__(self):
        self.instancia = None
        self.error = ""
        self.cargando = False
        self._lock = threading.Lock()

    _instalado = None

    @classmethod
    def instalado(cls) -> bool:
        # se mira una sola vez, al arrancar: buscarlo mientras torch se importa en otro hilo traba la respuesta
        if cls._instalado is None:
            cls._instalado = (importlib.util.find_spec("laya") is not None
                              and importlib.util.find_spec("torch") is not None)
        return cls._instalado

    def obtener(self):
        with self._lock:
            if self.instancia is None and not self.error:
                self.cargando = True
                try:
                    m = motor.Laya()
                    # la primera decisión en la placa es lenta (arranca CUDA): se hace acá y no en tu ruta
                    m.decidir("Hola, ¿cómo va?", {"x": {"type": "noul", "instructions": "¿Es un saludo?",
                                                        "criteria": {"true": "saluda", "false": "no saluda"}}})
                    self.instancia = m
                except Exception as e:   # noqa: BLE001
                    self.error = str(e) or type(e).__name__
                finally:
                    self.cargando = False
            if self.error:
                raise RuntimeError(self.error)
            return self.instancia

    def precargar(self):
        try:
            self.obtener()
        except Exception:   # noqa: BLE001 — el error queda guardado y se muestra en la página
            pass

    def estado(self) -> dict:
        m = self.instancia
        return {"instalado": self.instalado(), "cargado": m is not None, "cargando": self.cargando,
                "gpu": getattr(m, "gpu", None), "placa": getattr(m, "placa", None), "error": self.error}


LAYA = _Laya()


# ── los trabajos: cada ruta corre en su hilo y va dejando lo que decide para que la página lo muestre ──
class Trabajo:
    def __init__(self):
        self.id = uuid.uuid4().hex[:12]
        self.eventos = []
        self.estado = "corriendo"
        self.resultado = None
        self.error = ""
        self.t0 = time.perf_counter()
        self._lock = threading.Lock()

    def avisar(self, tipo: str, datos: dict | None = None):
        with self._lock:
            self.eventos.append({"tipo": tipo, "t": round(time.perf_counter() - self.t0, 2), **(datos or {})})

    def desde(self, n: int) -> tuple:
        with self._lock:
            return self.eventos[n:], len(self.eventos)


TRABAJOS: dict = {}
_TLOCK = threading.Lock()


def _amable(e: Exception) -> str:
    """El error, en palabras. Nunca lleva la clave: urllib no la pone en el mensaje y acá no se agrega."""
    t = str(e) or type(e).__name__
    if "401" in t:
        return "OpenRouter no aceptó la clave. Revisala en openrouter.ai → Keys."
    if "402" in t:
        return "Tu cuenta de OpenRouter no tiene saldo para esto."
    if "Falta tu clave" in t:
        return "Falta tu clave de OpenRouter: pegala en el campo de JEV."
    if "HTTP Error 404" in t or "does not exist" in t or "Unable to download" in t:
        return "No encontré ese canal. Fijate que la URL sea la del canal (youtube.com/@canal)."
    return t


def correr(trabajo: Trabajo, canal_url: str, objetivo: str, perfil: str, nombre_motor: str, clave: str):
    try:
        trabajo.avisar("fase", {"texto": "Leyendo los videos del canal"})
        datos = canal.videos_del_canal(canal_url)
        videos = datos["videos"]
        if not videos:
            raise ValueError("Ese canal no tiene videos largos públicos para leer.")
        titulos = {v["id"]: v["titulo"] for v in videos}
        trabajo.avisar("canal", {"canal": datos["canal"], "total": len(videos), "ids": [v["id"] for v in videos],
                                 "etapas": [n for n, _ in ruta.PERFILES[perfil]["etapas"]]})
        if nombre_motor == "laya":
            if not LAYA.instancia:
                trabajo.avisar("fase", {"texto": "Cargando Laya en tu placa"})
            m = LAYA.obtener()
        else:
            m = motor.JEV(clave)   # la clave vive solo en este objeto, en memoria, mientras dura la ruta
        trabajo.avisar("fase", {"texto": f"{m.nombre} está leyendo {len(videos)} títulos"})

        def avisar(tipo, d):
            if "id" in d:
                d = {**d, "titulo": titulos.get(d["id"], "")}
            trabajo.avisar(tipo, d)

        t_decidir = time.perf_counter()
        res = ruta.armar(m, videos, objetivo, perfil, avisar=avisar)
        ids = [v["id"] for e in res["etapas"] for v in e["videos"]]
        res.update(canal=datos["canal"], canal_url=datos["url"],
                   segundos=round(time.perf_counter() - trabajo.t0, 1),
                   segundos_decidir=round(time.perf_counter() - t_decidir, 1),
                   placa=getattr(m, "placa", None),
                   playlist=("https://www.youtube.com/watch_videos?video_ids=" + ",".join(ids[:50])) if ids else "")
        trabajo.resultado = res
        trabajo.estado = "listo"
        trabajo.avisar("listo")
    except Exception as e:   # noqa: BLE001
        trabajo.error = _amable(e)
        trabajo.estado = "error"
        trabajo.avisar("error", {"texto": trabajo.error})


class Servidor(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):
        if isinstance(sys.exc_info()[1], (ConnectionAbortedError, ConnectionResetError, BrokenPipeError)):
            return   # el navegador se fue antes de que llegara la respuesta: no es un error
        super().handle_error(request, client_address)


class Manejador(BaseHTTPRequestHandler):
    server_version = "hoja-de-ruta"

    def log_message(self, fmt, *args):   # sin registro de pedidos: no hay nada que se pueda filtrar
        pass

    # ── respuestas ──
    def _json(self, datos, codigo: int = 200):
        cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(cuerpo)

    def _error(self, texto: str, codigo: int = 400):
        self._json({"error": texto}, codigo)

    def _host_ok(self) -> bool:
        host = re.sub(r":\d+$", "", (self.headers.get("Host") or "").strip().lower())
        return host in HOSTS

    def _origen_ok(self) -> bool:
        # otra página abierta en tu navegador no puede mandar pedidos acá y gastar tu clave
        origen = self.headers.get("Origin")
        if not origen:
            return True
        h = (urlparse(origen).hostname or "").lower()
        return h in {"127.0.0.1", "localhost", "::1"}

    # ── GET ──
    def do_GET(self):
        if not self._host_ok():
            return self._error("Solo desde tu compu.", 403)
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/api/motores":
            return self._json({"laya": LAYA.estado(), "jev": {"clave_guardada": bool(motor.clave_openrouter())},
                               "canal_por_defecto": CANAL_POR_DEFECTO,
                               "perfiles": {k: {"nombre": p["nombre"], "etapas": [n for n, _ in p["etapas"]]}
                                            for k, p in ruta.PERFILES.items()}})
        if u.path == "/api/canal":
            try:
                d = canal.videos_del_canal((q.get("url") or [""])[0])
            except Exception as e:   # noqa: BLE001
                return self._error(_amable(e))
            return self._json({"canal": d["canal"], "url": d["url"], "videos": len(d["videos"]), "leido": d.get("leido")})
        m = re.fullmatch(r"/api/progreso/([0-9a-f]{12})", u.path)
        if m:
            t = TRABAJOS.get(m.group(1))
            if not t:
                return self._error("Esa ruta no existe (¿se reinició el programa?).", 404)
            try:
                n = max(0, int((q.get("desde") or ["0"])[0]))
            except ValueError:
                n = 0
            eventos, total = t.desde(n)
            return self._json({"estado": t.estado, "eventos": eventos, "n": total, "error": t.error,
                               "resultado": t.resultado if t.estado == "listo" else None})
        return self._estatico(u.path)

    def _estatico(self, ruta_web: str):
        nombre = "index.html" if ruta_web in ("", "/") else ruta_web.lstrip("/")
        archivo = (WEB / nombre).resolve()
        if WEB.resolve() not in archivo.parents or not archivo.is_file():
            return self._error("No existe.", 404)
        cuerpo = archivo.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", TIPOS.get(archivo.suffix.lower(), "application/octet-stream"))
        self.send_header("Content-Length", str(len(cuerpo)))
        self.send_header("Cache-Control", "no-cache" if archivo.suffix == ".html" else "max-age=3600")
        self.end_headers()
        self.wfile.write(cuerpo)

    # ── POST ──
    def do_POST(self):
        if not self._host_ok() or not self._origen_ok():
            return self._error("Solo desde tu compu.", 403)
        if urlparse(self.path).path != "/api/ruta":
            return self._error("No existe.", 404)
        if "application/json" not in (self.headers.get("Content-Type") or ""):
            return self._error("Mandá JSON.", 415)
        try:
            largo = int(self.headers.get("Content-Length") or 0)
            pedido = json.loads(self.rfile.read(min(largo, 20000)).decode("utf-8") or "{}")
        except (ValueError, UnicodeDecodeError):
            return self._error("No entendí el pedido.")
        objetivo = str(pedido.get("objetivo") or "").strip()
        perfil = str(pedido.get("perfil") or "aprender")
        nombre_motor = "laya" if str(pedido.get("motor") or "").lower() == "laya" else "jev"
        clave = str(pedido.get("clave") or "").strip()
        if len(objetivo) < 8:
            return self._error("Contá un poco más qué querés lograr (una frase alcanza).")
        if perfil not in ruta.PERFILES:
            return self._error("Elegí quién sos.")
        try:
            canal_url = canal.normalizar_url(str(pedido.get("canal") or ""))
        except ValueError as e:
            return self._error(str(e))
        if nombre_motor == "laya" and not LAYA.instalado():
            return self._error("Laya no está instalado en esta compu (pip install laya). Probá con JEV.")
        if nombre_motor == "jev" and not (clave or motor.clave_openrouter()):
            return self._error("Falta tu clave de OpenRouter: pegala en el campo de JEV.")
        t = Trabajo()
        with _TLOCK:
            TRABAJOS[t.id] = t
            for viejo in list(TRABAJOS)[:-20]:   # se guardan las últimas 20 rutas, en memoria
                TRABAJOS.pop(viejo, None)
        threading.Thread(target=correr, args=(t, canal_url, objetivo, perfil, nombre_motor, clave), daemon=True).start()
        return self._json({"id": t.id})


def main():
    ap = argparse.ArgumentParser(description="La hoja de ruta: los videos de un canal, en el orden que te sirve.")
    ap.add_argument("--puerto", type=int, default=8765)
    ap.add_argument("--no-abrir", action="store_true", help="no abrir el navegador")
    ap.add_argument("--sin-precargar", action="store_true", help="no cargar Laya al arrancar (se carga en la primera ruta)")
    a = ap.parse_args()
    try:
        srv = Servidor(("127.0.0.1", a.puerto), Manejador)
    except OSError:
        sys.exit(f"El puerto {a.puerto} está ocupado. ¿Ya está andando? Abrí http://127.0.0.1:{a.puerto} "
                 f"o usá --puerto con otro número.")
    url = f"http://127.0.0.1:{a.puerto}"
    print(f"La hoja de ruta está andando en {url}  (Ctrl+C para cortarla)", flush=True)
    if LAYA.instalado() and not a.sin_precargar:
        threading.Thread(target=LAYA.precargar, daemon=True).start()
    if not a.no_abrir:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
