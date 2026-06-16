# -*- coding: utf-8 -*-
"""
Galaxy Beats FM — versão Vercel/PC modo Super Deus.
- Flask app pronto para Vercel em api/index.py
- Sem Playwright obrigatório no runtime
- Histórico em /tmp no Vercel para evitar erro de sistema read-only
- Identificação por API externa e fallback ShazamIO on-demand
"""

from __future__ import annotations

import asyncio
import html
import json
import logging
import os
import re
import time
import tempfile
from collections import deque
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus
from zoneinfo import ZoneInfo

import requests
from flask import Flask, jsonify, render_template, request, g

# ─────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parents[1]
TZ = ZoneInfo("Europe/Lisbon")
UA = {"User-Agent": "GalaxyBeatsFM/2.0 (+github.com/ruicirilo271)"}
TIMEOUT = 8
IS_VERCEL = bool(os.getenv("VERCEL") or os.getenv("AWS_LAMBDA_FUNCTION_NAME"))
TMP_DIR = Path(tempfile.gettempdir())

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s: %(message)s")
logger = logging.getLogger("galaxybeats")

# ───────────── Chaves e ficheiros ─────────────
DEFAULT_COVER = "/static/default_cover.png"
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "").strip()
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY", "").strip()

# No Vercel só é seguro gravar em /tmp.
HISTORY_FILE = Path(
    os.getenv("HISTORY_FILE")
    or (str(TMP_DIR / "galaxybeats_history.json") if IS_VERCEL else str(BASE_DIR / "history.json"))
)
SEED_HISTORY_FILE = BASE_DIR / "history.json"

DEMO_URL = "https://streams.radio.co/s0d51f35d2/listen"

# ───────────── Estações ─────────────
STATIONS: dict[str, dict[str, str]] = {
    "MOTARD": {
        "nome": "Rádio Motard",
        "url": os.getenv("URL_MOTARD", DEMO_URL),
        "logo": "https://cdn.onlineradiobox.com/img/l/1/45671.v8.png",
    },
    "RENASCENCA": {
        "nome": "Rádio Renascença",
        "url": os.getenv("URL_RENASCENCA", DEMO_URL),
        "logo": "https://cdn.onlineradiobox.com/img/l/1/19431.v4.png",
    },
    "CIDADEFM": {
        "nome": "Cidade FM",
        "url": os.getenv("URL_CIDADEFM", DEMO_URL),
        "logo": "https://cdn.onlineradiobox.com/img/l/1/71601.v15.png",
    },
    "RADIOCIDADE": {
        "nome": "Rádio Cidade",
        "url": os.getenv("URL_RADIOCIDADE", DEMO_URL),
        "logo": "https://cdn.onlineradiobox.com/img/l/3/93733.v4.png",
    },
    "RECORD": {
        "nome": "Rádio Record",
        "url": os.getenv("URL_RECORD", DEMO_URL),
        "logo": "https://cdn.onlineradiobox.com/img/l/9/19399.v8.png",
    },
    "ANTENA1": {
        "nome": "Antena 1",
        "url": os.getenv("URL_ANTENA1", DEMO_URL),
        "logo": "https://cdn.onlineradiobox.com/img/l/5/45585.v5.png",
    },
}

SCHEDULE = [
    ("00:00", "MOTARD", "Rock Sem Limites", "DJ Carlos Speed", "Clássicos e novidades do rock mundial."),
    ("02:00", "RENASCENCA", "Noite de Paz", "Pe. António Vieira", "Reflexões noturnas e música suave."),
    ("04:00", "RENASCENCA", "Madrugada RR", "Joana Mendes", "Informação, entrevistas e espiritualidade."),
    ("06:00", "RADIOCIDADE", "Wake Up Cidade", "DJ Nuno Luz", "Pop & hits para acordar com energia."),
    ("09:00", "CIDADEFM", "Manhãs da Cidade", "Diogo Pires", "Os maiores êxitos com boa disposição."),
    ("11:00", "RENASCENCA", "Tempo de Fé", "Ana Sofia Cardoso", "Espaço de reflexão e espiritualidade."),
    ("13:00", "RECORD", "Brasil no Ar", "Rogério Alves", "Notícias, cultura e música brasileira."),
    ("14:00", "CIDADEFM", "Tardes da Cidade", "Catarina Palma", "Novidades pop e convidados especiais."),
    ("16:00", "RADIOCIDADE", "Top 20 Cidade", "DJ Vasco Alves", "Os 20 hits mais ouvidos da semana."),
    ("18:00", "MOTARD", "Estrada Livre", "DJ Roadmaster", "Rock e metal para acompanhar a condução."),
    ("19:00", "ANTENA1", "60 Minutos", "Jornalistas Antena 1", "Análise dos temas do dia."),
    ("20:00", "CIDADEFM", "Noite Pop", "DJ Kiko", "A playlist perfeita para relaxar e curtir."),
    ("22:00", "MOTARD", "Midnight Ride", "DJ Raven", "O melhor do rock pesado até de madrugada."),
]

HISTORY: deque[dict[str, Any]] = deque(maxlen=120)
_SPOTIFY_TOKEN_CACHE: dict[str, Any] = {"token": None, "expires_at": 0}

# ───────────── Flask setup ─────────────
app = Flask(
    __name__,
    static_folder=str(BASE_DIR / "static"),
    template_folder=str(BASE_DIR / "templates"),
)


@app.before_request
def before() -> None:
    g.start = datetime.now(TZ)


@app.after_request
def after(resp):
    try:
        dt = (datetime.now(TZ) - g.start).total_seconds()
        logger.info("%s %s [%s] %.2fs", request.method, request.path, resp.status_code, dt)
    except Exception:
        pass
    return resp


@app.route("/")
def index():
    return render_template("index.html")


@app.get("/health")
def health():
    return jsonify(
        {
            "ok": True,
            "app": "Galaxy Beats FM Super Deus",
            "time": datetime.now(TZ).isoformat(),
            "platform": "vercel" if IS_VERCEL else "local",
            "history_file": str(HISTORY_FILE),
            "youtube_api_key_ready": bool(YOUTUBE_API_KEY),
            "spotify_ready": bool(SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET),
            "lastfm_ready": bool(LASTFM_API_KEY),
            "stations": list(STATIONS.keys()),
        }
    )


# ───────────── Histórico ─────────────
def load_history() -> None:
    """Carrega histórico. Em Vercel tenta /tmp e, se não existir, usa history.json como seed."""
    sources = [HISTORY_FILE]
    if SEED_HISTORY_FILE not in sources:
        sources.append(SEED_HISTORY_FILE)

    loaded = False
    for source in sources:
        try:
            if source.exists():
                with source.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    HISTORY.clear()
                    # O ficheiro é gravado em ordem antiga → nova. appendleft deixa a nova no topo.
                    for it in data[-120:]:
                        if isinstance(it, dict):
                            HISTORY.appendleft(it)
                    logger.info("Histórico carregado de %s (%s)", source, len(HISTORY))
                    loaded = True
                    break
        except Exception as e:
            logger.warning("Falha a carregar histórico %s: %s", source, e)

    if not loaded:
        logger.info("Sem histórico inicial.")


def save_history() -> None:
    try:
        HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        with HISTORY_FILE.open("w", encoding="utf-8") as f:
            json.dump(list(HISTORY)[::-1], f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Falha a gravar histórico em %s: %s", HISTORY_FILE, e)


def add_history(key: str, station_name: str, artist: str, title: str, source: str) -> None:
    now = datetime.now(TZ)
    artist = (artist or "").strip()
    title = (title or "").strip()
    if not artist or not title or title == "—":
        return

    for it in list(HISTORY)[:8]:
        try:
            same = (
                it.get("station_id") == key
                and (it.get("artist") or "").casefold() == artist.casefold()
                and (it.get("title") or "").casefold() == title.casefold()
            )
            recent = (now - datetime.fromisoformat(it.get("when"))).total_seconds() < 240
            if same and recent:
                return
        except Exception:
            continue

    HISTORY.appendleft(
        {
            "when": now.isoformat(),
            "station_id": key,
            "station": station_name,
            "artist": artist,
            "title": title,
            "source": source,
        }
    )
    save_history()


# ───────────── Helpers programação ─────────────
def parse_hhmm(h: str) -> dtime:
    hour, minute = map(int, h.split(":"))
    return dtime(hour=hour, minute=minute)


def schedule_today(now: datetime):
    today = now.date()
    items = []
    for hhmm, key, prog, dj, desc in SCHEDULE:
        dt = datetime.combine(today, parse_hhmm(hhmm), tzinfo=TZ)
        items.append((dt, key, prog, dj, desc))
    first = items[0]
    items.append((first[0] + timedelta(days=1), first[1], first[2], first[3], first[4]))
    return items


def current_slot(now: datetime):
    items = schedule_today(now)
    for i in range(len(items) - 1):
        start, key, _, _, _ = items[i]
        end = items[i + 1][0]
        if start <= now < end:
            return i, start, end, key
    return 0, items[0][0], items[1][0], items[0][1]


def key_from_request(default_auto: bool = True) -> str:
    forced = (request.args.get("force") or "").strip().upper()
    if forced in STATIONS:
        return forced
    if default_auto:
        _, _, _, key = current_slot(datetime.now(TZ))
        return key
    return ""


def split_joined_title(value: str) -> tuple[str, str]:
    if not value or value == "—":
        return "", ""
    for sep in (" – ", " — ", " - "):
        if sep in value:
            left, right = value.split(sep, 1)
            # A app usa: música – artista
            return left.strip(), right.strip()
    return value.strip(), ""


def clean_text(value: str, limit: int = 1200) -> str:
    value = re.sub(r"<[^>]+>", "", value or "")
    value = html.unescape(value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


# ───────────── APIs de enriquecimento ─────────────
def spotify_get_token() -> Optional[str]:
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        return None
    now = time.time()
    if _SPOTIFY_TOKEN_CACHE.get("token") and _SPOTIFY_TOKEN_CACHE.get("expires_at", 0) > now + 60:
        return _SPOTIFY_TOKEN_CACHE["token"]
    try:
        r = requests.post(
            "https://accounts.spotify.com/api/token",
            data={"grant_type": "client_credentials"},
            auth=(SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET),
            timeout=TIMEOUT,
            headers=UA,
        )
        if r.ok:
            data = r.json()
            token = data.get("access_token")
            if token:
                _SPOTIFY_TOKEN_CACHE["token"] = token
                _SPOTIFY_TOKEN_CACHE["expires_at"] = now + int(data.get("expires_in", 3600))
                return token
        logger.warning("Spotify token falhou: %s %s", r.status_code, r.text[:120])
    except Exception as e:
        logger.warning("Spotify token erro: %s", e)
    return None


def itunes_cover(artist: str, title: str) -> Optional[str]:
    try:
        r = requests.get(
            "https://itunes.apple.com/search",
            params={"term": f"{artist} {title}", "media": "music", "entity": "song", "limit": 1},
            timeout=TIMEOUT,
            headers=UA,
        )
        if r.ok:
            items = r.json().get("results", [])
            if items:
                artwork = items[0].get("artworkUrl100") or items[0].get("artworkUrl60")
                if artwork:
                    return artwork.replace("100x100bb", "600x600bb").replace("60x60bb", "600x600bb")
    except Exception as e:
        logger.warning("iTunes cover erro: %s", e)
    return None


def spotify_cover(artist: str, title: str) -> Optional[str]:
    token = spotify_get_token()
    if not token:
        return itunes_cover(artist, title)
    try:
        queries = [f'track:"{title}" artist:"{artist}"', f"{artist} {title}"]
        for q in queries:
            r = requests.get(
                "https://api.spotify.com/v1/search",
                headers={"Authorization": f"Bearer {token}", **UA},
                params={"q": q, "type": "track", "limit": 1},
                timeout=TIMEOUT,
            )
            if r.ok:
                items = r.json().get("tracks", {}).get("items", [])
                if items:
                    images = items[0].get("album", {}).get("images", [])
                    if images:
                        return images[0].get("url")
        return itunes_cover(artist, title)
    except Exception as e:
        logger.warning("Spotify cover erro: %s", e)
        return itunes_cover(artist, title)


def lastfm_bio(artist: str) -> Optional[str]:
    if not LASTFM_API_KEY:
        return None
    try:
        r = requests.get(
            "https://ws.audioscrobbler.com/2.0/",
            params={"method": "artist.getinfo", "artist": artist, "api_key": LASTFM_API_KEY, "format": "json", "lang": "pt"},
            timeout=TIMEOUT,
            headers=UA,
        )
        if r.ok:
            summary = r.json().get("artist", {}).get("bio", {}).get("summary", "") or ""
            return clean_text(summary, 1300)
    except Exception as e:
        logger.warning("Last.fm bio erro: %s", e)
    return None


def lyrics_ovh(artist: str, title: str) -> Optional[str]:
    try:
        r = requests.get(
            f"https://api.lyrics.ovh/v1/{quote_plus(artist)}/{quote_plus(title)}",
            timeout=TIMEOUT,
            headers=UA,
        )
        if r.ok:
            lyrics = r.json().get("lyrics", "") or ""
            return lyrics.strip()[:4500]
    except Exception as e:
        logger.warning("Lyrics erro: %s", e)
    return None


def clean_youtube_query_part(value: str) -> str:
    value = html.unescape(value or "")
    value = re.sub(r"\[[^\]]+\]", " ", value)
    value = re.sub(r"\([^)]*(radio|remaster|edit|mix|version|explicit|clean)[^)]*\)", " ", value, flags=re.I)
    value = re.sub(r"\s+", " ", value).strip(" -–—_|•")
    return value


def _youtube_video_is_playable(video: dict[str, Any], country: str = "PT") -> bool:
    """Valida se o vídeo deve tocar dentro do iframe em Portugal."""
    status = video.get("status") or {}
    details = video.get("contentDetails") or {}
    restriction = details.get("regionRestriction") or {}

    if status.get("privacyStatus") != "public":
        return False
    if status.get("embeddable") is not True:
        return False

    blocked = restriction.get("blocked") or []
    allowed = restriction.get("allowed")

    if country in blocked:
        return False
    if isinstance(allowed, list) and allowed and country not in allowed:
        return False
    if isinstance(allowed, list) and len(allowed) == 0:
        return False

    return True


def _youtube_filter_playable_candidates(ids: list[str], country: str = "PT") -> dict[str, dict[str, Any]]:
    """
    Confirma os IDs devolvidos pelo search.list com videos.list.
    Isto evita muitos casos de "Video unavailable" no iframe.
    """
    if not ids or not YOUTUBE_API_KEY:
        return {}

    try:
        r = requests.get(
            "https://www.googleapis.com/youtube/v3/videos",
            params={
                "part": "snippet,status,contentDetails",
                "id": ",".join(ids[:50]),
                "key": YOUTUBE_API_KEY,
            },
            timeout=TIMEOUT,
            headers=UA,
        )
        data = r.json() if r.headers.get("content-type", "").lower().startswith("application/json") else {}
        if not r.ok:
            msg = (data.get("error") or {}).get("message") or r.text[:180]
            logger.warning("YouTube videos.list falhou: %s %s", r.status_code, msg)
            return {}

        playable: dict[str, dict[str, Any]] = {}
        for item in data.get("items", []) or []:
            vid = item.get("id") or ""
            if vid and _youtube_video_is_playable(item, country=country):
                playable[vid] = item
        return playable
    except Exception as e:
        logger.warning("YouTube videos.list erro: %s", e)
        return {}


def youtube_search_info(artist: str, title: str) -> dict[str, Any]:
    """
    Procura um vídeo no YouTube que seja realmente embutível.

    Importante:
    - search.list com videoEmbeddable=true nem sempre chega para evitar "Video unavailable".
    - Por isso também uso videoSyndicated=true e confirmo cada ID com videos.list/status.embeddable.
    """
    artist_q = clean_youtube_query_part(artist)
    title_q = clean_youtube_query_part(title)

    if not artist_q or not title_q:
        return {"embed_url": "", "watch_url": "", "video_id": "", "title": "", "error": "Artista ou música em falta."}

    if not YOUTUBE_API_KEY:
        return {
            "embed_url": "",
            "watch_url": "",
            "video_id": "",
            "title": "",
            "error": "YOUTUBE_API_KEY em falta no Vercel.",
        }

    # Preferir official audio/lyric quando for música: costuma bloquear menos no iframe do que alguns VEVO oficiais.
    queries = [
        f'"{artist_q}" "{title_q}" official audio',
        f'"{artist_q}" "{title_q}" lyric video',
        f'"{artist_q}" "{title_q}" official music video',
        f'{artist_q} {title_q} official audio',
        f'{artist_q} {title_q}',
    ]

    last_error = "Vídeo não encontrado ou bloqueado para iframe."
    seen: set[str] = set()

    for q in queries:
        try:
            r = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "part": "snippet",
                    "q": q,
                    "maxResults": 10,
                    "type": "video",
                    "key": YOUTUBE_API_KEY,
                    "videoEmbeddable": "true",
                    "videoSyndicated": "true",
                    "safeSearch": "none",
                    "regionCode": "PT",
                },
                timeout=TIMEOUT,
                headers=UA,
            )

            try:
                data = r.json()
            except Exception:
                data = {}

            if not r.ok:
                msg = (data.get("error") or {}).get("message") or r.text[:180]
                last_error = f"YouTube API: {msg}"
                logger.warning("YouTube search.list falhou: %s %s", r.status_code, msg)
                continue

            candidates: list[tuple[str, str]] = []
            for item in data.get("items", []) or []:
                vid = (item.get("id") or {}).get("videoId") or ""
                if not vid or vid in seen:
                    continue
                seen.add(vid)
                yt_title = (item.get("snippet") or {}).get("title") or ""
                candidates.append((vid, yt_title))

            if not candidates:
                continue

            playable = _youtube_filter_playable_candidates([vid for vid, _ in candidates], country="PT")
            for vid, yt_title in candidates:
                if vid not in playable:
                    continue
                return {
                    "embed_url": f"https://www.youtube-nocookie.com/embed/{vid}",
                    "watch_url": f"https://www.youtube.com/watch?v={vid}",
                    "video_id": vid,
                    "title": yt_title or ((playable[vid].get("snippet") or {}).get("title") or ""),
                    "error": "",
                }

            last_error = "A API encontrou vídeos, mas estavam bloqueados para iframe ou para Portugal."

        except Exception as e:
            last_error = f"Erro a contactar o YouTube: {e}"
            logger.warning("YouTube erro: %s", e)

    return {"embed_url": "", "watch_url": "", "video_id": "", "title": "", "error": last_error}

def youtube_video(artist: str, title: str) -> Optional[str]:
    # Mantido por compatibilidade com código antigo.
    info = youtube_search_info(artist, title)
    return info.get("embed_url") or None


# ───────────── Metadata/identificação ─────────────
def radio_metadata_api(url: str) -> tuple[str, str, str]:
    """Tenta API externa. Retorna música, artista, fonte."""
    apis = [
        f"https://radio-metadata-api-main.vercel.app/radio_info/?radio_url={quote_plus(url)}",
        f"https://twj.es/get_stream_title/?url={quote_plus(url)}",
    ]
    for api in apis:
        try:
            r = requests.get(api, timeout=TIMEOUT, headers=UA)
            if not r.ok:
                continue
            d = r.json()
            song = (
                d.get("title")
                or d.get("song")
                or d.get("now_playing")
                or d.get("stream_title")
                or d.get("current_song")
                or ""
            )
            artist = d.get("artist") or d.get("performer") or d.get("author") or ""
            if isinstance(song, dict):
                artist = song.get("artist") or artist
                song = song.get("title") or song.get("song") or ""
            if song:
                return str(song).strip(), str(artist).strip(), "metadata-api"
        except Exception as e:
            logger.warning("metadata API erro: %s", e)
    return "", "", ""


def capture_stream_sample(url: str, key: str, seconds: int = 14, max_bytes: int = 900_000) -> Optional[Path]:
    """Grava uma amostra curta do stream para /tmp sem ffmpeg, adequado ao Vercel."""
    sample = TMP_DIR / f"galaxybeats_{key}_{int(time.time())}.mp3"
    deadline = time.time() + seconds
    total = 0
    try:
        with requests.get(url, headers=UA, stream=True, timeout=(6, seconds + 8)) as r:
            r.raise_for_status()
            with sample.open("wb") as f:
                for chunk in r.iter_content(chunk_size=32_768):
                    if chunk:
                        f.write(chunk)
                        total += len(chunk)
                    if total >= max_bytes or time.time() >= deadline:
                        break
        if total < 20_000:
            logger.warning("Amostra muito pequena: %s bytes", total)
            return None
        logger.info("Amostra gravada: %s bytes em %s", total, sample)
        return sample
    except Exception as e:
        logger.warning("Falha ao gravar amostra %s: %s", key, e)
        try:
            sample.unlink(missing_ok=True)
        except Exception:
            pass
        return None


async def recognize_shazam(url: str, key: str) -> Optional[dict[str, Any]]:
    try:
        from shazamio import Shazam  # import lazy para a app não cair se faltar pacote localmente
    except Exception as e:
        logger.warning("ShazamIO não está instalado/disponível: %s", e)
        return None

    sample = capture_stream_sample(url, key)
    if not sample:
        return None
    try:
        shazam = Shazam()
        result = await shazam.recognize(str(sample))
        if result and result.get("track"):
            logger.info("Shazam reconheceu: %s – %s", result["track"].get("title"), result["track"].get("subtitle"))
        return result
    except Exception as e:
        logger.warning("Shazam erro: %s", e)
        return None
    finally:
        try:
            sample.unlink(missing_ok=True)
        except Exception:
            pass


def identify_track(key: str) -> dict[str, Any]:
    now = datetime.now(TZ)
    st = STATIONS[key]
    cache_file = TMP_DIR / f"galaxybeats_meta_{key}.json"

    try:
        if cache_file.exists():
            age = time.time() - cache_file.stat().st_mtime
            if age < 90:
                with cache_file.open("r", encoding="utf-8") as f:
                    return json.load(f)
    except Exception:
        pass

    song = ""
    artist = ""
    source = "—"

    # 1) API externa rápida
    song, artist, source = radio_metadata_api(st["url"])

    # 2) Fallback Shazam universal. Sem threads e sem ffmpeg.
    if not song:
        res = asyncio.run(recognize_shazam(st["url"], key))
        if res and res.get("track"):
            track = res["track"]
            song = (track.get("title") or "").strip()
            artist = (track.get("subtitle") or "").strip()
            source = "ShazamIO"

    title_joined = f"{song} – {artist}" if song and artist else (song or "—")
    if song and artist:
        add_history(key, st["nome"], artist, song, source)

    data = {
        "radio": st["nome"],
        "station_id": key,
        "title": title_joined,
        "song": song or "",
        "artist": artist or "",
        "source": source,
        "timestamp": now.isoformat(),
    }
    try:
        with cache_file.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
    except Exception:
        pass
    return data


# ───────────── API endpoints ─────────────
@app.get("/now")
def now_endpoint():
    now = datetime.now(TZ)
    items = schedule_today(now)
    forced = (request.args.get("force") or "").strip().upper()

    if forced in STATIONS:
        key = forced
        st = STATIONS[key]
        start_dt = now.replace(second=0, microsecond=0)
        end_dt = start_dt + timedelta(hours=1)
        prog = "Modo Manual"
        dj = "Selecionado por ti"
        desc = f"Rádio fixa: {st['nome']}"
        base_idx = next((i for i, (_, k, _, _, _) in enumerate(items[:-1]) if k == key), 0)
        nxt_idx = (base_idx + 1) % (len(items) - 1)
        nxt_time, nxt_key, nxt_prog, nxt_dj, nxt_desc = items[nxt_idx]
    else:
        idx, start_dt, end_dt, key = current_slot(now)
        st = STATIONS[key]
        nxt_idx = (idx + 1) % (len(items) - 1)
        nxt_time, nxt_key, nxt_prog, nxt_dj, nxt_desc = items[nxt_idx]
        _, _, prog, dj, desc = items[idx]

    nxt = STATIONS[nxt_key]
    return jsonify(
        {
            "timezone": "Europe/Lisbon",
            "server_time": now.isoformat(),
            "agora": {
                "id": key,
                "titulo": st["nome"],
                "url": st["url"],
                "logo": st["logo"],
                "inicio": start_dt.isoformat(),
                "fim": end_dt.isoformat(),
                "programa": prog,
                "dj": dj,
                "descricao": desc,
            },
            "proximo": {
                "id": nxt_key,
                "titulo": nxt["nome"],
                "quando": nxt_time.isoformat(),
                "logo": nxt["logo"],
                "programa": nxt_prog,
                "dj": nxt_dj,
                "descricao": nxt_desc,
            },
            "schedule": [
                {"hora": h, "id": k, "titulo": STATIONS[k]["nome"], "programa": p, "dj": dj, "descricao": d}
                for (h, k, p, dj, d) in SCHEDULE
            ],
        }
    )


@app.get("/metadata")
def metadata():
    key = key_from_request(default_auto=True)
    try:
        return jsonify(identify_track(key))
    except Exception as e:
        logger.exception("Erro em /metadata")
        st = STATIONS.get(key, {"nome": "—"})
        return jsonify({"radio": st["nome"], "station_id": key, "title": "—", "source": f"erro: {e}"})


@app.get("/history")
def history():
    return jsonify(list(HISTORY))


@app.get("/enrich")
def enrich():
    artist = (request.args.get("artist") or "").strip()
    title = (request.args.get("title") or "").strip()
    if not artist or not title:
        return jsonify({"error": "artist e title são obrigatórios"}), 400

    cover = spotify_cover(artist, title) or (request.url_root.rstrip("/") + DEFAULT_COVER)
    bio = lastfm_bio(artist) or ""
    lyrics = lyrics_ovh(artist, title) or ""
    yt_info = youtube_search_info(artist, title)

    return jsonify(
        {
            "artist": artist,
            "title": title,
            "cover": cover,
            "bio": bio,
            "lyrics": lyrics,
            "youtube": yt_info.get("embed_url") or "",
            "youtube_id": yt_info.get("video_id") or "",
            "youtube_watch": yt_info.get("watch_url") or "",
            "youtube_title": yt_info.get("title") or "",
            "youtube_error": yt_info.get("error") or "",
            "youtube_api_key_ready": bool(YOUTUBE_API_KEY),
        }
    )


# Carrega histórico também quando a app é importada pelo Vercel.
load_history()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "8250"))
    app.run(host="0.0.0.0", port=port, debug=True)
