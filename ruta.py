# -*- coding: utf-8 -*-
"""Arma la hoja de ruta: de TODOS los videos de un canal, los que te sirven para lo que querés, en orden.

Son dos pasadas de decisiones, nada más:
  1. «¿Este video te sirve para lo que querés lograr?» — un sí/no por video, a todo el canal.
  2. «¿Va en esta etapa?» — un sí/no por cada etapa de tu perfil (en una sola llamada), solo a los que sirven.
Con eso cada etapa se queda con los videos que mejor le encajan, y la ruta sale en el orden de las etapas.

⚠️ Por qué la segunda pasada pregunta etapa por etapa y no «¿en cuál de las cuatro va?»: con la elección, JEV
contesta con 0,98-1,00 de seguridad y casi todo cae en la misma etapa (en un canal de tutoriales, «Cómo se
implementa» se llevaba 12 de 13). Preguntando cada etapa por separado, un video puede encajar en dos y la etapa
con menos candidatos elige primero: así la ruta tiene etapas de verdad.

El motor no escribe ni inventa nada: solo decide sobre los títulos reales del canal.
"""
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor

# Las etapas dependen de quién sos. El motor no puede inventarlas (no escribe): elige entre estas.
PERFILES = {
    "aprender": {
        "nombre": "Quiero aprender",
        "etapas": [
            ("Entender qué es", "entender qué es y para qué sirve, los conceptos base, antes de tocar nada"),
            ("Hacerlo por primera vez", "armar, instalar o hacer lo primero, paso a paso"),
            ("Mejorarlo", "mejorar lo que ya hace, resolver problemas, casos reales"),
            ("Ir más allá", "avanzado: escalar, optimizar, combinar con otras cosas"),
        ],
    },
    "empresa": {
        "nombre": "Tengo una empresa",
        "etapas": [
            ("Qué le sirve a tu empresa", "entender qué puede hacer esto por un negocio y qué no, sin tecnicismos"),
            ("Casos reales", "ver cómo lo usa una empresa de verdad, un caso de cliente, lo que quedó funcionando"),
            ("Cómo se implementa", "cómo se arma, qué hace falta, cómo se pone en marcha en el negocio"),
            ("Que siga andando", "mantenerlo, mejorarlo, medirlo y que el equipo lo use"),
        ],
    },
    "agencia": {
        "nombre": "Quiero ofrecerlo como servicio",
        "etapas": [
            ("Entender qué es", "qué es de verdad este trabajo y qué no, antes de arrancar"),
            ("Qué ofrecer", "qué servicio o solución venderle a una empresa hoy"),
            ("Conseguir clientes", "cómo te llegan los clientes, contenido, contactos, prospección"),
            ("Cierre y entrega de servicio", "cómo cerrar la venta y cómo hacer la entrega de servicio para que el cliente siga"),
        ],
    },
}
POR_ETAPA = 3          # como mucho, tres videos por etapa: una ruta, no el canal entero
MIN_ETAPA = 0.3        # para entrar en una etapa, el video tiene que encajarle al menos esto…
MARGEN_ETAPA = 0.3     # …y a no más de esto del que mejor le encaja a esa etapa
GENERAL = 0.55         # si ninguna etapa le encaja más que esto, es un video general (un curso entero): va al principio
UMBRAL = 0.6           # «sirve» desde acá…
MARGEN = 0.15          # …y a no más de esto del que más sirve (si el mejor es 0,92, entra desde 0,77)
MINIMO = 5             # si pasan menos, se toman igual los mejores (y se avisa)
MAXIMO = 20            # los que pasan a la segunda pasada


def pregunta_sirve() -> dict:
    return {"sirve": {
        "type": "noul",
        "instructions": "¿Este video le sirve a esta persona para lo que quiere lograr?",
        "criteria": {"true": "el video trata de algo que necesita aprender o hacer para lograr eso",
                     "false": "el video trata de otra cosa, o no le suma para eso"}}}


def preguntas_etapas(perfil: str) -> dict:
    """Un sí/no por etapa, todas en la misma llamada."""
    return {f"e{i}": {
        "type": "noul",
        "instructions": f"Para lo que quiere lograr esta persona, ¿este video va en la etapa «{nombre}»?",
        "criteria": {"true": f"el video trata de esto: {desc}",
                     "false": "el video es de otra parte del camino"}}
        for i, (nombre, desc) in enumerate(PERFILES[perfil]["etapas"])}


def repartir(videos: list, n_etapas: int, prioridad=lambda v: v["sirve"]) -> list:
    """Cada etapa se queda con los que le encajan y, de esos, con los que más sirven (y más nuevos).
    El encaje es la puerta, no el orden: si no, un video viejo que «encaja justo» le gana al curso nuevo.
    Elige primero la etapa que tiene MENOS candidatos: si no, la que le encaja a todo se come los videos y
    las otras quedan vacías."""
    candidatos = []
    for i in range(n_etapas):
        tope = max((v["encaje"][i] for v in videos), default=0)
        c = [v for v in videos if v["encaje"][i] >= max(MIN_ETAPA, tope - MARGEN_ETAPA)
             or (i == 0 and max(v["encaje"]) < GENERAL)]   # el curso que cubre todo no «encaja» en ninguna
        candidatos.append(sorted(c, key=lambda v: -prioridad(v)))
    usados, etapas = set(), [[] for _ in range(n_etapas)]
    for i in sorted(range(n_etapas), key=lambda i: len(candidatos[i])):
        for v in candidatos[i]:
            if len(etapas[i]) >= POR_ETAPA:
                break
            if v["id"] not in usados:
                etapas[i].append({**v, "etapa": i})
                usados.add(v["id"])
    return etapas


def estado(objetivo: str, titulo: str, perfil: str) -> str:
    return (f"Quién es: {PERFILES[perfil]['nombre'].lower()}\n"
            f"Lo que quiere lograr: «{objetivo.strip()}»\nVideo: «{titulo}»")


_RELLENO = {"de", "la", "el", "los", "las", "en", "y", "a", "con", "un", "una", "tu", "para", "que", "del", "lo",
            "cambia", "todo", "paso", "desde", "cero", "tutorial", "completo", "completa", "espanol", "2024", "2025",
            "2026", "gratis", "guia", "como", "mi", "es", "por", "curso", "masterclass", "clase"}


def _tokens(titulo: str) -> set:
    t = unicodedata.normalize("NFKD", titulo.lower()).encode("ascii", "ignore").decode()
    return {w for w in re.findall(r"[a-z0-9]+", t) if w not in _RELLENO and len(w) > 1}


def sin_repetidos(videos: list) -> list:
    """El mismo video subido dos veces (o casi el mismo título) va una sola vez: el que más sirve."""
    elegidos = []
    for v in videos:
        tv = _tokens(v["titulo"])
        if any(tv and (len(tv & _tokens(e["titulo"])) / max(1, len(tv | _tokens(e["titulo"]))) >= 0.5) for e in elegidos):
            continue
        elegidos.append(v)
    return elegidos


def _prioridad(v: dict, total: int) -> float:
    # lo que más sirve primero; entre parecidos, lo más nuevo (orden 0 = el último que subió)
    return v["sirve"] - 0.10 * (v.get("orden", 0) / max(1, total))


def armar(motor, videos: list, objetivo: str, perfil: str = "aprender", avisar=lambda tipo, datos: None,
          paralelo: int = 12) -> dict:
    if perfil not in PERFILES:
        perfil = "aprender"
    if not objetivo or len(objetivo.strip()) < 8:
        raise ValueError("Contá un poco más qué querés lograr (una frase alcanza).")
    decisiones, total = 0, len(videos)
    hilos = paralelo if motor.nombre == "JEV" else 1

    # ── 1. ¿Te sirve? — a todo el canal ──
    def juzgar(v):
        out = motor.decidir(estado(objetivo, v["titulo"], perfil), pregunta_sirve())
        return v, float((out.get("answers") or {}).get("sirve", {}).get("noul") or 0), out.get("_ms", 0)

    puntuados = []
    with ThreadPoolExecutor(hilos) as ex:
        try:
            for v, p, ms in ex.map(juzgar, videos):
                decisiones += 1
                puntuados.append({**v, "sirve": round(p, 3)})
                avisar("sirve", {"id": v["id"], "p": round(p, 3), "ms": round(ms, 1), "hechas": decisiones, "total": total})
        except Exception:
            ex.shutdown(wait=False, cancel_futures=True)   # con una clave mala no se hacen los 400 pedidos igual
            raise
    puntuados.sort(key=lambda v: -_prioridad(v, total))
    mejor = max((v["sirve"] for v in puntuados), default=0)
    corte = max(UMBRAL, mejor - MARGEN)
    pasan = [v for v in puntuados if v["sirve"] >= corte]
    poco = len(pasan) < MINIMO
    if poco:
        pasan = sorted(puntuados, key=lambda v: -v["sirve"])[:MINIMO]
    pasan = sin_repetidos(pasan)[:MAXIMO]
    avisar("pasan", {"ids": [v["id"] for v in pasan], "corte": round(corte, 2)})

    # ── 2. ¿En qué etapa va? — un sí/no por etapa, solo a los que sirven ──
    n_etapas = len(PERFILES[perfil]["etapas"])
    avisar("etapas", {"decisiones": len(pasan) * n_etapas})

    def ubicar(v):
        out = motor.decidir(estado(objetivo, v["titulo"], perfil), preguntas_etapas(perfil))
        a = out.get("answers") or {}
        return v, [round(float((a.get(f"e{i}") or {}).get("noul") or 0), 3) for i in range(n_etapas)]

    with ThreadPoolExecutor(hilos) as ex:
        try:
            for v, encaje in ex.map(ubicar, pasan):
                decisiones += n_etapas
                v["encaje"] = encaje
                mejor_e = max(range(n_etapas), key=lambda i: encaje[i])
                avisar("etapa", {"id": v["id"], "etapa": mejor_e, "p": encaje[mejor_e], "hechas": decisiones})
        except Exception:
            ex.shutdown(wait=False, cancel_futures=True)
            raise

    etapas = [{"nombre": PERFILES[perfil]["etapas"][i][0], "videos": vs}
              for i, vs in enumerate(repartir(pasan, n_etapas, lambda v: _prioridad(v, total))) if vs]
    return {"objetivo": objetivo.strip(), "perfil": perfil, "perfil_nombre": PERFILES[perfil]["nombre"],
            "etapas": etapas, "decisiones": decisiones, "costo": round(getattr(motor, "costo", 0.0), 6),
            "motor": motor.nombre, "poco": poco, "videos_del_canal": total}
