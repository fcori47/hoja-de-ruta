# -*- coding: utf-8 -*-
"""Los videos de un canal de YouTube, sin clave de YouTube: yt-dlp lee la pestaña «Videos» del canal.

Solo los largos (los Shorts y los directos viven en otras pestañas). Los títulos se piden en castellano:
sin eso YouTube los devuelve traducidos al idioma del pedido (a veces en inglés).
"""
import json
import re
import time
from pathlib import Path

CACHE = Path(__file__).resolve().parent / "canales"


def normalizar_url(url: str) -> str:
    url = (url or "").strip()
    if not url:
        raise ValueError("Pegá la URL del canal (por ejemplo https://www.youtube.com/@facundocorengia).")
    if url.startswith("@"):
        url = "https://www.youtube.com/" + url
    if not url.startswith("http"):
        url = "https://" + url
    url = re.sub(r"[?#].*$", "", url).rstrip("/")
    url = re.sub(r"/(videos|shorts|streams|featured|playlists|community|about)$", "", url)
    if not re.search(r"youtube\.com/(@[^/]+|channel/[^/]+|c/[^/]+|user/[^/]+)$", url):
        raise ValueError("Eso no parece la URL de un canal de YouTube (tiene que ser como youtube.com/@canal).")
    return url + "/videos"


def videos_del_canal(url: str, usar_cache: bool = True, horas_cache: int = 24) -> dict:
    url = normalizar_url(url)
    CACHE.mkdir(exist_ok=True)
    archivo = CACHE / (re.sub(r"[^a-zA-Z0-9@_-]+", "_", url.split("youtube.com/")[1].replace("/videos", "")) + ".json")
    if usar_cache and archivo.exists() and time.time() - archivo.stat().st_mtime < horas_cache * 3600:
        return json.loads(archivo.read_text(encoding="utf-8"))
    import yt_dlp
    opts = {"extract_flat": "in_playlist", "quiet": True, "skip_download": True, "noprogress": True,
            "no_warnings": True, "extractor_args": {"youtube": {"lang": ["es"]}}}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=False)
    videos = []
    for i, e in enumerate(info.get("entries") or []):
        if not e or not e.get("id") or not e.get("title"):
            continue
        videos.append({"id": e["id"], "titulo": e["title"].replace("​", "").strip(),
                       "segundos": int(e.get("duration") or 0), "vistas": int(e.get("view_count") or 0),
                       "orden": i})   # 0 = el más nuevo
    datos = {"canal": info.get("channel") or info.get("uploader") or info.get("title") or "",
             "url": url, "videos": videos, "leido": time.strftime("%Y-%m-%d %H:%M")}
    archivo.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
    return datos
