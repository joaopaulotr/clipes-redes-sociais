"""Live monitor (spec 002): one thread per watched Twitch channel.

offline -> (live) session: record 10 s segments + read chat -> Detector -> peak
        -> wait 30 s -> per-hour limit -> cut buffer to .mp4 -> job 'ao_vivo' (MVP1 pipeline)
        -> (offline for 5 min) close session -> delete buffer -> queue the VOD (H4)
"""

import logging
import shutil
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from clipes import db, twitch
from clipes.config import settings
from clipes.detector import Detector

log = logging.getLogger("clipes.monitor")

ATRASO_CHAT_S = 8          # chat reacts a few seconds after the moment
ANTES_S = 60               # seconds of video before the moment
DEPOIS_S = 30              # seconds after the moment (also how long we wait before cutting)
BUFFER_S = 600             # keep 10 min of segments
CHECAR_STATUS_S = 60       # how often to ask "is it live?"
OFFLINE_FECHA_S = 300      # offline this long = stream ended (RF-004, reconnect edge case)
SALTO_RELOGIO_S = 30       # bigger jump = machine slept / froze -> blind interval

_gravando: set[str] = set()
_trava = threading.Lock()


def _utc_iso(dt_local: datetime) -> str:
    return dt_local.astimezone(timezone.utc).isoformat(timespec="seconds")


# ---------- buffer ----------

def _inicio_segmento(p: Path) -> datetime | None:
    try:
        return datetime.strptime(p.stem.removeprefix("seg_"), "%Y%m%d%H%M%S")
    except ValueError:
        return None


def segmentos_entre(pasta: Path, inicio: datetime, fim: datetime) -> list[Path]:
    """Segments (10 s each) that overlap [inicio, fim], in order. Pure apart from listing the folder."""
    out = []
    for p in sorted(pasta.glob("seg_*.ts")):
        t = _inicio_segmento(p)
        if t is None:
            continue
        if t + timedelta(seconds=10) >= inicio and t <= fim:
            out.append(p)
    return out


def cortar_buffer(pasta: Path, inicio: datetime, fim: datetime, destino: Path) -> Path:
    """Joins the segments around the moment into one .mp4 (stream copy, no re-encode)."""
    segs = segmentos_entre(pasta, inicio, fim)
    if not segs:
        raise RuntimeError("buffer vazio para o momento (gravação ainda não começou?)")
    destino.parent.mkdir(parents=True, exist_ok=True)
    lista = destino.with_suffix(".txt")
    lista.write_text("".join(f"file '{s.resolve()}'\n" for s in segs), encoding="utf-8")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lista),
             "-c", "copy", "-movflags", "+faststart", str(destino)],
            check=True,
        )
    finally:
        lista.unlink(missing_ok=True)
    return destino


def podar_buffer(pasta: Path, agora: datetime) -> None:
    limite = agora - timedelta(seconds=BUFFER_S)
    for p in pasta.glob("seg_*.ts"):
        t = _inicio_segmento(p)
        if t and t < limite:
            p.unlink(missing_ok=True)


# ---------- one channel ----------

class Vigia(threading.Thread):
    def __init__(self, login: str, parar: threading.Event):
        super().__init__(daemon=True, name=f"vigia-{login}")
        self.login = login
        self.parar_global = parar
        self.parar = threading.Event()
        self.pasta = settings.ao_vivo_dir / login

    # -- helpers --
    _cache_ativo: tuple[float, bool] = (0.0, True)

    def _ativo(self) -> bool:
        if self.parar.is_set() or self.parar_global.is_set():
            return False
        quando, valor = self._cache_ativo
        if time.monotonic() - quando > 5:  # the session loop ticks ~5x/s; don't hit SQLite each time
            v = db.vigiado(self.login)
            valor = bool(v and v["ativo"])
            self._cache_ativo = (time.monotonic(), valor)
        return valor

    def _esperar(self, s: float) -> None:
        fim = time.monotonic() + s
        while time.monotonic() < fim and self._ativo():
            time.sleep(min(1.0, fim - time.monotonic()))

    def _status(self) -> twitch.Status | None:
        try:
            return twitch.status(self.login)
        except Exception as e:
            log.warning("%s: não consegui checar status: %s", self.login, e)
            db.atualizar_vigiado(self.login, erro=str(e)[:300])
            return None

    def _vaga(self) -> bool:
        """MAX_LIVES recorded at once; higher priority first among those waiting."""
        with _trava:
            if self.login in _gravando:
                return True
            if len(_gravando) >= settings.max_lives:
                return False
            _gravando.add(self.login)
            return True

    def _liberar_vaga(self) -> None:
        with _trava:
            _gravando.discard(self.login)

    # -- main loop --
    def run(self) -> None:
        log.info("%s: vigiando", self.login)
        try:
            while self._ativo():
                st = self._status()
                if st and st.ao_vivo:
                    if self._vaga():
                        self._sessao(st)
                        continue
                    db.atualizar_vigiado(self.login, status="espera")
                elif st:
                    db.atualizar_vigiado(self.login, status="offline", erro=None)
                self._esperar(CHECAR_STATUS_S)
        finally:
            self._liberar_vaga()
            if not self._ativo():
                db.atualizar_vigiado(self.login, status="offline")
            log.info("%s: parou de vigiar", self.login)

    def _sessao(self, st: twitch.Status) -> None:
        login = self.login
        sessao = db.abrir_sessao(login, st.titulo)
        db.atualizar_vigiado(login, status="gravando", nome=st.nome or None, erro=None)
        log.info("%s: ao vivo (%s), gravando", login, st.titulo)
        shutil.rmtree(self.pasta, ignore_errors=True)
        procs = twitch.iniciar_gravacao(login, self.pasta)
        chat = twitch.Chat(login)
        det = Detector(limiar_z=settings.limiar_z, min_msgs_s=settings.min_msgs_s)
        pendentes: list[tuple[datetime, float]] = []   # (moment, strength) waiting for the post-roll
        titulo = st.titulo
        espera_chat = 2.0
        chat_caiu_em: datetime | None = None
        ultimo_status = time.monotonic()
        offline_desde: float | None = None
        segundo = int(time.time())
        contagem = 0.0
        tique_anterior = time.time()

        try:
            chat.conectar()
        except OSError as e:
            chat_caiu_em = datetime.now()
            log.warning("%s: chat não conectou: %s", login, e)

        try:
            while self._ativo():
                agora_t = time.time()
                agora = datetime.now()

                # machine slept / froze: blind interval, recalibrate
                if agora_t - tique_anterior > SALTO_RELOGIO_S:
                    ini = datetime.fromtimestamp(tique_anterior)
                    db.registrar_cego(sessao, _utc_iso(ini), _utc_iso(agora), "computador parado")
                    det.esquecer()
                    pendentes.clear()
                tique_anterior = agora_t

                # chat
                if chat.sock:
                    try:
                        for msg in chat.ler():
                            contagem += twitch.peso_mensagem(msg)
                        espera_chat = 2.0
                    except (OSError, ConnectionError) as e:
                        log.warning("%s: chat caiu: %s", login, e)
                        chat.fechar()
                        chat_caiu_em = agora
                else:
                    time.sleep(0.2)
                    if chat_caiu_em and (agora - chat_caiu_em).total_seconds() >= espera_chat:
                        try:
                            chat.conectar()
                            db.registrar_cego(sessao, _utc_iso(chat_caiu_em), _utc_iso(agora), "chat fora")
                            chat_caiu_em = None
                            det.esquecer()
                        except OSError:
                            espera_chat = min(espera_chat * 2, 60)

                # one second closed -> detector
                s_atual = int(agora_t)
                while segundo < s_atual:
                    forca = det.empurrar(contagem)
                    contagem = 0.0
                    if forca is not None:
                        momento = datetime.fromtimestamp(segundo) - timedelta(seconds=ATRASO_CHAT_S)
                        log.info("%s: pico z=%.1f em %s", login, forca, momento.strftime("%H:%M:%S"))
                        pendentes.append((momento, forca))
                    segundo += 1

                # post-roll elapsed -> cut and queue
                for item in [p for p in pendentes if agora >= p[0] + timedelta(seconds=DEPOIS_S + 5)]:
                    pendentes.remove(item)
                    self._clipar(sessao, item[0], item[1], titulo)

                # periodic: status, recorder health, buffer
                if time.monotonic() - ultimo_status >= CHECAR_STATUS_S:
                    ultimo_status = time.monotonic()
                    podar_buffer(self.pasta, agora)
                    st2 = self._status()
                    if st2 and not st2.ao_vivo:
                        offline_desde = offline_desde or time.monotonic()
                        if time.monotonic() - offline_desde >= OFFLINE_FECHA_S:
                            break
                    elif st2:
                        offline_desde = None
                        titulo = st2.titulo or titulo
                        if any(p.poll() is not None for p in procs):  # recorder died while live
                            log.warning("%s: gravação parou, reiniciando", login)
                            db.registrar_cego(sessao, _utc_iso(agora - timedelta(seconds=CHECAR_STATUS_S)),
                                              _utc_iso(agora), "gravação reiniciada")
                            self._matar(procs)
                            procs = twitch.iniciar_gravacao(login, self.pasta)
        finally:
            self._matar(procs)
            chat.fechar()
            shutil.rmtree(self.pasta, ignore_errors=True)
            vod_job = self._enfileirar_vod() if offline_desde else None
            db.fechar_sessao(sessao, vod_job)
            self._liberar_vaga()
            db.atualizar_vigiado(login, status="offline")
            log.info("%s: sessão %s encerrada", login, sessao)

    def _clipar(self, sessao: int, momento: datetime, forca: float, titulo: str) -> None:
        login = self.login
        instante = _utc_iso(momento)
        v = db.vigiado(login)
        limite = v["limite_hora"] if v else settings.limite_hora_padrao
        uma_hora = _utc_iso(momento - timedelta(hours=1))
        if db.clipes_ao_vivo_desde(login, uma_hora) >= limite:
            db.registrar_momento(sessao, login, instante, forca, None, f"limite de {limite}/hora")
            log.info("%s: pico ignorado (limite/hora)", login)
            return
        destino = settings.uploads_dir / f"aovivo_{login}_{uuid.uuid4().hex[:8]}.mp4"
        try:
            cortar_buffer(self.pasta, momento - timedelta(seconds=ANTES_S),
                          momento + timedelta(seconds=DEPOIS_S), destino)
        except Exception as e:
            db.registrar_momento(sessao, login, instante, forca, None, f"corte falhou: {str(e)[:150]}")
            log.warning("%s: corte falhou: %s", login, e)
            return
        rotulo = f"Ao vivo · {momento.strftime('%H:%M')}" + (f" · {titulo}" if titulo else "")
        job = db.criar_job(str(destino), 1, "ao_vivo", canal=login, titulo=rotulo[:200])
        db.registrar_momento(sessao, login, instante, forca, job, None)
        log.info("%s: momento virou envio %s", login, job)

    def _enfileirar_vod(self) -> int | None:
        try:
            url = twitch.ultimo_vod(self.login)
        except Exception as e:
            log.warning("%s: não achei VOD: %s", self.login, e)
            return None
        if not url:
            log.info("%s: canal sem VOD publicado; História 4 pulada", self.login)
            return None
        return db.criar_job(url, settings.max_clipes_padrao, "twitch_vod", canal=self.login)

    @staticmethod
    def _matar(procs) -> None:
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()


# ---------- supervisor ----------

def loop(parar: threading.Event) -> None:
    """Starts one Vigia per active channel and stops the ones that were deactivated."""
    vigias: dict[str, Vigia] = {}
    while not parar.is_set():
        try:
            ativos = [v["login"] for v in db.listar_vigiados(so_ativos=True)]  # priority order
            for login in ativos:
                t = vigias.get(login)
                if t is None or not t.is_alive():
                    vigias[login] = Vigia(login, parar)
                    vigias[login].start()
            for login in list(vigias):
                if login not in ativos:
                    vigias.pop(login).parar.set()
        except Exception:
            log.exception("monitor: erro no supervisor")
        parar.wait(10)
    for t in vigias.values():
        t.parar.set()
