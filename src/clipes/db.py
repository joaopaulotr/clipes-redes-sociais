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

-- spec 002: monitor de lives
CREATE TABLE IF NOT EXISTS vigiados (
    login TEXT PRIMARY KEY,          -- login da Twitch (minúsculo)
    nome TEXT,
    autorizacao TEXT,                -- link da campanha ou nota da autorização
    ativo INTEGER NOT NULL DEFAULT 0,
    prioridade INTEGER NOT NULL DEFAULT 0,
    limite_hora INTEGER NOT NULL DEFAULT 4,
    status TEXT NOT NULL DEFAULT 'offline',   -- offline, ao_vivo, gravando, espera, erro
    ultimo_pico TEXT,
    erro TEXT,
    criado_em TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessoes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    login TEXT NOT NULL,
    inicio TEXT NOT NULL,
    fim TEXT,
    titulo TEXT,
    cegos TEXT NOT NULL DEFAULT '[]',         -- JSON [[inicio, fim, motivo], ...]
    vod_job_id INTEGER
);
CREATE TABLE IF NOT EXISTS momentos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sessao_id INTEGER REFERENCES sessoes(id) ON DELETE CASCADE,
    login TEXT NOT NULL,
    instante TEXT NOT NULL,                   -- UTC ISO do pico
    forca REAL,
    job_id INTEGER,
    motivo TEXT                               -- preenchido quando não virou clipe
);
CREATE TABLE IF NOT EXISTS avisos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    clipe_id INTEGER NOT NULL UNIQUE REFERENCES clipes(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pendente',  -- pendente, enviado, silenciado, erro
    criado_em TEXT NOT NULL,
    enviado_em TEXT
);
CREATE TABLE IF NOT EXISTS ajustes (
    chave TEXT PRIMARY KEY,
    valor TEXT
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

def criar_job(origem: str, max_clipes: int, tipo: str | None = None,
              canal: str | None = None, titulo: str | None = None) -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO jobs (origem, tipo, max_clipes, canal, titulo, criado_em) VALUES (?,?,?,?,?,?)",
            (origem, tipo, max_clipes, canal, titulo, agora()),
        )
        return int(cur.lastrowid)


def pegar_proximo_job(ao_vivo: bool | None = None) -> sqlite3.Row | None:
    """ao_vivo=True: só envios de live; False: todo o resto; None: qualquer um."""
    filtro = {True: " AND tipo='ao_vivo'", False: " AND tipo IS NOT 'ao_vivo'", None: ""}[ao_vivo]
    with conectar() as con:
        row = con.execute(
            f"SELECT * FROM jobs WHERE status='na_fila'{filtro} ORDER BY id LIMIT 1"
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
        # spec 002: clipe novo em revisão gera um aviso (uma vez por clipe)
        if campos.get("status") == "revisao":
            con.execute(
                "INSERT OR IGNORE INTO avisos (clipe_id, criado_em) VALUES (?,?)", (clipe_id, agora())
            )


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


# ---------- spec 002: vigiados ----------

def salvar_vigiado(login: str, nome: str | None, autorizacao: str | None,
                   prioridade: int, limite_hora: int) -> None:
    with conectar() as con:
        con.execute(
            """INSERT INTO vigiados (login, nome, autorizacao, prioridade, limite_hora, criado_em)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(login) DO UPDATE SET nome=excluded.nome, autorizacao=excluded.autorizacao,
                   prioridade=excluded.prioridade, limite_hora=excluded.limite_hora""",
            (login, nome, autorizacao, prioridade, limite_hora, agora()),
        )


def vigiado(login: str) -> sqlite3.Row | None:
    with conectar() as con:
        return con.execute("SELECT * FROM vigiados WHERE login=?", (login,)).fetchone()


def listar_vigiados(so_ativos: bool = False) -> list[sqlite3.Row]:
    where = "WHERE v.ativo=1" if so_ativos else ""
    with conectar() as con:
        return con.execute(
            f"""SELECT v.*,
                  (SELECT COUNT(*) FROM momentos m WHERE m.login=v.login AND m.job_id IS NOT NULL) AS clipes_ao_vivo,
                  (SELECT cegos FROM sessoes s WHERE s.login=v.login ORDER BY s.id DESC LIMIT 1) AS cegos
                FROM vigiados v {where} ORDER BY v.ativo DESC, v.prioridade DESC, v.login""",
        ).fetchall()


def atualizar_vigiado(login: str, **campos: Any) -> None:
    if not campos:
        return
    cols = ", ".join(f"{k}=?" for k in campos)
    with conectar() as con:
        con.execute(f"UPDATE vigiados SET {cols} WHERE login=?", (*campos.values(), login))


def apagar_vigiado(login: str) -> None:
    with conectar() as con:
        con.execute("DELETE FROM vigiados WHERE login=?", (login,))


# ---------- spec 002: sessões e momentos ----------

def abrir_sessao(login: str, titulo: str | None) -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO sessoes (login, inicio, titulo) VALUES (?,?,?)", (login, agora(), titulo)
        )
        return int(cur.lastrowid)


def fechar_sessao(sessao_id: int, vod_job_id: int | None = None) -> None:
    with conectar() as con:
        con.execute("UPDATE sessoes SET fim=?, vod_job_id=? WHERE id=?", (agora(), vod_job_id, sessao_id))


def registrar_cego(sessao_id: int, inicio: str, fim: str, motivo: str) -> None:
    with conectar() as con:
        row = con.execute("SELECT cegos FROM sessoes WHERE id=?", (sessao_id,)).fetchone()
        if not row:
            return
        cegos = json.loads(row["cegos"] or "[]")
        cegos = (cegos + [[inicio, fim, motivo]])[-20:]
        con.execute("UPDATE sessoes SET cegos=? WHERE id=?", (json.dumps(cegos), sessao_id))


def registrar_momento(sessao_id: int, login: str, instante: str, forca: float,
                      job_id: int | None, motivo: str | None) -> int:
    with conectar() as con:
        cur = con.execute(
            "INSERT INTO momentos (sessao_id, login, instante, forca, job_id, motivo) VALUES (?,?,?,?,?,?)",
            (sessao_id, login, instante, forca, job_id, motivo),
        )
        con.execute("UPDATE vigiados SET ultimo_pico=? WHERE login=?", (instante, login))
        return int(cur.lastrowid)


def clipes_ao_vivo_desde(login: str, desde_iso: str) -> int:
    with conectar() as con:
        return con.execute(
            "SELECT COUNT(*) FROM momentos WHERE login=? AND job_id IS NOT NULL AND instante>=?",
            (login, desde_iso),
        ).fetchone()[0]


def momentos_clipados(login: str) -> list[str]:
    """Instantes UTC (ISO) dos momentos que já viraram clipe ao vivo."""
    with conectar() as con:
        rows = con.execute(
            "SELECT instante FROM momentos WHERE lower(login)=lower(?) AND job_id IS NOT NULL", (login,)
        ).fetchall()
    return [r["instante"] for r in rows]


def momentos_recentes(limite: int = 30) -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute("SELECT * FROM momentos ORDER BY id DESC LIMIT ?", (limite,)).fetchall()


# ---------- spec 002: avisos e ajustes ----------

def ajuste(chave: str, padrao: str | None = None) -> str | None:
    with conectar() as con:
        row = con.execute("SELECT valor FROM ajustes WHERE chave=?", (chave,)).fetchone()
    return row["valor"] if row else padrao


def definir_ajuste(chave: str, valor: str) -> None:
    with conectar() as con:
        con.execute(
            "INSERT INTO ajustes (chave, valor) VALUES (?,?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
            (chave, valor),
        )


def avisos_pendentes() -> list[sqlite3.Row]:
    with conectar() as con:
        return con.execute(
            """SELECT a.id AS aviso_id, a.criado_em AS aviso_criado, c.*, j.canal AS canal, j.tipo AS job_tipo
               FROM avisos a JOIN clipes c ON c.id=a.clipe_id JOIN jobs j ON j.id=c.job_id
               WHERE a.status='pendente' ORDER BY a.id""",
        ).fetchall()


def marcar_avisos(ids: list[int], status: str) -> None:
    if not ids:
        return
    marks = ",".join("?" * len(ids))
    with conectar() as con:
        con.execute(
            f"UPDATE avisos SET status=?, enviado_em=? WHERE id IN ({marks})", (status, agora(), *ids)
        )
