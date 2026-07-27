"""The Telegram bot wrapper around python-telegram-bot (TR-6).

Transport only: it wires PTB handlers that **delegate** to a ``TelegramUpdateHandler``
(the Processor, TR-2), and exposes outbound send methods the Processor calls. It holds
no workflow state — deliberately no ConversationHandler.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from expenses.telegram_bot.keyboards import options_keyboard
from expenses.telegram_bot.ports import TelegramUpdateHandler

logger = logging.getLogger(__name__)


class ExpenseBot:
    def __init__(self, application: Application, handler: TelegramUpdateHandler) -> None:
        self._app = application
        self._handler = handler
        self._register_handlers()

    @classmethod
    def build(cls, token: str, handler: TelegramUpdateHandler) -> "ExpenseBot":
        application = ApplicationBuilder().token(token).build()
        return cls(application, handler)

    @property
    def application(self) -> Application:
        return self._app

    # --- inbound: PTB handlers delegate to the Processor ---

    def _register_handlers(self) -> None:
        self._app.add_handler(CommandHandler("start", self._on_start))
        self._app.add_handler(CallbackQueryHandler(self._on_callback))
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._on_message))
        self._app.add_error_handler(self._on_error)

    async def _on_error(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.error("unhandled bot error: %s", context.error, exc_info=context.error)

    async def _on_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        chat = update.effective_chat
        if chat is None:
            return
        await context.bot.send_message(
            chat.id,
            f"Expense bot ready.\nYour chat id is: {chat.id}\n"
            f"Put it in EXPENSES_TELEGRAM_CHAT_ID.",
        )

    async def _on_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.message is None:
            return
        try:
            await query.answer()  # acknowledge the tap (stops the spinner)
        except BadRequest as exc:
            # Stale callback (tapped before we were polling): nothing to ack. Route anyway.
            logger.warning("could not answer callback %s: %s", query.id, exc)
        await self._handler.on_callback(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            data=query.data or "",
            callback_id=query.id,
        )

    async def _on_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        message = update.effective_message
        if message is None:
            return
        await self._handler.on_message(chat_id=message.chat_id, text=message.text or "")

    # --- outbound: called by the Processor (TR-2) ---

    async def send_message(self, chat_id: int, text: str) -> None:
        """Send an informational notification (FR-5)."""
        await self._app.bot.send_message(chat_id, text)

    async def send_options(
        self,
        chat_id: int,
        text: str,
        options: list[str],
        *,
        tag: str = "",
        done_label: str | None = None,
        skip_label: str | None = None,
    ) -> None:
        """Send a prompt with an inline keyboard of choices (FR-6/7/8).

        ``tag`` identifies the workflow step; each button's callback_data is
        ``f"{tag}:{index}"`` so the Processor can map a tap back to the option.
        ``done_label``/``skip_label``, when set, append confirm / skip buttons
        (multi-select steps)."""
        await self._app.bot.send_message(
            chat_id,
            text,
            reply_markup=options_keyboard(options, tag=tag, done_label=done_label, skip_label=skip_label),
        )

    async def edit_options(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        options: list[str],
        *,
        tag: str = "",
        done_label: str | None = None,
        skip_label: str | None = None,
    ) -> None:
        """Re-render an existing prompt in place (used by the additive multi-select step
        so toggling a word updates the same message instead of sending a new one)."""
        try:
            await self._app.bot.edit_message_text(
                text,
                chat_id=chat_id,
                message_id=message_id,
                reply_markup=options_keyboard(
                    options, tag=tag, done_label=done_label, skip_label=skip_label
                ),
            )
        except BadRequest as exc:
            # "Message is not modified" (e.g. a duplicate tap) is harmless; log and move on.
            logger.warning("could not edit message %s: %s", message_id, exc)

    # --- lifecycle ---

    def run_polling(self) -> None:
        """Standalone long polling (manages its own event loop). For running inside an
        existing FastAPI loop (TR-0), use the Application's initialize/start/updater
        methods instead."""
        self._app.run_polling()
