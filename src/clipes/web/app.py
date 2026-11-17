"""Site local: enviar vídeos e revisar clipes."""

import json
import logging
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from clipes import avisos, db, monitor, twitch, worker
from clipes.config import settings
from clipes.fontes import classificar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
_parar = threading.Event()

STATUS_JOB = {
    "na_fila": ("Na fila", "chip"),
    "resolvendo": ("Lendo vídeo", "chip chip-roxo chip-vivo"),
    "sinais": ("Procurando momentos", "chip chip-roxo chip-vivo"),
    "processando": ("Gerando clipes", "chip chip-roxo chip-vivo"),
    "pronto": ("Pronto", "chip chip-branco"),
    "erro": ("Erro", "chip chip-alerta"),
}
templates.env.globals["STATUS_JOB"] = STATUS_JOB

STATUS_VIGIADO = {
    "offline": ("Offline", "chip"),
    "gravando": ("Ao vivo · gravando", "chip chip-roxo chip-vivo"),
    "espera": ("Ao vivo · na espera", "chip chip-branco"),
    "erro": ("Erro", "chip chip-alerta"),
}
templates.env.globals["STATUS_VIGIADO"] = STATUS_VIGIADO


def _hora(iso: str | None) -> str:
    """UTC ISO -> local 'dd/mm HH:MM'."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso).astimezone().strftime("%d/%m %H:%M")
    except ValueError:
        return iso


templates.env.filters["hora"] = _hora
templates.env.filters["json"] = lambda s: json.loads(s) if s else []


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.iniciar()
    threads = [
        threading.Thread(target=worker.loop, args=(_parar, False), daemon=True, name="worker"),
        threading.Thread(target=worker.loop, args=(_parar, True), daemon=True, name="worker-ao-vivo"),
        threading.Thread(target=monitor.loop, args=(_parar,), daemon=True, name="monitor"),
        threading.Thread(target=avisos.loop, args=(_parar,), daemon=True, name="avisos"),
    ]
    for t in threads:
        t.start()
    yield
    _parar.set()


app = FastAPI(title="Clipes", lifespan=lifespan)


def _clipe_ou_404(clipe_id: int):
    c = db.clipe(clipe_id)
    if not c:
        raise HTTPException(404)
    return c


# ---------- páginas ----------

@app.get("/", response_class=HTMLResponse)
def inicio(request: Request):
    return templates.TemplateResponse(request, "inicio.html", {
        "jobs": db.listar_jobs(), "max_padrao": settings.max_clipes_padrao,
        "sem_chave": not settings.openai_api_key,
    })


@app.get("/parcial/jobs", response_class=HTMLResponse)
def parcial_jobs(request: Request):
    return templates.TemplateResponse(request, "_jobs.html", {"jobs": db.listar_jobs()})


@app.post("/enviar")
async def enviar(
    links: str = Form(""),
    max_clipes: int = Form(20),
    arquivo: UploadFile | None = File(None),
):
    max_clipes = max(1, min(max_clipes, 100))
    for linha in links.splitlines():
        url = linha.strip()
        if url.startswith(("http://", "https://")):
            db.criar_job(url, max_clipes, classificar(url))
    if arquivo and arquivo.filename:
        sufixo = Path(arquivo.filename).suffix.lower() or ".mp4"
        if sufixo not in (".mp4", ".mov", ".mkv", ".webm"):
            raise HTTPException(400, "formato não suportado")
        destino = settings.uploads_dir / f"{uuid.uuid4().hex}{sufixo}"
        with destino.open("wb") as f:
            shutil.copyfileobj(arquivo.file, f, length=4 * 1024 * 1024)
        db.criar_job(str(destino), max_clipes, "upload")
    return RedirectResponse("/", status_code=303)


@app.get("/job/{job_id}", response_class=HTMLResponse)
def ver_job(request: Request, job_id: int, filtro: str = "revisao"):
    j = db.job(job_id)
    if not j:
        raise HTTPException(404)
    filtros = {
        "revisao": ("revisao",), "aprovado": ("aprovado",), "rejeitado": ("rejeitado",),
        "descartado": ("descartado", "erro"), "todos": None,
    }
    clipes = db.clipes_do_job(job_id, filtros.get(filtro, ("revisao",)))
    return templates.TemplateResponse(request, "job.html", {
        "j": j, "clipes": clipes, "filtro": filtro, "contagem": _contagem(job_id),
    })


@app.get("/parcial/job/{job_id}/status", response_class=HTMLResponse)
def parcial_status(request: Request, job_id: int):
    j = db.job(job_id)
    if not j:
        raise HTTPException(404)
    return templates.TemplateResponse(request, "_status.html", {"j": j, "contagem": _contagem(job_id)})


def _contagem(job_id: int) -> dict[str, int]:
    out: dict[str, int] = {}
    for c in db.clipes_do_job(job_id):
        out[c["status"]] = out.get(c["status"], 0) + 1
    return out


# ---------- ações de job ----------

@app.post("/job/{job_id}/reprocessar")
def reprocessar(job_id: int):
    db.atualizar_job(job_id, status="na_fila", erro=None, etapa=None)
    return RedirectResponse(f"/job/{job_id}", status_code=303)


@app.post("/job/{job_id}/apagar")
def apagar(job_id: int):
    j = db.job(job_id)
    if j and j["status"] not in ("pronto", "erro", "na_fila"):
        raise HTTPException(409, "job em andamento")
    shutil.rmtree(settings.clipes_dir / str(job_id), ignore_errors=True)
    if j and j["tipo"] in ("upload", "ao_vivo"):
        Path(j["origem"]).unlink(missing_ok=True)
    db.apagar_job(job_id)
    return RedirectResponse("/", status_code=303)


# ---------- ações de clipe ----------

@app.post("/clipe/{clipe_id}/{acao}", response_class=HTMLResponse)
def acao_clipe(request: Request, clipe_id: int, acao: str, titulo: str = Form(None)):
    _clipe_ou_404(clipe_id)
    if acao == "aprovar":
        db.atualizar_clipe(clipe_id, status="aprovado")
    elif acao == "rejeitar":
        db.atualizar_clipe(clipe_id, status="rejeitado")
    elif acao == "revisar":
        db.atualizar_clipe(clipe_id, status="revisao")
    elif acao == "titulo" and titulo is not None:
        db.atualizar_clipe(clipe_id, titulo=titulo.strip()[:150])
    else:
        raise HTTPException(400)
    return templates.TemplateResponse(request, "_clipe.html", {"c": db.clipe(clipe_id)})


@app.get("/clipe/{clipe_id}/video")
def video(clipe_id: int, baixar: bool = False):
    c = _clipe_ou_404(clipe_id)
    if not c["arquivo"] or not Path(c["arquivo"]).exists():
        raise HTTPException(404)
    nome = f"clipe_{clipe_id}.mp4"
    return FileResponse(c["arquivo"], media_type="video/mp4", filename=nome if baixar else None)


# ---------- canais ----------

@app.get("/canais", response_class=HTMLResponse)
def canais(request: Request):
    return templates.TemplateResponse(request, "canais.html", {"canais": db.listar_canais()})


@app.post("/canais/esquecer")
def esquecer(nome: str = Form(...)):
    db.esquecer_canal(nome)
    return RedirectResponse("/canais", status_code=303)


# ---------- monitor de lives (spec 002) ----------

@app.get("/monitor", response_class=HTMLResponse)
def ver_monitor(request: Request, msg: str = "", erro: str = ""):
    return templates.TemplateResponse(request, "monitor.html", {
        "vigiados": db.listar_vigiados(), "momentos": db.momentos_recentes(15),
        "telegram_ok": avisos.configurado(), "silenciado": avisos.silenciado(),
        "url_base": settings.url_base, "limite_padrao": settings.limite_hora_padrao,
        "max_lives": settings.max_lives, "msg": msg, "erro": erro,
    })


@app.get("/parcial/vigiados", response_class=HTMLResponse)
def parcial_vigiados(request: Request):
    return templates.TemplateResponse(request, "_vigiados.html", {
        "vigiados": db.listar_vigiados(), "momentos": db.momentos_recentes(15),
    })


def _volta(msg: str = "", erro: str = "") -> RedirectResponse:
    from urllib.parse import urlencode

    q = urlencode({k: v for k, v in (("msg", msg), ("erro", erro)) if v})
    return RedirectResponse("/monitor" + (f"?{q}" if q else ""), status_code=303)


@app.post("/monitor/canal")
def salvar_canal(
    link: str = Form(...), autorizacao: str = Form(""), prioridade: int = Form(0),
    limite_hora: int = Form(4), ativar: str = Form(""),
):
    login = twitch.login_do_link(link)
    if not login:
        return _volta(erro="Link ou nome de canal da Twitch inválido.")
    autorizacao = autorizacao.strip()[:500]
    db.salvar_vigiado(login, None, autorizacao or None, max(0, min(prioridade, 10)),
                      max(1, min(limite_hora, 30)))
    if ativar:
        if not autorizacao:
            return _volta(erro=f"{login} salvo, mas não ativado: informe a campanha ou autorização.")
        db.atualizar_vigiado(login, ativo=1)
    return _volta(msg=f"{login} salvo" + (" e ativado." if ativar else "."))


@app.post("/monitor/canal/{login}/{acao}")
def acao_canal(login: str, acao: str):
    v = db.vigiado(login)
    if not v:
        raise HTTPException(404)
    if acao == "ativar":
        if not v["autorizacao"]:  # RF-002
            return _volta(erro=f"Informe a campanha ou autorização de {login} antes de ativar.")
        db.atualizar_vigiado(login, ativo=1)
    elif acao == "desativar":
        db.atualizar_vigiado(login, ativo=0)
    elif acao == "apagar":
        if v["ativo"]:
            return _volta(erro="Desative o canal antes de apagar.")
        db.apagar_vigiado(login)
    else:
        raise HTTPException(400)
    return _volta()


@app.post("/monitor/avisos/{acao}")
def acao_avisos(acao: str):
    if acao == "silenciar":
        avisos.silenciar(True)
    elif acao == "reativar":
        avisos.silenciar(False)
    elif acao == "teste":
        if not avisos.configurado():
            return _volta(erro="Configure TELEGRAM_TOKEN e TELEGRAM_CHAT_ID no .env e reinicie.")
        try:
            avisos.enviar_teste()
        except Exception as e:
            return _volta(erro=f"Telegram recusou: {str(e)[:200]}")
        return _volta(msg="Mensagem de teste enviada. Confira o Telegram.")
    else:
        raise HTTPException(400)
    return _volta()
