"""The inbound interface the bot delegates to.

The Transaction Processor (TR-2) will implement ``TelegramUpdateHandler``; the bot
holds no workflow state itself (it only routes). ``LoggingUpdateHandler`` is a
scaffold stand-in used until TR-2 exists.
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class TelegramUpdateHandler(Protocol):
    async def on_callback(
        self, chat_id: int, message_id: int, data: str, callback_id: str
    ) -> None:
        """A user tapped an inline-keyboard button (data = its callback_data)."""

    async def on_message(self, chat_id: int, text: str) -> None:
        """A user sent a plain text message."""


class LoggingUpdateHandler:
    """Scaffold handler: logs what it receives. Replaced by the Processor (TR-2)."""

    async def on_callback(self, chat_id: int, message_id: int, data: str, callback_id: str) -> None:
        logger.info("callback from chat %s: %r (message %s)", chat_id, data, message_id)

    async def on_message(self, chat_id: int, text: str) -> None:
        logger.info("message from chat %s: %r", chat_id, text)
