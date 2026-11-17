"""Twitch for the live monitor (spec 002): channel login, is-live check, recording, chat, last VOD.

No Twitch app or token needed: status and recording come from streamlink, chat from the
anonymous IRC login ("justinfan"), the VOD list from yt-dlp.
"""

import logging
import random
import re
import socket
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from clipes.config import settings

log = logging.getLogger(__name__)

_LOGIN = re.compile(r"^[a-z0-9_]{3,25}$")
_RESERVADOS = {"videos", "directory", "settings", "p", "search", "downloads", "jobs", "turbo"}

GATILHOS = (
    "kekw", "lul", "omegalul", "lmao", "lol", "pog", "poggers", "clip", "clipa", "kkk",
    "hahaha", "wtf", "monkas", "pepelaugh", "icant", "😂", "🤣", "💀",
)


def login_do_link(texto: str) -> str | None:
    """'https://www.twitch.tv/Fulano/videos' | 'twitch.tv/fulano' | 'fulano' -> 'fulano'."""
    texto = (texto or "").strip()
    if not texto:
        return None
    if "twitch.tv" in texto.lower():
        if not texto.startswith(("http://", "https://")):
            texto = "https://" + texto
        u = urlparse(texto)
        host = (u.hostname or "").lower().removeprefix("www.").removeprefix("m.")
        if host != "twitch.tv":
            return None
        partes = [p for p in u.path.split("/") if p]
        if not partes:
            return None
        candidato = partes[0].lower()
    else:
        candidato = texto.lstrip("@").lower()
    if candidato in _RESERVADOS or not _LOGIN.match(candidato):
        return None
    return candidato


def peso_mensagem(texto: str) -> float:
    """1 per message, 3 when it carries a laugh/hype trigger (same weighting as the MVP1 chat signal)."""
    t = texto.lower()
    return 3.0 if any(g in t for g in GATILHOS) else 1.0


def parse_irc(linha: str) -> tuple[str, str] | None:
    """':user!user@user.tmi.twitch.tv PRIVMSG #canal :texto' -> ('canal', 'texto'). Else None."""
    if " PRIVMSG #" not in linha:
        return None
    if linha.startswith("@"):  # IRCv3 tags
        _, _, linha = linha.partition(" ")
    try:
        _, resto = linha.split(" PRIVMSG #", 1)
        canal, texto = resto.split(" :", 1)
    except ValueError:
        return None
    return canal.strip().lower(), texto.rstrip("\r\n")


# ---------- status ----------

@dataclass
class Status:
    ao_vivo: bool
    titulo: str = ""
    nome: str = ""


def status(login: str) -> Status:
    """Is the channel live right now? (streamlink, no Twitch app needed)."""
    from streamlink import Streamlink

    s = Streamlink()
    _, classe, url = s.resolve_url(f"https://www.twitch.tv/{login}")
    plugin = classe(s, url)
    streams = plugin.streams()
    if not streams:
        return Status(False)
    return Status(True, plugin.get_title() or "", plugin.get_author() or login)


# ---------- recording ----------

def _streamlink_bin() -> str:
    candidato = Path(sys.executable).parent / "streamlink"
    return str(candidato) if candidato.exists() else "streamlink"


def iniciar_gravacao(login: str, pasta: Path) -> tuple[subprocess.Popen, subprocess.Popen]:
    """streamlink -> ffmpeg: 10 s .ts segments named by their local start time (YYYYmmddHHMMSS)."""
    pasta.mkdir(parents=True, exist_ok=True)
    sl = subprocess.Popen(
        [_streamlink_bin(), "--twitch-disable-ads", "--stdout", "--loglevel", "error",
         f"https://www.twitch.tv/{login}", settings.qualidade_live],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    ff = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-map", "0:v:0?", "-map", "0:a:0?",
         "-c", "copy", "-f", "segment", "-segment_time", "10", "-reset_timestamps", "1",
         "-strftime", "1", str(pasta / "seg_%Y%m%d%H%M%S.ts")],
        stdin=sl.stdout, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert sl.stdout
    sl.stdout.close()  # ffmpeg owns the pipe now
    return sl, ff


# ---------- chat ----------

class Chat:
    """Anonymous, read-only Twitch IRC connection. `ler()` returns messages that arrived."""

    def __init__(self, login: str):
        self.login = login
        self.sock: socket.socket | None = None
        self._buf = b""

    def conectar(self) -> None:
        self.fechar()
        s = socket.create_connection(("irc.chat.twitch.tv", 6667), timeout=10)
        s.sendall(f"NICK justinfan{random.randint(10000, 99999)}\r\n".encode())
        s.sendall(f"JOIN #{self.login}\r\n".encode())
        s.settimeout(0.2)
        self.sock = s
        self._buf = b""

    def ler(self) -> list[str]:
        if not self.sock:
            raise ConnectionError("chat desconectado")
        try:
            dados = self.sock.recv(65536)
        except socket.timeout:
            return []
        if not dados:
            raise ConnectionError("chat fechou a conexão")
        self._buf += dados
        *linhas, self._buf = self._buf.split(b"\r\n")
        msgs = []
        for bruta in linhas:
            linha = bruta.decode("utf-8", "replace")
            if linha.startswith("PING"):
                self.sock.sendall(linha.replace("PING", "PONG", 1).encode() + b"\r\n")
                continue
            p = parse_irc(linha)
            if p:
                msgs.append(p[1])
        return msgs

    def fechar(self) -> None:
        if self.sock:
            try:
                self.sock.close()
            except OSError:
                pass
        self.sock = None


# ---------- VOD ----------

def ultimo_vod(login: str) -> str | None:
    """URL of the most recent past broadcast, or None (VODs disabled / not published yet)."""
    import yt_dlp

    opts = {"quiet": True, "no_warnings": True, "extract_flat": True, "playlistend": 1}
    url = f"https://www.twitch.tv/{login}/videos?filter=archives&sort=time"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
    for e in info.get("entries") or []:
        if e.get("url"):
            return e["url"] if e["url"].startswith("http") else f"https://www.twitch.tv/videos/{e.get('id')}"
    return None
