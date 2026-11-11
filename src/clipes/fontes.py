"""De onde vem o vídeo: classifica a entrada, lê metadados e baixa só os trechos."""

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import download_range_func

from clipes.config import settings

FORMATO_720 = "bv*[height<=720]+ba/b[height<=720]/bv*+ba/b"


def classificar(origem: str) -> str:
    """Tipo da entrada a partir da URL (ou caminho local)."""
    if not origem.startswith(("http://", "https://")):
        return "upload"
    u = urlparse(origem)
    host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
    caminho = u.path.lower()
    if host in ("youtube.com", "youtu.be", "music.youtube.com"):
        return "youtube"
    if host == "clips.twitch.tv" or (host == "twitch.tv" and "/clip/" in caminho):
        return "twitch_clip"
    if host == "twitch.tv" and "/videos/" in caminho:
        return "twitch_vod"
    if host == "kick.com":
        return "kick"
    if caminho.endswith((".mp4", ".mov", ".mkv", ".webm")):
        return "mp4_url"
    return "generic"


@dataclass
class Info:
    tipo: str
    titulo: str
    canal: str
    duracao: float
    foi_live: bool = False
    heatmap: list[dict] = field(default_factory=list)
    comentarios: list[str] = field(default_factory=list)
    url: str = ""
    arquivo_local: Path | None = None


def _opts_base() -> dict[str, Any]:
    opts: dict[str, Any] = {"quiet": True, "no_warnings": True, "noprogress": True}
    if settings.ytdlp_cookies:
        opts["cookiefile"] = settings.ytdlp_cookies
    return opts


def duracao_arquivo(caminho: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(caminho)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def resolver(origem: str, tipo: str | None = None) -> Info:
    tipo = tipo or classificar(origem)
    if tipo == "upload":
        p = Path(origem)
        return Info(tipo, p.stem, "upload", duracao_arquivo(p), arquivo_local=p)

    opts = _opts_base() | {"skip_download": True}
    if tipo == "youtube":
        opts["getcomments"] = True
        opts["extractor_args"] = {"youtube": {"max_comments": ["300", "300", "0", "0"]}}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(origem, download=False)

    comentarios = [c.get("text", "") for c in (info.get("comments") or [])]
    return Info(
        tipo=tipo,
        titulo=info.get("title") or "",
        canal=info.get("uploader") or info.get("channel") or info.get("creator") or "desconhecido",
        duracao=float(info.get("duration") or 0),
        foi_live=bool(info.get("was_live")) or tipo == "twitch_vod",
        heatmap=info.get("heatmap") or [],
        comentarios=comentarios,
        url=info.get("webpage_url") or origem,
    )


def baixar_trecho(info: Info, inicio: float, fim: float, destino: Path) -> Path:
    """Baixa (ou corta, se local) só o trecho [inicio, fim] em até 720p. Retorna o .mp4."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if info.arquivo_local:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{inicio:.2f}", "-to", f"{fim:.2f}",
             "-i", str(info.arquivo_local), "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
             "-c:a", "aac", str(destino)],
            check=True,
        )
        return destino

    base = destino.with_suffix("")
    opts = _opts_base() | {
        "format": FORMATO_720,
        "outtmpl": str(base) + ".%(ext)s",
        "merge_output_format": "mp4",
        "download_ranges": download_range_func(None, [(inicio, fim)]),
    }
    with yt_dlp.YoutubeDL(opts) as ydl:
        ydl.download([info.url])
    feitos = sorted(base.parent.glob(base.name + ".*"))
    feitos = [f for f in feitos if f.suffix in (".mp4", ".mkv", ".webm")]
    if not feitos:
        raise RuntimeError(f"download do trecho {inicio:.0f}-{fim:.0f}s não gerou arquivo")
    if feitos[0] != destino:
        feitos[0].replace(destino)
    return destino


def baixar_inteiro(info: Info, destino: Path) -> Path:
    """Para vídeos curtos (clipe da Twitch, Short)."""
    if info.arquivo_local:
        return info.arquivo_local
    return baixar_trecho(info, 0, info.duracao or 600, destino)


def url_audio(info: Info) -> str:
    """URL direta (ou caminho) do áudio, para o ffmpeg ler em streaming sem baixar o vídeo."""
    if info.arquivo_local:
        return str(info.arquivo_local)
    opts = _opts_base() | {"format": "bestaudio/Audio_Only/worst", "skip_download": True}
    with yt_dlp.YoutubeDL(opts) as ydl:
        i = ydl.extract_info(info.url, download=False)
    if i.get("url"):
        return i["url"]
    for f in i.get("requested_formats") or []:
        if f.get("url"):
            return f["url"]
    raise RuntimeError("não achei URL de áudio")


_TS = re.compile(r"(?<![\d:])(?:(\d{1,2}):)?(\d{1,2}):(\d{2})(?![\d:])")


def minutagens(texto: str) -> list[int]:
    """'kkkk 2:14 e 1:02:33' -> [134, 3753]"""
    out = []
    for h, m, s in _TS.findall(texto):
        if int(s) >= 60:
            continue
        out.append(int(h or 0) * 3600 + int(m) * 60 + int(s))
    return out
