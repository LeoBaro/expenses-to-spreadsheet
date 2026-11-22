"""Run the long-lived application (TR-0).

``uv run expenses-serve`` starts the FastAPI app under uvicorn. Startup builds the
whole object graph, loads state, builds the cache, starts Telegram polling and the
internal poll scheduler — the app then runs until interrupted.
"""

from __future__ import annotations


from expenses.config import Settings
from expenses.logging_setup import configure_logging


def main() -> None:
    import uvicorn

    configure_logging()
    settings = Settings()
    uvicorn.run(
        "expenses.bootstrap.app:create_app",
        factory=True,
        host=settings.server_host,
        port=settings.server_port,
    )


if __name__ == "__main__":
    main()
