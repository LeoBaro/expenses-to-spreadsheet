"""Telegram bot CLI (scaffold).

- ``uv run expenses-telegram run``        long-poll; logs incoming messages/taps.
  Send /start to the bot to learn your chat id.
- ``uv run expenses-telegram send-test``  push a message with two inline buttons to
  EXPENSES_TELEGRAM_CHAT_ID and exit (tests the outbound + callback round trip while
  `run` is polling in another terminal).
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from expenses.config import Settings
from expenses.telegram_bot.bot import ExpenseBot
from expenses.telegram_bot.ports import LoggingUpdateHandler

logger = logging.getLogger(__name__)


def _require_token(settings: Settings) -> str:
    if not settings.telegram_bot_token:
        raise SystemExit("EXPENSES_TELEGRAM_BOT_TOKEN is not set.")
    return settings.telegram_bot_token


def _run(settings: Settings) -> None:
    bot = ExpenseBot.build(_require_token(settings), LoggingUpdateHandler())
    logger.info("Polling… send /start to the bot to see your chat id. Ctrl-C to stop.")
    bot.run_polling()


async def _send_test(settings: Settings) -> None:
    token = _require_token(settings)
    if settings.telegram_chat_id is None:
        raise SystemExit("EXPENSES_TELEGRAM_CHAT_ID is not set (run `expenses-telegram run` and /start first).")
    bot = ExpenseBot.build(token, LoggingUpdateHandler())
    async with bot.application:  # initialize + shutdown
        await bot.send_options(
            settings.telegram_chat_id,
            "Scaffold test — pick one:",
            ["Categorize", "Ignore"],
        )
    print("Sent. Tap a button in Telegram; `expenses-telegram run` will log the callback.")


def main() -> None:
    parser = argparse.ArgumentParser(prog="expenses-telegram", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("run", help="start long polling (logs incoming updates)")
    sub.add_parser("send-test", help="send a test message with inline buttons to the configured chat")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = Settings()
    if args.command == "run":
        _run(settings)
    elif args.command == "send-test":
        asyncio.run(_send_test(settings))


if __name__ == "__main__":
    main()
