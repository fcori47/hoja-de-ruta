# Hoja de ruta

Le pasás la URL de un canal de YouTube, le contás qué querés lograr y te arma la hoja de ruta con sus videos: cuáles ver y en qué orden, por etapas.

![La hoja de ruta armada con JEV: 443 videos leídos, 467 decisiones en 26,6 s](docs/captura.png)

No escribe nada. Lee todos los títulos del canal y decide dos cosas, video por video:

1. **¿Este video te sirve para lo que querés lograr?** Un sí o no, con su probabilidad, a todo el canal.
2. **¿En qué etapa del camino va?** Un sí o no por cada etapa, solo a los que sirven.

Con eso arma la ruta: cada etapa se queda con los videos que le encajan y, de esos, con los que más te sirven y los más nuevos. Todo lo que ves son videos que existen en el canal: no hay nada inventado.

Las etapas dependen de quién sos:

| Perfil | Etapas |
|---|---|
| Quiero aprender | Entender qué es · Hacerlo por primera vez · Mejorarlo · Ir más allá |
| Tengo una empresa | Qué le sirve a tu empresa · Casos reales · Cómo se implementa · Que siga andando |
| Quiero ofrecerlo como servicio | Entender qué es · Qué ofrecer · Conseguir clientes · Cierre y entrega de servicio |

## Quién decide

Dos modelos que deciden en vez de escribir, con la misma forma de preguntar:

- **JEV** (`typesafe/jev-1.13`), por OpenRouter, con tu clave.
- **Laya**, el modelo abierto, en tu compu y gratis.

Lo que se midió armando rutas con un canal de 443 videos, en una RTX 4070 Ti SUPER:

| | JEV | Laya sin entrenar |
|---|---|---|
| Lo que tarda la ruta | 16 a 26 s (unas 500 decisiones, de a doce a la vez) | unos 30 s (de a una, ~65 ms cada una) |
| Lo que cuesta | unos USD 0,0077 por ruta: menos de un centavo | nada |
| ¿Entiende lo que querés? | Sí | No: lee el tema, no el pedido |

**Laya sin entrenar no sirve para esto.** De sus 15 primeros videos coincidió con JEV en 0 a 3, y a casi todo el canal le dio «sirve» con 0,9 o más. Se probaron cuatro formas de preguntarle y dio igual.

La regla sigue siendo «en tu compu, Laya; en un servidor, JEV». Pero para entender lo que alguien quiere, hoy conviene JEV.

## Cómo se instala

Necesitás Python 3.10 o más nuevo.

```
pip install yt-dlp
```

Con eso ya anda con JEV. Para usar Laya, que es opcional:

```
pip install laya
```

Además va PyTorch. Con placa NVIDIA, instalá la versión con CUDA: en pytorch.org elegís tu sistema y tu CUDA, y te da el comando. Sin placa también anda, pero tarda casi un segundo por decisión.

## Cómo se usa

```
python app.py
```

Se abre http://127.0.0.1:8765 en tu navegador. Ahí:

1. Pegás el canal.
2. Contás qué querés lograr.
3. Elegís quién sos y quién decide.

Mientras decide, ves pasar cada video con su probabilidad.

Cuando termina, podés hacer tres cosas:

- marcar los videos que ya viste, que quedan guardados en tu navegador;
- abrir la ruta como playlist de YouTube;
- descargarla como una página suelta.

**La clave de OpenRouter** se saca en openrouter.ai → Keys. Hay tres formas de pasársela:

- Pegarla en la página: se usa para esa ruta y no se guarda.
- Dejarla en la variable de entorno `OPENROUTER_API_KEY`.
- Dejarla en un archivo `.env` al lado de `app.py`:

```
OPENROUTER_API_KEY=sk-or-...
```

**Opciones:**

- `python app.py --no-abrir` levanta el servidor sin abrir el navegador.
- `--puerto 9000` es por si el 8765 está ocupado.
- `--sin-precargar` no carga Laya al arrancar: queda para la primera ruta que lo use.

Los videos de cada canal se guardan un día en `canales/`, así la segunda ruta arranca al toque.

## Qué hay adentro

| Archivo | Qué hace |
|---|---|
| `app.py` | el servidor local y lo que le contesta a la página (solo biblioteca estándar de Python) |
| `ruta.py` | arma la ruta: las dos pasadas de decisiones y el reparto en etapas |
| `motor.py` | JEV y Laya, con la misma forma de preguntar |
| `canal.py` | lee los videos de un canal con yt-dlp, sin clave de YouTube |
| `web/` | la página |

## Tu clave

- El servidor escucha solo en tu compu (127.0.0.1).
- Rechaza los pedidos que vienen de otra página o con otro nombre: una web abierta en tu navegador no puede usar tu clave.
- La clave que pegás vive en memoria mientras se arma la ruta. No se escribe en ningún archivo ni en ningún registro.

## Licencia

MIT. Lo armó Facundo Corengia.
