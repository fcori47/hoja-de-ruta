# -*- coding: utf-8 -*-
"""Los dos motores que deciden: JEV (por OpenRouter, con tu clave) y Laya (en tu compu, gratis).

Los dos hablan el mismo idioma: les pasás un ESTADO (un texto con la situación) y PREGUNTAS de tres tipos,
y te devuelven la respuesta con su probabilidad. No escriben texto: deciden.
  - noul   → sí/no como probabilidad            {"noul": 0.93}
  - choice → una opción entre varias              {"choice": "b", "confidence": 0.8, "probabilities": {...}}
  - score  → un escalón de una escala ordenada   {"score": 0.66, "legend": ..., "confidence": ...}

Qué conviene usar (lo que se midió armando rutas con un canal de 443 videos):
  - JEV entiende lo que querés y cuesta centavos de centavo: la ruta entera (unas 500 decisiones, de a doce a la
    vez) tardó 16-26 s y costó unos USD 0,0077.
  - Laya corre en tu placa y no cuesta nada (~65 ms por decisión en una RTX 4070 Ti SUPER: ~30 s la ruta), pero
    SIN ENTRENAR no sirve para esto: lee el tema, no entiende qué querés. Contra JEV, de sus 15 primeros coincidió
    en 0 a 3, y casi todo le dio «sirve» con 0,9 o más. Probadas cuatro formas de preguntarle: igual.
  - Si no tenés placa NVIDIA, Laya tarda casi un segundo por decisión.
"""
import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

URL_JEV = "https://openrouter.ai/api/alpha/decisions"
MODELO_JEV = "typesafe/jev-1.13"   # fijo a propósito: con «latest» los umbrales se mueven sin aviso


def clave_openrouter() -> str:
    """La clave de OpenRouter: la variable de entorno o el archivo .env al lado de este programa."""
    k = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if k:
        return k
    env = Path(__file__).resolve().parent / ".env"
    if env.exists():
        for linea in env.read_text(encoding="utf-8").splitlines():
            linea = linea.strip()
            if linea.startswith("OPENROUTER_API_KEY") and "=" in linea:
                return linea.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


class JEV:
    nombre = "JEV"

    def __init__(self, clave: str = ""):
        self.clave = clave or clave_openrouter()
        if not self.clave:
            raise RuntimeError("Falta tu clave de OpenRouter (openrouter.ai → Keys). Ponela en la página o en el .env.")
        self.costo = 0.0

    def decidir(self, estado: str, preguntas: dict, timeout: int = 40) -> dict:
        cuerpo = {"model": MODELO_JEV, "state": estado, "questions": preguntas}
        req = urllib.request.Request(
            URL_JEV, data=json.dumps(cuerpo, ensure_ascii=False).encode("utf-8"), method="POST",
            headers={"Authorization": f"Bearer {self.clave}", "Content-Type": "application/json",
                     "HTTP-Referer": "https://github.com/fcori47/hoja-de-ruta", "X-Title": "hoja de ruta"})
        # 529 = «system_overloaded»: JEV a veces se satura unos segundos. Se reintenta.
        for intento in range(4):
            try:
                t0 = time.perf_counter()
                out = json.loads(urllib.request.urlopen(req, timeout=timeout).read().decode("utf-8"))
                out["_ms"] = (time.perf_counter() - t0) * 1000
                self.costo += (out.get("usage") or {}).get("cost") or 0
                return out
            except urllib.error.HTTPError as e:
                detalle = e.read().decode("utf-8", "ignore")[:300]
                if e.code in (408, 429, 500, 502, 503, 504, 529) and intento < 3:
                    time.sleep(1.5 * (intento + 1))
                    continue
                if e.code == 529:
                    raise RuntimeError("JEV está saturado en este momento (OpenRouter 529). Probá de nuevo en un rato.") from None
                raise RuntimeError(f"OpenRouter respondió {e.code}: {detalle}") from None
            except (urllib.error.URLError, TimeoutError):
                if intento < 3:
                    time.sleep(1.5 * (intento + 1))
                    continue
                raise


class Laya:
    nombre = "Laya"
    _lock = threading.Lock()   # una sola placa: las decisiones van de a una

    def __init__(self):
        try:
            import torch
            from laya import Router
        except ImportError:
            raise RuntimeError("Laya no está instalado: pip install laya (y PyTorch; con placa NVIDIA, la versión CUDA).") from None
        self._torch = torch
        self.gpu = torch.cuda.is_available()
        self.placa = torch.cuda.get_device_name(0) if self.gpu else "procesador"
        self.router = Router(device="cuda" if self.gpu else "cpu")
        self.costo = 0.0

    def decidir(self, estado: str, preguntas: dict, timeout: int = 40) -> dict:
        t0 = time.perf_counter()
        with self._lock:
            out = self.router.predict(estado, preguntas)
            if self.gpu:
                self._torch.cuda.synchronize()
        out = dict(out)
        out["_ms"] = (time.perf_counter() - t0) * 1000
        return out


def crear(nombre: str, clave: str = ""):
    nombre = (nombre or "").strip().lower()
    if nombre == "laya":
        return Laya()
    return JEV(clave)
