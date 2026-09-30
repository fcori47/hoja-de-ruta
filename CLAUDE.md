# CLAUDE.md — Hoja de ruta

Instrucciones para Claude Code, Codex o cualquier asistente que trabaje en este repo.

**Qué es:** una app local que arma una hoja de ruta con los videos de un canal de YouTube. La persona pega el canal,
escribe qué quiere lograr y elige su perfil. Un modelo que **decide** (JEV por OpenRouter, o Laya en la compu) elige
qué videos le sirven y en qué etapa van. No genera texto: solo elige entre los videos que existen.

## Instalar y levantar

1. Python 3.10 o más nuevo. Un entorno virtual:
   ```bash
   python -m venv .venv
   # Windows: .venv\Scripts\activate   ·   macOS/Linux: source .venv/bin/activate
   pip install -r requirements.txt
   ```
2. **La clave de OpenRouter se la pedís a la persona.** Copiás `.env.example` a `.env` y la ponés ahí:
   `OPENROUTER_API_KEY=sk-or-...`
   - ⛔ Nunca en el código, nunca en un commit y nunca impresa en la terminal ni en un log.
   - Si no tiene clave: openrouter.ai → Keys. Con USD 5 de crédito alcanza para cientos de rutas.
3. Levantar:
   ```bash
   python app.py              # abre http://127.0.0.1:8765
   python app.py --no-abrir   # sin abrir el navegador
   python app.py --puerto 9000
   ```
4. **Laya es opcional:** `pip install laya`, más PyTorch (con placa NVIDIA, la versión CUDA de pytorch.org). Sin
   entrenar arma rutas casi al azar: la app arranca con JEV elegido a propósito.

## Probar que anda, sin navegador

El servidor responde en `http://127.0.0.1:8765`:

| Pedido | Qué devuelve |
|---|---|
| `GET /api/motores` | si Laya está instalado, si hay clave guardada (solo `true`/`false`, nunca la clave) y los perfiles |
| `GET /api/canal?url=@canal` | el nombre del canal y cuántos videos tiene |
| `POST /api/ruta` con JSON `{canal, objetivo, perfil, motor, clave?}` | `{id}` del trabajo |
| `GET /api/progreso/<id>?desde=N` | `{estado: corriendo·listo·error, eventos, resultado}` |

`perfil` es `aprender`, `empresa` o `agencia`. `motor` es `jev` o `laya`. `clave` es opcional: si falta, se usa la
del `.env`.

Prueba rápida en Python (con la app levantada y la clave en el `.env`):

```python
import json, time, urllib.request
def api(ruta, datos=None):
    req = urllib.request.Request("http://127.0.0.1:8765" + ruta, method="POST" if datos else "GET",
                                 data=json.dumps(datos).encode() if datos else None,
                                 headers={"Content-Type": "application/json"} if datos else {})
    return json.loads(urllib.request.urlopen(req, timeout=60).read())
t = api("/api/ruta", {"canal": "@facundocorengia", "objetivo": "quiero aprender a usar Claude Code",
                      "perfil": "aprender", "motor": "jev"})
while (p := api(f"/api/progreso/{t['id']}"))["estado"] == "corriendo":
    time.sleep(1)
print(p["estado"], [(e["nombre"], len(e["videos"])) for e in (p["resultado"] or {}).get("etapas", [])])
```

Lo esperable con JEV: un canal de ~400 videos tarda 13 a 26 s, hace unas 500 decisiones y cuesta ~USD 0,0075. Si
`estado` es `error`, el texto de `error` ya viene en castellano y dice qué hacer.

## Cómo está hecho

| Archivo | Qué hace |
|---|---|
| `app.py` | Servidor local, **solo biblioteca estándar** (ThreadingHTTPServer). Un hilo por ruta; el progreso se pide por polling |
| `ruta.py` | Las dos pasadas: «¿sirve?» (un sí o no por video, de a 12 en paralelo con JEV) y «¿en qué etapa?» (un sí o no por etapa, en una sola llamada). Después reparte, ordena y saca los repetidos |
| `motor.py` | `JEV` (POST a `https://openrouter.ai/api/alpha/decisions`, modelo `typesafe/jev-1.13`) y `Laya` (`laya.Router`). Los dos reciben un estado en texto y preguntas `noul`, `choice` o `score` |
| `canal.py` | Los videos de la pestaña «Videos» del canal con yt-dlp (sin Shorts, títulos en castellano). Se guardan 24 h en `canales/` |
| `web/index.html` | La página: HTML, CSS y JS en un solo archivo, con `base.css` y las tipografías en `web/` |

Formato de las respuestas de los motores: `noul` devuelve `{"noul": 0.93}` y `choice` devuelve
`{"choice": "e1", "confidence": 0.8, "probabilities": {...}}`.

## Reglas del repo (no romperlas)

- **La clave de la persona es sagrada:** vive en memoria o en su `.env`. No se escribe en archivos, no se loguea y
  no la devuelve ningún endpoint.
- **El servidor escucha solo en 127.0.0.1** y rechaza pedidos con otro `Host` u otro `Origin`. Así una web abierta
  en el navegador no puede gastar su clave. ⛔ No pasarlo a `0.0.0.0`.
- **`app.py` sin dependencias:** nada de Flask ni FastAPI, así la instalación es un solo `pip install`.
- **El modelo decide, no escribe.** No agregar generación de texto: es lo que la hace barata y honesta, porque solo
  muestra videos que existen.
- **`typesafe/jev-1.13` va fijo**, no `latest`: con otra versión los umbrales cambian sin aviso.
- **La página está en castellano rioplatense** (voseo: «pegá», «contá», «elegí»). Los textos nuevos, igual.
- No se versionan `.env`, `canales/`, `__pycache__/`, logs ni entornos virtuales (ya están en `.gitignore`).

## Tareas comunes

**Agregar un perfil** (por ejemplo, «Soy docente»):
1. En `ruta.py`, sumalo a `PERFILES`: una clave, el `nombre` y la lista de `etapas`. Cada etapa es
   `(nombre, descripción)`, y **la descripción es lo que lee el modelo**: una frase concreta de qué entra ahí.
2. En `web/index.html`, sumá el botón al selector de «¿Quién sos?» (`data-v="<la clave>"`). Si pasan de 3, ajustá
   `--n` del selector.
3. Probalo con la API de arriba, con dos objetivos distintos.

**Cambiar el largo de la ruta:** `POR_ETAPA` en `ruta.py` (videos por etapa).

**Más exigente o más permisivo:**
- para «sirve», `UMBRAL` y `MARGEN`;
- para el reparto en etapas, `MIN_ETAPA`, `MARGEN_ETAPA` y `GENERAL`.

Después de tocar un umbral, probá con dos canales distintos: el que anda bien con uno puede vaciar etapas en otro.

## Si algo falla

| Síntoma | Causa y arreglo |
|---|---|
| `OpenRouter 529` · «JEV está saturado» | JEV se satura unos segundos. `motor.py` reintenta 3 veces con espera; si sigue, más tarde |
| «OpenRouter no aceptó la clave» | La clave está mal o sin crédito |
| No trae videos del canal | YouTube cambió: `pip install -U yt-dlp` |
| Laya tarda casi 1 s por decisión | No hay placa NVIDIA o PyTorch no tiene CUDA |
| El puerto está ocupado | `--puerto 9000` |
