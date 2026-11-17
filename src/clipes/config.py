"""Configuração lida do .env."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")


def _int(name: str, default: int) -> int:
    return int(os.getenv(name, default))


@dataclass(frozen=True)
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.getenv("DATA_DIR", ROOT / "data")))
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")
    llm_simples: str = os.getenv("LLM_SIMPLES", "gpt-6-luna")
    llm_complexo: str = os.getenv("LLM_COMPLEXO", "gpt-6.1-terra")
    nota_minima: int = _int("NOTA_MINIMA", 6)
    max_clipes_padrao: int = _int("MAX_CLIPES", 20)
    clipe_min_s: int = _int("CLIPE_MIN_S", 15)
    clipe_max_s: int = _int("CLIPE_MAX_S", 60)
    janela_s: int = _int("JANELA_S", 90)
    distancia_min_s: int = _int("DISTANCIA_MIN_S", 60)
    whisper_modelo: str = os.getenv("WHISPER_MODELO", "small")
    ytdlp_cookies: str = os.getenv("YTDLP_COOKIES", "")
    marca: str = os.getenv("MARCA", "")

    # monitor de lives (spec 002)
    telegram_token: str = os.getenv("TELEGRAM_TOKEN", "")
    telegram_chat_id: str = os.getenv("TELEGRAM_CHAT_ID", "")
    url_base: str = os.getenv("URL_BASE", "http://localhost:8000").rstrip("/")
    max_lives: int = _int("MAX_LIVES", 3)
    limite_hora_padrao: int = _int("LIMITE_HORA", 4)
    limiar_z: float = float(os.getenv("LIMIAR_Z", "3.0"))
    min_msgs_s: float = float(os.getenv("MIN_MSGS_S", "2.0"))
    qualidade_live: str = os.getenv("QUALIDADE_LIVE", "720p60,720p,480p,best")

    @property
    def db_path(self) -> Path:
        return self.data_dir / "clipes.db"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def trabalho_dir(self) -> Path:
        return self.data_dir / "trabalho"

    @property
    def clipes_dir(self) -> Path:
        return self.data_dir / "clipes"

    @property
    def ao_vivo_dir(self) -> Path:
        return self.data_dir / "ao_vivo"

    @property
    def spoilers_path(self) -> Path:
        return self.data_dir / "spoilers.txt"

    def garantir_pastas(self) -> None:
        for p in (self.data_dir, self.uploads_dir, self.trabalho_dir, self.clipes_dir, self.ao_vivo_dir):
            p.mkdir(parents=True, exist_ok=True)
        if not self.spoilers_path.exists():
            self.spoilers_path.write_text(
                "# Uma linha por item: missões, personagens, eventos da história do GTA VI.\n"
                "# Clipes que mencionem ou mostrem estes itens são marcados como spoiler.\n",
                encoding="utf-8",
            )


settings = Settings()
