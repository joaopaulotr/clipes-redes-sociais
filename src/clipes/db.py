"""SQLite: jobs (envios), clipes e canais. Uma conexão por chamada (thread-safe)."""

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator

from clipes.config import settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    origem TEXT NOT NULL,            -- url ou caminho do upload
    tipo TEXT,                       -- youtube, twitch_vod, twitch_clip, kick, mp4_url, upload, generic
    titulo TEXT,
    canal TEXT,
    duracao REAL,
    max_clipes INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'na_fila',
    etapa TEXT,
    erro TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS clipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id INTEGER NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    inicio REAL NOT NULL,
    fim REAL NOT NULL,
    nota_sinal REAL,
    nota_llm INTEGER,
    categoria TEXT,
    titulo TEXT,
    gancho TEXT,
    descricao TEXT,
    hashtags TEXT,
    spoiler INTEGER DEFAULT 0,
    spoiler_motivo TEXT,
    status TEXT NOT NULL DEFAULT 'candidato',
    arquivo TEXT,
    erro TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS canais (
    nome TEXT PRIMARY KEY,
    webcam TEXT,                     -- JSON {x,y,w,h} em frações 0-1, ou 'null' = sem webcam
    atualizado_em TEXT NOT NULL
);
"""


def agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def conectar() -> Iterator[sqlite3.Connection]:
    con = sqlite3.connect(settings.db_path, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.execute("PRAGMA journal_mode = WAL")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def iniciar() -> None:
    settings.garantir_pastas()
    with conectar() as con:
        con.executescript(SCHEMA)
        # job interrompido (app fechado no meio) volta para a fila
        con.execute(
            "UPDATE jobs SET status='na_fila', etapa=NULL WHERE status NOT IN ('pronto','erro','na_fila')"
        )


# ---------- jobs ----------

def criar_job(origem: str, max_clipes: int, tipo: str | None = None) -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO jobs (origem, tipo, max_clipes, criado_em) VALUES (?,?,?,?)",
            (origem, tipo, max_clipes, agora()),
        )
        return int(cur.lastrowid)


def pegar_proximo_job() -> sqlite3.Row | None:
    with conectar() as con:
        row = con.execute(
            "SELECT * FROM jobs WHERE status='na_fila' ORDER BY id LIMIT 1"
        ).fetchone()
        if row:
            con.execute("UPDATE jobs SET status='resolvendo' WHERE id=?", (row["id"],))
        return row


def atualizar_job(job_id: int, **campos: Any) -> None:
    if not campos:
        return
    cols = ", ".join(f"{k}=?" for k in campos)
    with conectar() as con:
        con.execute(f"UPDATE jobs SET {cols} WHERE id=?", (*campos.values(), job_id))


def job(job_id: int) -> sqlite3.Row | None:
    with conectar() as con:
        return con.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()


def listar_jobs(limite: int = 50) -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute(
            """SELECT j.*,
                      (SELECT COUNT(*) FROM clipes c WHERE c.job_id=j.id AND c.status='revisao') AS em_revisao,
                      (SELECT COUNT(*) FROM clipes c WHERE c.job_id=j.id AND c.status='aprovado') AS aprovados
               FROM jobs j ORDER BY j.id DESC LIMIT ?""",
            (limite,),
        ).fetchall()


def apagar_job(job_id: int) -> None:
    with conectar() as con:
        con.execute("DELETE FROM jobs WHERE id=?", (job_id,))


# ---------- clipes ----------

def criar_clipe(job_id: int, inicio: float, fim: float, nota_sinal: float) -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO clipes (job_id, inicio, fim, nota_sinal, criado_em) VALUES (?,?,?,?,?)",
            (job_id, inicio, fim, nota_sinal, agora()),
        )
        return int(cur.lastrowid)


def atualizar_clipe(clipe_id: int, **campos: Any) -> None:
    if not campos:
        return
    if "hashtags" in campos and isinstance(campos["hashtags"], list):
        campos["hashtags"] = " ".join(campos["hashtags"])
    cols = ", ".join(f"{k}=?" for k in campos)
    with conectar() as con:
        con.execute(f"UPDATE clipes SET {cols} WHERE id=?", (*campos.values(), clipe_id))


def clipe(clipe_id: int) -> sqlite3.Row | None:
    with conectar() as con:
        return con.execute("SELECT * FROM clipes WHERE id=?", (clipe_id,)).fetchone()


def clipes_do_job(job_id: int, status: tuple[str, ...] | None = None) -> list[sqlite3.Row]:
    with conectar() as con:
        if status:
            marks = ",".join("?" * len(status))
            return con.execute(
                f"SELECT * FROM clipes WHERE job_id=? AND status IN ({marks}) ORDER BY nota_llm DESC, inicio",
                (job_id, *status),
            ).fetchall()
        return con.execute(
            "SELECT * FROM clipes WHERE job_id=? ORDER BY nota_llm DESC, inicio", (job_id,)
        ).fetchall()


# ---------- canais ----------

_SEM_INFO = object()


def webcam_do_canal(nome: str) -> Any:
    """Retorna dict {x,y,w,h}, None (canal sem webcam) ou _SEM_INFO (nunca analisado)."""
    with conectar() as con:
        row = con.execute("SELECT webcam FROM canais WHERE nome=?", (nome,)).fetchone()
    if row is None:
        return _SEM_INFO
    return json.loads(row["webcam"])


def salvar_webcam(nome: str, webcam: dict | None) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO canais (nome, webcam, atualizado_em) VALUES (?,?,?) "
            "ON CONFLICT(nome) DO UPDATE SET webcam=excluded.webcam, atualizado_em=excluded.atualizado_em",
            (nome, json.dumps(webcam), agora()),
        )


def esquecer_canal(nome: str) -> None:
    with conectar() as con:
        con.execute("DELETE FROM canais WHERE nome=?", (nome,))


def listar_canais() -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute("SELECT * FROM canais ORDER BY nome").fetchall()


SEM_INFO = _SEM_INFO
