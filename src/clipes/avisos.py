"""Telegram notices (spec 002, H3): one grouped message when clips land in review.

Run `uv run python -m clipes.avisos` after sending any message to your bot to find your chat_id.
"""

import html
import json
import logging
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone

from clipes import db
from clipes.config import settings

log = logging.getLogger("clipes.avisos")

SILENCIO = "avisos_silenciados"
QUIETO_S = 15
MAX_ITENS = 8


def configurado() -> bool:
    return bool(settings.telegram_token and settings.telegram_chat_id)


def silenciado() -> bool:
    return db.ajuste(SILENCIO, "0") == "1"


def silenciar(sim: bool) -> None:
    db.definir_ajuste(SILENCIO, "1" if sim else "0")


# ---------- pure ----------

def _idade_s(iso: str, agora: datetime) -> float:
    return (agora - datetime.fromisoformat(iso)).total_seconds()


def pronto_para_enviar(criados_em: list[str], agora: datetime, quieto_s: int = QUIETO_S) -> bool:
    """Send when there is something pending and the newest one is at least `quieto_s` old."""
    if not criados_em:
        return False
    return min(_idade_s(c, agora) for c in criados_em) >= quieto_s


def montar_mensagem(clipes: list[dict], url_base: str) -> tuple[str, list[list[dict]]]:
    """(HTML text, inline keyboard) for a group of clips."""
    n = len(clipes)
    linhas = [f"<b>🎬 {n} clipe{'s' if n > 1 else ''} para revisar</b>", ""]
    for c in clipes[:MAX_ITENS]:
        alerta = " ⚠️ <b>spoiler</b>" if c.get("spoiler") else ""
        nota = f" · nota {c['nota_llm']}" if c.get("nota_llm") is not None else ""
        origem = " · 🔴 ao vivo" if c.get("job_tipo") == "ao_vivo" else ""
        titulo = html.escape(c.get("titulo") or "(sem título)")
        canal = html.escape(c.get("canal") or "")
        linhas.append(f"• {titulo}\n  <i>{canal}{nota}{origem}</i>{alerta}")
    if n > MAX_ITENS:
        linhas.append(f"… e mais {n - MAX_ITENS}")
    jobs = list(dict.fromkeys(c["job_id"] for c in clipes))
    botoes = [[{"text": "Revisar" if len(jobs) == 1 else f"Revisar envio {j}",
                "url": f"{url_base}/job/{j}"}] for j in jobs[:4]]
    if len(jobs) > 4:
        botoes.append([{"text": "Ver todos os envios", "url": f"{url_base}/"}])
    return "\n".join(linhas), botoes


# ---------- Telegram Bot API ----------

def _api(metodo: str, dados: dict) -> dict:
    url = f"https://api.telegram.org/bot{settings.telegram_token}/{metodo}"
    corpo = urllib.parse.urlencode(
        {k: json.dumps(v) if isinstance(v, (dict, list)) else v for k, v in dados.items()}
    ).encode()
    with urllib.request.urlopen(urllib.request.Request(url, data=corpo), timeout=15) as r:
        resp = json.loads(r.read())
    if not resp.get("ok"):
        raise RuntimeError(resp.get("description") or "Telegram recusou")
    return resp


def enviar(texto: str, botoes: list[list[dict]] | None = None) -> None:
    dados = {"chat_id": settings.telegram_chat_id, "text": texto, "parse_mode": "HTML",
             "disable_web_page_preview": "true"}
    if botoes:
        dados["reply_markup"] = {"inline_keyboard": botoes}
    _api("sendMessage", dados)


def enviar_teste() -> None:
    enviar("✅ <b>Clipes</b>: avisos funcionando. Você vai receber os clipes novos aqui.",
           [[{"text": "Abrir o site", "url": f"{settings.url_base}/"}]])


# ---------- loop ----------

def tique(agora: datetime | None = None) -> None:
    pend = db.avisos_pendentes()
    if not pend:
        return
    ids = [p["aviso_id"] for p in pend]
    if silenciado():
        db.marcar_avisos(ids, "silenciado")
        return
    if not configurado():
        db.marcar_avisos(ids, "sem_config")  # don't pile up and flood once configured
        return
    agora = agora or datetime.now(timezone.utc)
    if not pronto_para_enviar([p["aviso_criado"] for p in pend], agora):
        return
    texto, botoes = montar_mensagem([dict(p) for p in pend], settings.url_base)
    try:
        enviar(texto, botoes)
        db.marcar_avisos(ids, "enviado")
    except Exception as e:
        log.warning("aviso no Telegram falhou: %s", e)
        db.marcar_avisos(ids, "erro")


def loop(parar: threading.Event) -> None:
    while not parar.is_set():
        try:
            tique()
        except Exception:
            log.exception("avisos: erro")
        parar.wait(5)


def _descobrir_chat_id() -> None:
    if not settings.telegram_token:
        print("Coloque TELEGRAM_TOKEN no .env primeiro (crie o bot com o @BotFather).")
        return
    resp = _api("getUpdates", {})
    vistos = {}
    for u in resp.get("result", []):
        msg = u.get("message") or u.get("channel_post") or {}
        chat = msg.get("chat") or {}
        if chat.get("id"):
            vistos[chat["id"]] = chat.get("username") or chat.get("title") or chat.get("first_name")
    if not vistos:
        print("Nenhuma mensagem encontrada. Mande 'oi' para o seu bot no Telegram e rode de novo.")
    for cid, nome in vistos.items():
        print(f"TELEGRAM_CHAT_ID={cid}    ({nome})")


if __name__ == "__main__":
    _descobrir_chat_id()
