"""Site local: enviar vídeos e revisar clipes."""

import logging
import shutil
import threading
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from clipes import db, worker
from clipes.config import settings
from clipes.fontes import classificar

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

templates = Jinja2Templates(directory=Path(__file__).parent / "templates")
_parar = threading.Event()

STATUS_JOB = {
    "na_fila": ("Na fila", "bg-zinc-700"),
    "resolvendo": ("Lendo vídeo", "bg-sky-700"),
    "sinais": ("Procurando momentos", "bg-sky-700"),
    "processando": ("Gerando clipes", "bg-amber-600"),
    "pronto": ("Pronto", "bg-emerald-700"),
    "erro": ("Erro", "bg-red-700"),
}
templates.env.globals["STATUS_JOB"] = STATUS_JOB


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.iniciar()
    t = threading.Thread(target=worker.loop, args=(_parar,), daemon=True, name="worker")
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
    if j and j["tipo"] == "upload":
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
