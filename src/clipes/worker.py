"""Processa a fila: resolver → sinais → candidatos → baixar → transcrever → LLM → render."""

import logging
import shutil
import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from clipes import db, fontes, llm, render, sinais, transcricao
from clipes.config import settings

log = logging.getLogger("clipes.worker")

CURTO_S = 90  # até isso, o vídeo inteiro vira 1 clipe
PESOS = {"chat": 1.0, "audio": 0.6, "heatmap": 1.2, "comentarios": 0.8}


def _etapa(job_id: int, texto: str, status: str | None = None) -> None:
    log.info("job %s: %s", job_id, texto)
    campos = {"etapa": texto}
    if status:
        campos["status"] = status
    db.atualizar_job(job_id, **campos)


def _sinais(info: fontes.Info) -> dict[str, np.ndarray]:
    """Calcula em paralelo os sinais que fazem sentido para o tipo de entrada."""
    tarefas = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        if info.foi_live and info.url:
            tarefas["chat"] = ex.submit(sinais.chat, info.url, info.duracao)
        if info.heatmap:
            tarefas["heatmap"] = ex.submit(sinais.heatmap, info.heatmap, info.duracao)
        if info.comentarios:
            tarefas["comentarios"] = ex.submit(sinais.comentarios, info.comentarios, info.duracao)
        tarefas["audio"] = ex.submit(lambda: sinais.audio(fontes.url_audio(info), info.duracao))
        out = {}
        for nome, fut in tarefas.items():
            try:
                out[nome] = fut.result()
            except Exception as e:
                log.warning("sinal %s falhou: %s", nome, e)
        return out


def _webcam(canal: str, frame: Path) -> dict | None:
    salvo = db.webcam_do_canal(canal)
    if salvo is not db.SEM_INFO:
        return salvo
    try:
        cam = llm.achar_webcam(frame)
    except Exception as e:
        log.warning("detecção de webcam falhou: %s", e)
        return None
    db.salvar_webcam(canal, cam)
    return cam


def _processar_candidato(info: fontes.Info, job_id: int, clipe_id: int, pasta_trab: Path, pasta_out: Path) -> None:
    c = db.clipe(clipe_id)
    assert c
    inicio, fim = c["inicio"], c["fim"]
    trecho = pasta_trab / f"trecho_{clipe_id}.mp4"

    if info.duracao <= CURTO_S:
        fontes.baixar_inteiro(info, trecho)
    else:
        fontes.baixar_trecho(info, inicio, fim, trecho)
    dur_trecho = fontes.duracao_arquivo(trecho)

    palavras, _ = transcricao.transcrever(trecho)

    # 1) LLM simples: triagem (pula em vídeo curto — já é o momento)
    nota = 7
    if info.duracao > CURTO_S:
        t = llm.triar(info.titulo, info.canal, transcricao.texto_puro(palavras), c["nota_sinal"] or 0)
        nota = t.nota
        db.atualizar_clipe(clipe_id, nota_llm=t.nota, categoria=t.categoria)
        if t.nota < settings.nota_minima:
            db.atualizar_clipe(clipe_id, status="descartado", spoiler=int(t.suspeita_spoiler))
            return

    # 2) LLM complexo: corte, textos, spoiler
    frames = [
        render.extrair_frame(trecho, dur_trecho * f, pasta_trab / f"f{clipe_id}_{i}.jpg")
        for i, f in enumerate((0.15, 0.5, 0.85))
    ]
    final = llm.finalizar(info.titulo, info.canal, dur_trecho, transcricao.texto_com_tempo(palavras), frames)
    ini_rel = min(max(0.0, final.inicio), max(0.0, dur_trecho - settings.clipe_min_s))
    fim_rel = min(dur_trecho, max(final.fim, ini_rel + settings.clipe_min_s))
    fim_rel = min(fim_rel, ini_rel + settings.clipe_max_s)
    if info.duracao <= CURTO_S:
        ini_rel, fim_rel = 0.0, dur_trecho

    db.atualizar_clipe(
        clipe_id, status="renderizando",
        inicio=inicio + ini_rel, fim=inicio + fim_rel,
        nota_llm=nota,
        titulo=final.titulo, gancho=final.gancho, descricao=final.descricao,
        hashtags=final.hashtags, spoiler=int(final.spoiler), spoiler_motivo=final.spoiler_motivo,
    )

    # 3) render
    cam = _webcam(info.canal, frames[1])
    credito = f"{settings.marca} · {info.canal}" if settings.marca else info.canal
    saida = pasta_out / f"clipe_{clipe_id}.mp4"
    render.renderizar(trecho, ini_rel, fim_rel, palavras, final.gancho, credito, cam, saida)
    db.atualizar_clipe(clipe_id, status="revisao", arquivo=str(saida))


def processar(job_id: int) -> None:
    j = db.job(job_id)
    assert j
    pasta_trab = settings.trabalho_dir / str(job_id)
    pasta_out = settings.clipes_dir / str(job_id)
    pasta_trab.mkdir(parents=True, exist_ok=True)
    pasta_out.mkdir(parents=True, exist_ok=True)

    _etapa(job_id, "lendo metadados", "resolvendo")
    info = fontes.resolver(j["origem"], j["tipo"])
    db.atualizar_job(job_id, tipo=info.tipo, titulo=info.titulo, canal=info.canal, duracao=info.duracao)

    # já processado antes (app reiniciado): reaproveita candidatos pendentes
    pendentes = db.clipes_do_job(job_id, ("candidato", "renderizando"))
    if not pendentes and not db.clipes_do_job(job_id):
        if info.duracao <= CURTO_S:
            janelas = [(0.0, info.duracao, 1.0)]
        else:
            _etapa(job_id, "procurando momentos (chat, áudio, replays)", "sinais")
            series = _sinais(info)
            score = sinais.combinar(series, PESOS)
            qtd = j["max_clipes"] * 2
            janelas = sinais.escolher_janelas(
                score, qtd, settings.janela_s, settings.distancia_min_s, info.duracao
            ) or sinais.janelas_sem_sinal(info.duracao, qtd, settings.janela_s)
            log.info("job %s: sinais=%s, %d candidatos", job_id, list(series), len(janelas))
        for ini, fim, nota in janelas:
            db.criar_clipe(job_id, ini, fim, nota)
        pendentes = db.clipes_do_job(job_id, ("candidato",))

    # mais forte primeiro; para quando atingir max_clipes prontos
    pendentes = sorted(pendentes, key=lambda c: -(c["nota_sinal"] or 0))
    for n, c in enumerate(pendentes, 1):
        prontos = len(db.clipes_do_job(job_id, ("revisao", "aprovado", "rejeitado")))
        if prontos >= j["max_clipes"]:
            db.atualizar_clipe(c["id"], status="descartado")
            continue
        _etapa(job_id, f"candidato {n}/{len(pendentes)} · {prontos} clipes prontos", "processando")
        try:
            _processar_candidato(info, job_id, c["id"], pasta_trab, pasta_out)
        except Exception as e:
            log.error("clipe %s falhou: %s", c["id"], traceback.format_exc())
            db.atualizar_clipe(c["id"], status="erro", erro=str(e)[:500])

    shutil.rmtree(pasta_trab, ignore_errors=True)
    prontos = len(db.clipes_do_job(job_id, ("revisao", "aprovado", "rejeitado")))
    _etapa(job_id, f"{prontos} clipes prontos", "pronto")


def loop(parar: threading.Event) -> None:
    while not parar.is_set():
        j = db.pegar_proximo_job()
        if not j:
            parar.wait(2)
            continue
        try:
            processar(j["id"])
        except Exception as e:
            log.error("job %s falhou: %s", j["id"], traceback.format_exc())
            db.atualizar_job(j["id"], status="erro", erro=str(e)[:1000])
        time.sleep(0.1)
