"""Spec 002: live monitor, detector, notices. No network, no LLM."""

import shutil
import subprocess
from datetime import datetime, timedelta, timezone

import numpy as np
import pytest

from clipes import avisos, db, monitor
from clipes.config import Settings
from clipes.detector import Detector
from clipes.sinais import filtrar_ja_clipados
from clipes.twitch import login_do_link, parse_irc, peso_mensagem


# ---------- twitch ----------

def test_login_do_link():
    assert login_do_link("https://www.twitch.tv/Fulano") == "fulano"
    assert login_do_link("https://twitch.tv/fulano/videos") == "fulano"
    assert login_do_link("twitch.tv/fulano_123") == "fulano_123"
    assert login_do_link("@Fulano") == "fulano"
    assert login_do_link("fulano") == "fulano"
    assert login_do_link("https://www.twitch.tv/videos/123") is None
    assert login_do_link("https://www.youtube.com/@fulano") is None
    assert login_do_link("ab") is None
    assert login_do_link("") is None


def test_parse_irc():
    linha = ":user!user@user.tmi.twitch.tv PRIVMSG #fulano :KEKW que isso"
    assert parse_irc(linha) == ("fulano", "KEKW que isso")
    com_tags = "@badge-info=;color=#FF0000 :u!u@u.tmi.twitch.tv PRIVMSG #Fulano :oi :)"
    assert parse_irc(com_tags) == ("fulano", "oi :)")
    assert parse_irc(":tmi.twitch.tv 001 justinfan123 :Welcome") is None


def test_peso_mensagem():
    assert peso_mensagem("KEKW") == 3.0
    assert peso_mensagem("bom dia") == 1.0


# ---------- detector ----------

def _alimentar(det: Detector, serie) -> list[tuple[int, float]]:
    return [(i, z) for i, c in enumerate(serie) if (z := det.empurrar(c)) is not None]


def test_detector_acha_explosao_e_ignora_ruido():
    rng = np.random.default_rng(1)
    serie = list(rng.poisson(3, 600).astype(float))
    serie[400:410] = [30.0] * 10
    picos = _alimentar(Detector(), serie)
    assert len(picos) == 1
    assert 400 <= picos[0][0] <= 410


def test_detector_nao_dispara_no_aquecimento_nem_em_chat_vazio():
    assert _alimentar(Detector(), [0.0] * 100 + [50.0] * 5) == []  # less than 120 s of history
    assert _alimentar(Detector(), [0.0] * 300 + [1.0] * 5) == []   # below min msgs/s


def test_detector_dois_picos_proximos_viram_um():
    serie = [3.0] * 300 + [40.0] * 5 + [3.0] * 30 + [40.0] * 5 + [3.0] * 100
    assert len(_alimentar(Detector(), serie)) == 1


def test_detector_calibra_em_chat_movimentado():
    # 50 msgs/s steady is normal for a big channel: no peak; 200 msgs/s is
    rng = np.random.default_rng(2)
    serie = list(rng.normal(50, 5, 500).clip(0))
    assert _alimentar(Detector(), serie) == []
    serie[450:456] = [200.0] * 6
    assert len(_alimentar(Detector(), serie)) == 1


# ---------- buffer ----------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg ausente")
def test_cortar_buffer_junta_segmentos(tmp_path):
    t0 = datetime(2026, 11, 19, 20, 0, 0)
    for i in range(6):  # six 10 s segments = 20:00:00 .. 20:01:00
        nome = tmp_path / f"seg_{(t0 + timedelta(seconds=10 * i)).strftime('%Y%m%d%H%M%S')}.ts"
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=10",
             "-f", "lavfi", "-i", "sine=frequency=440", "-t", "10", "-c:v", "libx264", "-c:a", "aac",
             "-f", "mpegts", str(nome)], check=True,
        )
    segs = monitor.segmentos_entre(tmp_path, t0 + timedelta(seconds=15), t0 + timedelta(seconds=35))
    assert len(segs) == 3  # 20:00:10, :20, :30
    out = monitor.cortar_buffer(tmp_path, t0 + timedelta(seconds=15), t0 + timedelta(seconds=35),
                                tmp_path / "out.mp4")
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                                "-of", "csv=p=0", str(out)], capture_output=True, text=True).stdout)
    assert 28 <= dur <= 32
    monitor.podar_buffer(tmp_path, t0 + timedelta(seconds=600 + 15))
    assert len(list(tmp_path.glob("seg_*.ts"))) == 4  # the first two are older than 10 min


# ---------- VOD without duplicates ----------

def test_filtrar_ja_clipados():
    janelas = [(100.0, 190.0, 1.0), (500.0, 590.0, 0.9), (1000.0, 1090.0, 0.8)]
    assert filtrar_ja_clipados(janelas, [540.0]) == [janelas[0], janelas[2]]
    assert filtrar_ja_clipados(janelas, [640.0]) == [janelas[0], janelas[2]]  # within 60 s margin
    assert filtrar_ja_clipados(janelas, [2000.0]) == janelas
    assert filtrar_ja_clipados(janelas, []) == janelas


# ---------- notices ----------

def test_pronto_para_enviar_espera_ficar_quieto():
    agora = datetime(2026, 11, 19, 20, 0, 30, tzinfo=timezone.utc)
    antigo = (agora - timedelta(seconds=40)).isoformat()
    novo = (agora - timedelta(seconds=5)).isoformat()
    assert avisos.pronto_para_enviar([antigo], agora)
    assert not avisos.pronto_para_enviar([antigo, novo], agora)  # one just arrived: group it
    assert not avisos.pronto_para_enviar([], agora)


def test_montar_mensagem_agrupa_e_escapa():
    clipes = [
        {"job_id": 7, "titulo": "Ele <não> esperava", "canal": "fulano", "nota_llm": 8, "spoiler": 0,
         "job_tipo": "ao_vivo"},
        {"job_id": 7, "titulo": "Final da missão", "canal": "fulano", "nota_llm": 7, "spoiler": 1,
         "job_tipo": "ao_vivo"},
    ]
    texto, botoes = avisos.montar_mensagem(clipes, "https://mac.ts.net")
    assert "2 clipes" in texto and "&lt;não&gt;" in texto and "spoiler" in texto and "ao vivo" in texto
    assert botoes == [[{"text": "Revisar", "url": "https://mac.ts.net/job/7"}]]


@pytest.fixture
def banco(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "settings", Settings(data_dir=tmp_path))
    db.iniciar()
    return db


def test_clipe_em_revisao_gera_um_aviso_e_silencio_descarta(banco, monkeypatch):
    j = banco.criar_job("x.mp4", 1, "ao_vivo", canal="fulano")
    c = banco.criar_clipe(j, 0, 30, 1.0)
    banco.atualizar_clipe(c, status="revisao", titulo="t")
    banco.atualizar_clipe(c, status="aprovado")
    banco.atualizar_clipe(c, status="revisao")  # "undo" must not notify twice
    assert len(banco.avisos_pendentes()) == 1
    assert banco.avisos_pendentes()[0]["canal"] == "fulano"

    monkeypatch.setattr(avisos, "db", banco)
    avisos.silenciar(True)
    avisos.tique()
    assert banco.avisos_pendentes() == []


def test_fila_ao_vivo_separada(banco):
    vod = banco.criar_job("https://www.twitch.tv/videos/1", 20, "twitch_vod")
    live = banco.criar_job("a.mp4", 1, "ao_vivo", canal="fulano")
    assert banco.pegar_proximo_job(ao_vivo=True)["id"] == live
    assert banco.pegar_proximo_job(ao_vivo=False)["id"] == vod
    assert banco.pegar_proximo_job() is None


def test_limite_por_hora_conta_so_clipados(banco):
    s = banco.abrir_sessao("fulano", "live")
    agora = datetime.now(timezone.utc)
    banco.registrar_momento(s, "fulano", agora.isoformat(timespec="seconds"), 4.0, 10, None)
    banco.registrar_momento(s, "fulano", agora.isoformat(timespec="seconds"), 4.0, None, "limite")
    desde = (agora - timedelta(hours=1)).isoformat(timespec="seconds")
    assert banco.clipes_ao_vivo_desde("fulano", desde) == 1
