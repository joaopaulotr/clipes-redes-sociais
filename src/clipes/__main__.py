"""uv run python -m clipes  →  sobe o site + worker."""

import os

import uvicorn

from clipes.config import ROOT  # noqa: F401  (carrega o .env)


def main() -> None:
    uvicorn.run(
        "clipes.web.app:app",
        host=os.getenv("HOST", "127.0.0.1"),
        port=int(os.getenv("PORT", "8000")),
    )


if __name__ == "__main__":
    main()
