"""Julgamento por LLM (OpenAI Responses API).

- simples  (LLM_SIMPLES, padrão gpt-6-luna):  triagem de TODOS os candidatos.
- complexo (LLM_COMPLEXO, padrão gpt-6.1-terra): corte exato, título, gancho, spoiler, webcam.
"""

import base64
from functools import lru_cache
from pathlib import Path
from typing import Literal

from openai import OpenAI
from pydantic import BaseModel, Field

from clipes.config import settings

Categoria = Literal["reacao", "engracado", "fail", "acao", "habilidade", "bug", "conversa", "outro"]


class Triagem(BaseModel):
    nota: int = Field(description="0 a 10: quão bom seria como clipe curto viral")
    categoria: Categoria
    suspeita_spoiler: bool = Field(description="true se pode mostrar/contar algo da história do jogo")
    motivo: str = Field(description="uma frase curta")


class Final(BaseModel):
    inicio: float = Field(description="segundos, relativo ao início do trecho")
    fim: float = Field(description="segundos, relativo ao início do trecho")
    titulo: str = Field(description="título curto e chamativo, até 70 caracteres")
    gancho: str = Field(description="texto na tela nos 2 primeiros segundos, até 6 palavras")
    descricao: str = Field(description="1-2 frases para a legenda do post, com crédito ao criador")
    hashtags: list[str] = Field(description="3 a 6 hashtags, com #")
    spoiler: bool
    spoiler_motivo: str = Field(description="vazio se não for spoiler")


class CaixaWebcam(BaseModel):
    tem_webcam: bool
    x: float = Field(description="borda esquerda, fração 0-1 da largura")
    y: float = Field(description="borda de cima, fração 0-1 da altura")
    w: float = Field(description="largura, fração 0-1")
    h: float = Field(description="altura, fração 0-1")


@lru_cache(maxsize=1)
def _cliente() -> OpenAI:
    if not settings.openai_api_key:
        raise RuntimeError("OPENAI_API_KEY não configurada no .env")
    return OpenAI(api_key=settings.openai_api_key)


def _imagem(caminho: Path) -> dict:
    b64 = base64.b64encode(caminho.read_bytes()).decode()
    return {"type": "input_image", "image_url": f"data:image/jpeg;base64,{b64}", "detail": "low"}


def _spoilers() -> str:
    try:
        linhas = settings.spoilers_path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return ""
    itens = [l.strip() for l in linhas if l.strip() and not l.startswith("#")]
    return "\n".join(f"- {i}" for i in itens)


INSTRUCOES_TRIAGEM = """Você faz a triagem de trechos de lives e vídeos de games (principalmente GTA) \
para uma conta de clipes curtos no TikTok, YouTube Shorts e Instagram Reels.

Dê nota de 0 a 10 para o quanto o trecho funciona sozinho como clipe curto:
- 8-10: reação forte, momento engraçado, fail épico, jogada absurda, frase marcante, caos.
- 5-7: interessante mas precisa de contexto, ou o pico é fraco.
- 0-4: conversa parada, menu, loading, silêncio, leitura de chat, propaganda.

Os sinais (chat/áudio/replays) indicam que algo aconteceu; a transcrição mostra o quê.
Marque suspeita_spoiler se o trecho parecer cutscene, missão da história, final, ou revelação de enredo."""

INSTRUCOES_FINAL = """Você edita clipes curtos verticais (15 a 60 s) de lives e vídeos de games \
(principalmente GTA) para TikTok, YouTube Shorts e Instagram Reels, em português do Brasil.

Tarefas:
1. Escolha início e fim exatos dentro do trecho (segundos relativos ao trecho). O clipe deve \
começar perto da ação (sem enrolação) e terminar logo depois do clímax/reação, sem cortar frase \
no meio. Duração entre {min_s} e {max_s} segundos.
2. Título curto e chamativo (não clickbait mentiroso), em PT-BR.
3. Gancho: texto que aparece nos 2 primeiros segundos para prender quem está rolando o feed.
4. Descrição curta com crédito ao criador ({canal}) e 3 a 6 hashtags.
5. Spoiler: marque true se o trecho mostra ou conta missão da história, cutscene, final, morte \
de personagem, ou qualquer item da lista abaixo. Na dúvida, true.

Itens de spoiler conhecidos (pode estar vazio):
{spoilers}"""


def triar(titulo_fonte: str, canal: str, transcricao: str, nota_sinal: float) -> Triagem:
    entrada = (
        f"Fonte: {titulo_fonte}\nCriador: {canal}\n"
        f"Força dos sinais (0-1): {nota_sinal:.2f}\n\nTranscrição do trecho:\n{transcricao or '(sem fala)'}"
    )
    r = _cliente().responses.parse(
        model=settings.llm_simples,
        instructions=INSTRUCOES_TRIAGEM,
        input=entrada,
        text_format=Triagem,
    )
    if r.output_parsed is None:
        raise RuntimeError("LLM simples não devolveu resposta válida")
    return r.output_parsed


def finalizar(
    titulo_fonte: str, canal: str, duracao_trecho: float, transcricao_tempo: str, frames: list[Path]
) -> Final:
    instrucoes = INSTRUCOES_FINAL.format(
        min_s=settings.clipe_min_s, max_s=settings.clipe_max_s, canal=canal,
        spoilers=_spoilers() or "(nenhum)",
    )
    texto = (
        f"Fonte: {titulo_fonte}\nCriador: {canal}\nDuração do trecho: {duracao_trecho:.1f} s\n\n"
        f"Transcrição com tempos [segundos]:\n{transcricao_tempo or '(sem fala)'}\n\n"
        f"Frames do trecho em ordem (início, meio, fim) seguem abaixo."
    )
    conteudo = [{"type": "input_text", "text": texto}] + [_imagem(f) for f in frames]
    r = _cliente().responses.parse(
        model=settings.llm_complexo,
        instructions=instrucoes,
        input=[{"role": "user", "content": conteudo}],
        text_format=Final,
    )
    if r.output_parsed is None:
        raise RuntimeError("LLM complexo não devolveu resposta válida")
    return r.output_parsed


def achar_webcam(frame: Path) -> dict | None:
    """Caixa da webcam do streamer em frações 0-1, ou None se não houver."""
    conteudo = [
        {"type": "input_text", "text": (
            "Este é um frame de uma live/vídeo de game. Existe uma webcam do streamer (rosto da "
            "pessoa sobreposto ao jogo)? Se sim, dê a caixa que contém a webcam inteira, em frações "
            "0-1 da imagem. Se não houver webcam, tem_webcam=false e zeros."
        )},
        _imagem(frame),
    ]
    r = _cliente().responses.parse(
        model=settings.llm_complexo,
        input=[{"role": "user", "content": conteudo}],
        text_format=CaixaWebcam,
    )
    c = r.output_parsed
    if c is None or not c.tem_webcam or c.w < 0.05 or c.h < 0.05:
        return None
    x, y = max(0.0, c.x), max(0.0, c.y)
    return {"x": x, "y": y, "w": min(c.w, 1 - x), "h": min(c.h, 1 - y)}
