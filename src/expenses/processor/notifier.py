"""Telegram adapter for the Processor's Notifier port.

Bridges the pure-UI bot (TR-6) to the Processor (TR-2): the Processor calls
``notify(text)``; this sends it to the configured chat. Wired by the composition
root (TR-0)."""

from __future__ import annotations

from expenses.telegram_bot.bot import ExpenseBot


class TelegramNotifier:
    def __init__(self, bot: ExpenseBot, chat_id: int) -> None:
        self._bot = bot
        self._chat_id = chat_id

    async def notify(self, text: str) -> None:
        await self._bot.send_message(self._chat_id, text)
