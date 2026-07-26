"""Telegram Bot (TR-6).

A **pure UI surface**: it renders notifications and option prompts, and relays the
user's raw taps/messages to a handler (the Transaction Processor, TR-2, owns all
workflow state and logic). Named ``telegram_bot`` to avoid clashing with
python-telegram-bot's own top-level ``telegram`` package.
"""

from expenses.telegram_bot.bot import ExpenseBot
from expenses.telegram_bot.ports import LoggingUpdateHandler, TelegramUpdateHandler

__all__ = ["ExpenseBot", "TelegramUpdateHandler", "LoggingUpdateHandler"]
