"""Edição: frames, legenda .ass palavra a palavra e render 9:16 com ffmpeg."""

import subprocess
from pathlib import Path

from clipes.transcricao import Palavra

LARGURA, ALTURA = 1080, 1920
ALTURA_CAM = 640  # terço de cima quando há webcam
AMARELO = "&H0000FFFF&"  # ASS usa BGR


def extrair_frame(video: Path, t: float, destino: Path, largura: int = 640) -> Path:
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error", "-ss", f"{max(t, 0):.2f}", "-i", str(video),
         "-frames:v", "1", "-vf", f"scale={largura}:-2", "-q:v", "4", str(destino)],
        check=True,
    )
    return destino


def _tempo_ass(s: float) -> str:
    s = max(0.0, s)
    h, resto = divmod(s, 3600)
    m, seg = divmod(resto, 60)
    return f"{int(h)}:{int(m):02d}:{seg:05.2f}"


def _esc(texto: str) -> str:
    return texto.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ")


def gerar_ass(
    palavras: list[Palavra], duracao: float, gancho: str, credito: str,
    por_grupo: int = 3, margem_legenda: int = 560,
) -> str:
    """Legenda: grupos de `por_grupo` palavras, palavra atual em amarelo.
    `palavras` já com tempo relativo ao início do clipe."""
    cab = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {LARGURA}
PlayResY: {ALTURA}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Legenda,Arial Black,78,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,1,0,0,0,100,100,0,0,1,6,2,2,60,60,{margem_legenda},1
Style: Gancho,Arial Black,72,&H00000000,&H00000000,&H00FFFFFF,&H00FFFFFF,1,0,0,0,100,100,0,0,3,14,0,8,80,80,170,1
Style: Credito,Arial,38,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,3,0,2,40,40,70,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    linhas = []
    for i in range(0, len(palavras), por_grupo):
        grupo = palavras[i:i + por_grupo]
        for j, atual in enumerate(grupo):
            ini = atual.inicio
            fim = grupo[j + 1].inicio if j + 1 < len(grupo) else atual.fim
            if fim - ini < 0.05:
                continue
            partes = []
            for k, p in enumerate(grupo):
                t = _esc(p.texto).upper()
                partes.append(f"{{\\c{AMARELO}}}{t}{{\\c&H00FFFFFF&}}" if k == j else t)
            linhas.append(
                f"Dialogue: 0,{_tempo_ass(ini)},{_tempo_ass(fim)},Legenda,,0,0,0,,{' '.join(partes)}"
            )
    if gancho:
        linhas.append(
            f"Dialogue: 1,{_tempo_ass(0)},{_tempo_ass(min(2.5, duracao))},Gancho,,0,0,0,,{_esc(gancho).upper()}"
        )
    if credito:
        linhas.append(f"Dialogue: 0,{_tempo_ass(0)},{_tempo_ass(duracao)},Credito,,0,0,0,,{_esc(credito)}")
    return cab + "\n".join(linhas) + "\n"


def filtro_video(webcam: dict | None) -> str:
    """filter_complex 1080x1920. Termina em [base] (legenda aplicada depois)."""
    if webcam:
        x, y, w, h = webcam["x"], webcam["y"], webcam["w"], webcam["h"]
        jogo_h = ALTURA - ALTURA_CAM
        prop = LARGURA / jogo_h
        return (
            "[0:v]split=2[a][b];"
            f"[a]crop=iw*{w:.4f}:ih*{h:.4f}:iw*{x:.4f}:ih*{y:.4f},"
            f"scale={LARGURA}:{ALTURA_CAM}:force_original_aspect_ratio=increase,"
            f"crop={LARGURA}:{ALTURA_CAM}[cam];"
            f"[b]crop='min(iw,ih*{prop:.4f})':ih:'(iw-min(iw,ih*{prop:.4f}))/2':0,"
            f"scale={LARGURA}:{jogo_h}:force_original_aspect_ratio=increase,crop={LARGURA}:{jogo_h}[jogo];"
            "[cam][jogo]vstack=inputs=2,setsar=1[base]"
        )
    return (
        "[0:v]split=2[a][b];"
        f"[a]scale={LARGURA}:{ALTURA}:force_original_aspect_ratio=increase,crop={LARGURA}:{ALTURA},"
        "boxblur=20:5[fundo];"
        f"[b]scale={LARGURA}:-2[frente];"
        "[fundo][frente]overlay=(W-w)/2:(H-h)/2,setsar=1[base]"
    )


def renderizar(
    fonte: Path, inicio: float, fim: float, palavras: list[Palavra],
    gancho: str, credito: str, webcam: dict | None, destino: Path,
) -> Path:
    """Corta [inicio, fim] de `fonte` (segundos relativos ao arquivo) e gera o 9:16 final."""
    duracao = fim - inicio
    rel = [Palavra(p.inicio - inicio, p.fim - inicio, p.texto)
           for p in palavras if p.fim > inicio and p.inicio < fim]
    margem = 560 if not webcam else 300
    ass = destino.with_suffix(".ass")
    ass.write_text(gerar_ass(rel, duracao, gancho, credito, margem_legenda=margem), encoding="utf-8")

    filtro = filtro_video(webcam) + f";[base]ass={ass.name}[v]"
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-ss", f"{inicio:.2f}", "-t", f"{duracao:.2f}", "-i", str(fonte.resolve()),
         "-filter_complex", filtro, "-map", "[v]", "-map", "0:a?",
         "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", destino.name],
        check=True, cwd=destino.parent,  # cwd evita escapar 'C:\' no filtro ass
    )
    ass.unlink(missing_ok=True)
    return destino
