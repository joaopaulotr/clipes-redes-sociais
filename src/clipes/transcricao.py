"""Transcrição local com faster-whisper (CPU, int8), com tempo por palavra."""

import subprocess
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from clipes.config import settings

_modelo = None
_trava = threading.Lock()


@dataclass
class Palavra:
    inicio: float
    fim: float
    texto: str


def _carregar():
    global _modelo
    with _trava:
        if _modelo is None:
            from faster_whisper import WhisperModel

            _modelo = WhisperModel(settings.whisper_modelo, device="cpu", compute_type="int8")
    return _modelo


def _audio_16k(arquivo: Path) -> np.ndarray:
    """Decodifica com ffmpeg (evita depender da versão do PyAV)."""
    bruto = subprocess.run(
        ["ffmpeg", "-loglevel", "error", "-i", str(arquivo), "-vn", "-ac", "1", "-ar", "16000",
         "-f", "s16le", "-"],
        capture_output=True, check=True,
    ).stdout
    return np.frombuffer(bruto, dtype=np.int16).astype(np.float32) / 32768.0


def transcrever(arquivo: Path) -> tuple[list[Palavra], str]:
    """Retorna (palavras com tempo relativo ao arquivo, idioma detectado)."""
    modelo = _carregar()
    audio = _audio_16k(arquivo)
    if len(audio) < 1600:
        return [], ""
    segmentos, info = modelo.transcribe(
        audio, word_timestamps=True, vad_filter=True, beam_size=1
    )
    palavras: list[Palavra] = []
    for seg in segmentos:
        for w in seg.words or []:
            texto = w.word.strip()
            if texto:
                palavras.append(Palavra(float(w.start), float(w.end), texto))
    return palavras, info.language


def texto_com_tempo(palavras: list[Palavra], bloco_s: float = 5.0) -> str:
    """'[0.0] fala fala [5.2] mais fala' — compacto para mandar ao LLM."""
    linhas, atual, marco = [], [], None
    for p in palavras:
        if marco is None or p.inicio - marco >= bloco_s:
            if atual:
                linhas.append(f"[{marco:.1f}] " + " ".join(atual))
            atual, marco = [], p.inicio
        atual.append(p.texto)
    if atual:
        linhas.append(f"[{marco:.1f}] " + " ".join(atual))
    return "\n".join(linhas)


def texto_puro(palavras: list[Palavra]) -> str:
    return " ".join(p.texto for p in palavras)
