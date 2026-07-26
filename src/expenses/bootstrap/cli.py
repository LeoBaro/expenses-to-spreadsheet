"""Run the long-lived application (TR-0).

``uv run expenses-serve`` starts the FastAPI app under uvicorn. Startup builds the
whole object graph, loads state, builds the cache, starts Telegram polling and the
internal poll scheduler — the app then runs until interrupted.
"""

from __future__ import annotations

import logging

from expenses.config import Settings


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings()
    uvicorn.run(
        "expenses.bootstrap.app:create_app",
        factory=True,
        host=settings.server_host,
        port=settings.server_port,
    )


if __name__ == "__main__":
    main()
