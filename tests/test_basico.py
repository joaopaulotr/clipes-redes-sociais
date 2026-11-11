import numpy as np

from clipes.fontes import classificar, minutagens
from clipes.render import gerar_ass
from clipes.sinais import comentarios, escolher_janelas, heatmap, picos_relativos
from clipes.transcricao import Palavra, texto_com_tempo


def test_classificar():
    assert classificar("https://www.youtube.com/watch?v=abc") == "youtube"
    assert classificar("https://youtu.be/abc") == "youtube"
    assert classificar("https://www.twitch.tv/videos/123") == "twitch_vod"
    assert classificar("https://clips.twitch.tv/Algo-xyz") == "twitch_clip"
    assert classificar("https://www.twitch.tv/fulano/clip/Algo-xyz") == "twitch_clip"
    assert classificar("https://kick.com/fulano/videos/abc") == "kick"
    assert classificar("https://exemplo.com/video.mp4") == "mp4_url"
    assert classificar("https://exemplo.com/pagina") == "generic"
    assert classificar(r"C:\videos\a.mp4") == "upload"


def test_minutagens():
    assert minutagens("kkkk 2:14 e 1:02:33") == [134, 3753]
    assert minutagens("nada aqui 12:75") == []
    assert minutagens("0:05") == [5]


def test_picos_relativos_acha_explosao():
    x = np.ones(1000)
    x[500:510] = 20
    p = picos_relativos(x)
    assert p.argmax() in range(495, 515)
    assert p.max() == 1.0


def test_escolher_janelas_respeita_distancia():
    s = np.zeros(1000)
    s[100] = 1.0
    s[120] = 0.9  # perto demais do 100: ignorado
    s[600] = 0.8
    j = escolher_janelas(s, 5, 90, 60, 1000)
    assert len(j) == 2
    assert j[0][0] == 40 and j[0][1] == 130
    assert j[1][0] == 540


def test_heatmap_e_comentarios():
    h = heatmap([{"start_time": 50, "end_time": 60, "value": 1.0}], 100)
    assert h[55] == 1.0 and h[10] == 0
    c = comentarios(["olha 1:00 kkkk", "1:01 mds"], 200)
    assert c[60] > 0 and c[150] == 0


def test_gerar_ass_destaca_palavra():
    ps = [Palavra(0, 0.4, "que"), Palavra(0.5, 0.9, "isso"), Palavra(1.0, 1.5, "{mano}")]
    ass = gerar_ass(ps, 5, "OLHA ISSO", "@fulano")
    assert "Dialogue" in ass and "OLHA ISSO" in ass and "@fulano" in ass
    assert "{mano}" not in ass.replace("{\\c", "")  # chaves do texto escapadas


def test_texto_com_tempo():
    ps = [Palavra(0, 0.5, "a"), Palavra(1, 1.5, "b"), Palavra(6, 6.5, "c")]
    assert texto_com_tempo(ps) == "[0.0] a b\n[6.0] c"
