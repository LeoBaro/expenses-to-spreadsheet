"""The Composition Root (TR-0).

The single module that knows every concrete implementation and assembles the whole
object graph by constructor injection against the Protocol *ports* each component
declares. No component constructs its own collaborators; nothing here is a runtime
call — this builds the graph, then steps out of the runtime path.

Manual "poor-man's DI" (plain constructor calls): for a single-user app a DI
container is out of scope.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

from expenses.cache.manager import CacheManager
from expenses.categorization.engine import CategorizationEngine
from expenses.config import Settings
from expenses.poller.enable_banking.auth import EnableBankingAuth
from expenses.poller.enable_banking.gateway import EnableBankingGateway
from expenses.poller.poller import TransactionPoller
from expenses.poller.scheduler import IntervalScheduler
from expenses.processor.notifier import TelegramNotifier
from expenses.processor.ports import LoggingNotifier, LoggingUnknownHandler, Notifier
from expenses.processor.processor import TransactionProcessor
from expenses.sheets.client import GoogleSheetsClient
from expenses.state.manager import StateManager
from expenses.telegram_bot.bot import ExpenseBot
from expenses.telegram_bot.ports import LoggingUpdateHandler

logger = logging.getLogger(__name__)


class PollCycle:
    """Wraps one poll cycle to surface Enable Banking **consent expiry** (TR-0 DD).

    The authorized session behind ``eb_account_uid`` expires (``valid_until``; ~90
    days in production). When it lapses, Enable Banking answers 401/403 and polling
    must not silently stop — we notify the user (Telegram) to re-run the consent
    flow, then keep looping so recovery is automatic once they re-authorize.

    The notification is sent once per expiry (not every cycle) and re-armed after
    the next successful poll.
    """

    def __init__(self, poller: TransactionPoller, notifier: Notifier) -> None:
        self._poller = poller
        self._notifier = notifier
        self._expiry_notified = False

    async def __call__(self) -> object:
        try:
            result = await self._poller.poll_once()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code in (401, 403):
                await self._notify_expiry()
                return None
            raise
        else:
            self._expiry_notified = False  # re-arm: a good poll means the session is live
            return result

    async def _notify_expiry(self) -> None:
        logger.error("Enable Banking returned an auth error — session likely expired")
        if self._expiry_notified:
            return
        self._expiry_notified = True
        try:
            await self._notifier.notify(
                "⚠️ Enable Banking authorization has expired or been revoked.\n"
                "Expense polling is paused. Re-run the consent flow "
                "(`expenses-consent authorize …`) and update EXPENSES_EB_ACCOUNT_UID "
                "to reconnect."
            )
        except Exception:  # noqa: BLE001 - a failed notification must not kill the loop
            logger.exception("failed to send consent-expiry notification")


@dataclass
class Components:
    """The assembled object graph. Held by the FastAPI app so the lifespan can drive
    startup/shutdown and the health endpoint can inspect state."""

    settings: Settings
    http_client: httpx.AsyncClient
    sheets: GoogleSheetsClient
    cache: CacheManager
    engine: CategorizationEngine
    state: StateManager
    processor: TransactionProcessor
    poller: TransactionPoller
    scheduler: IntervalScheduler
    bot: ExpenseBot | None


def build_components(settings: Settings) -> Components:
    """Construct and wire every component from validated settings."""
    if not settings.eb_account_uid:
        raise RuntimeError(
            "EXPENSES_EB_ACCOUNT_UID is not set. Complete the one-time consent flow "
            "(`expenses-consent`) to obtain an account UID before serving."
        )

    # --- Enable Banking (TR-1) ---
    http_client = httpx.AsyncClient(timeout=30.0)
    auth = EnableBankingAuth(settings.eb_application_id, settings.private_key())
    gateway = EnableBankingGateway(http_client, auth, settings.eb_api_base_url)

    # --- Sheets → Cache → Engine (TR-4/5/3) ---
    sheets = GoogleSheetsClient.from_settings(settings)
    cache = CacheManager(sheets)
    engine = CategorizationEngine(cache)

    # --- State (TR-7) ---
    state = StateManager(settings.state_file_path)

    # --- Telegram (TR-6) + notifier (TR-2 port) ---
    bot: ExpenseBot | None = None
    notifier: Notifier = LoggingNotifier()
    if settings.telegram_bot_token:
        # The bot delegates inbound updates to a TelegramUpdateHandler; the interactive
        # FR-6→8 workflow (TR-2 slice 2) will implement it. Until then it just logs.
        bot = ExpenseBot.build(settings.telegram_bot_token, LoggingUpdateHandler())
        if settings.telegram_chat_id is not None:
            notifier = TelegramNotifier(bot, settings.telegram_chat_id)
        else:
            logger.warning(
                "Telegram token set but EXPENSES_TELEGRAM_CHAT_ID is not — "
                "notifications will be logged, not sent. Send /start to the bot to learn it."
            )

    # --- Processor (TR-2, automatic path) ---
    processor = TransactionProcessor(
        engine, sheets, state, notifier, LoggingUnknownHandler()
    )

    # --- Poller (TR-1) feeds the Processor; State is its early idempotency guard ---
    poller = TransactionPoller(
        gateway,
        state,
        processor,
        account_uid=settings.eb_account_uid,
        lookback_days=settings.poll_lookback_days,
        transaction_status=settings.eb_transaction_status,
    )

    # --- Scheduler (TR-1 DD-1): internal asyncio loop, consent-expiry aware ---
    cycle = PollCycle(poller, notifier)
    scheduler = IntervalScheduler(cycle, settings.poll_interval_seconds)

    return Components(
        settings=settings,
        http_client=http_client,
        sheets=sheets,
        cache=cache,
        engine=engine,
        state=state,
        processor=processor,
        poller=poller,
        scheduler=scheduler,
        bot=bot,
    )
