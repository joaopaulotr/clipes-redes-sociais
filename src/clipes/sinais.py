"""Onde está o momento quente: cada sinal vira uma série 'intensidade por segundo' (0-1)."""

import logging
import subprocess

import numpy as np

from clipes.fontes import minutagens

log = logging.getLogger(__name__)

GATILHOS = (
    "kekw", "lul", "omegalul", "lmao", "lol", "pog", "poggers", "clip", "clipa", "kkk",
    "hahaha", "kkkkk", "wtf", "monkas", "pepelaugh", "icant", "😂", "🤣", "💀",
)
ATRASO_CHAT_S = 8  # o chat reage alguns segundos depois do momento


def _media_movel(x: np.ndarray, janela: int) -> np.ndarray:
    if len(x) == 0:
        return x
    janela = max(1, min(janela, len(x)))
    k = np.ones(janela) / janela
    return np.convolve(x, k, mode="same")


def picos_relativos(x: np.ndarray, janela: int = 300) -> np.ndarray:
    """Quanto cada segundo está acima do 'normal' local (auto-calibra por canal). Saída 0-1."""
    if len(x) == 0 or not np.any(x):
        return np.zeros_like(x, dtype=float)
    base = _media_movel(x, janela)
    desvio = np.sqrt(np.maximum(_media_movel((x - base) ** 2, janela), 1e-9))
    z = np.clip((x - base) / desvio, 0, None)
    z = _media_movel(z, 5)  # suaviza picos de 1 segundo
    topo = np.percentile(z, 99.5) or z.max() or 1.0
    return np.clip(z / topo, 0, 1)


def _normalizar(x: np.ndarray) -> np.ndarray:
    m = x.max() if len(x) else 0
    return x / m if m > 0 else x.astype(float)


# ---------- sinais ----------

def audio(fonte: str, duracao: float) -> np.ndarray:
    """Volume RMS por segundo, lendo o áudio em streaming via ffmpeg (8 kHz mono)."""
    n = int(duracao) + 1
    rms = np.zeros(n)
    taxa = 8000
    proc = subprocess.Popen(
        ["ffmpeg", "-loglevel", "error", "-i", fonte, "-vn", "-ac", "1", "-ar", str(taxa),
         "-f", "s16le", "-"],
        stdout=subprocess.PIPE,
    )
    assert proc.stdout
    seg = 0
    while seg < n:
        bloco = proc.stdout.read(taxa * 2)
        if not bloco:
            break
        a = np.frombuffer(bloco, dtype=np.int16).astype(np.float32)
        rms[seg] = float(np.sqrt(np.mean(a * a))) if len(a) else 0.0
        seg += 1
    proc.stdout.close()
    proc.wait()
    return picos_relativos(rms)


def chat(url: str, duracao: float) -> np.ndarray:
    """Replay do chat (Twitch VOD / YouTube live): mensagens por segundo + peso de gatilhos."""
    from chat_downloader import ChatDownloader

    n = int(duracao) + 1
    contagem = np.zeros(n)
    try:
        for msg in ChatDownloader().get_chat(url, message_groups=["messages"]):
            t = msg.get("time_in_seconds")
            if t is None or t < 0:
                continue
            i = int(t) - ATRASO_CHAT_S
            if not 0 <= i < n:
                continue
            texto = (msg.get("message") or "").lower()
            peso = 1.0 + (2.0 if any(g in texto for g in GATILHOS) else 0.0)
            contagem[i] += peso
    except Exception as e:  # API não oficial: se falhar, segue sem chat
        log.warning("chat indisponível (%s): %s", url, e)
        return np.zeros(n)
    return picos_relativos(contagem)


def heatmap(pontos: list[dict], duracao: float) -> np.ndarray:
    """'Mais repetidos' do YouTube."""
    n = int(duracao) + 1
    s = np.zeros(n)
    for p in pontos:
        a, b = int(p.get("start_time", 0)), int(p.get("end_time", 0)) + 1
        s[max(a, 0):min(b, n)] = p.get("value", 0)
    # tira o início (sempre alto: todo mundo vê o começo)
    s[: min(30, n)] *= 0.3
    return _normalizar(s)


def comentarios(textos: list[str], duracao: float) -> np.ndarray:
    """Minutagens citadas nos comentários ('2:14 kkkk')."""
    n = int(duracao) + 1
    s = np.zeros(n)
    for t in textos:
        for seg in minutagens(t):
            if 0 <= seg < n:
                s[max(seg - 5, 0):min(seg + 10, n)] += 1
    return _normalizar(s)


# ---------- candidatos ----------

def combinar(series: dict[str, np.ndarray], pesos: dict[str, float]) -> np.ndarray:
    validas = {k: v for k, v in series.items() if len(v) and np.any(v)}
    if not validas:
        return np.zeros(max((len(v) for v in series.values()), default=0))
    n = max(len(v) for v in validas.values())
    total = np.zeros(n)
    soma_pesos = 0.0
    for k, v in validas.items():
        w = pesos.get(k, 1.0)
        total[: len(v)] += w * v
        soma_pesos += w
    return total / soma_pesos


def escolher_janelas(
    score: np.ndarray, quantidade: int, janela_s: int, distancia_min_s: int, duracao: float
) -> list[tuple[float, float, float]]:
    """Picos mais fortes, separados por pelo menos `distancia_min_s`.
    Retorna [(inicio, fim, nota)] com janela de `janela_s` (2/3 antes do pico, 1/3 depois)."""
    if len(score) == 0 or not np.any(score):
        return []
    s = score.copy()
    janelas = []
    antes, depois = janela_s * 2 // 3, janela_s // 3
    while len(janelas) < quantidade:
        pico = int(np.argmax(s))
        nota = float(s[pico])
        if nota <= 0.05:
            break
        inicio = max(0.0, pico - antes)
        fim = min(float(duracao), pico + depois)
        if fim - inicio >= 10:
            janelas.append((inicio, fim, round(nota, 3)))
        s[max(0, pico - distancia_min_s):pico + distancia_min_s] = 0
    return sorted(janelas, key=lambda j: j[0])


def janelas_sem_sinal(duracao: float, quantidade: int, janela_s: int) -> list[tuple[float, float, float]]:
    """Último recurso: fatias espaçadas (o LLM decide o que presta)."""
    if duracao <= 0:
        return []
    passo = max(janela_s, duracao / max(quantidade, 1))
    out, t = [], 0.0
    while t + 10 < duracao and len(out) < quantidade:
        out.append((t, min(duracao, t + janela_s), 0.0))
        t += passo
    return out
