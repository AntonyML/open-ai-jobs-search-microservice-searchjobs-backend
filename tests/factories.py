"""Test doubles y constructores de datos para la suite.

Dónde vive cada cosa:
- TelegramMessage / FakeTelegram: sustitutos del frente externo Telegram
  (Telethón). Es la única dependencia externa costosa/no determinista.
- make_job_posting: constructor de un JobPosting válido para sembrar la DB.
- FakeOrchestrator: sustituto del orquestador en tests de contrato HTTP (e2e),
  donde la frontera mockeada es el servicio, no la DB.
"""

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from app.models import JobPosting


@dataclass
class TelegramMessage:
    """Subconjunto mínimo de un mensaje de Telethón que usan los parsers."""

    id: int
    text: str


def make_message(text: str, msg_id: int) -> TelegramMessage:
    return TelegramMessage(id=msg_id, text=text)


def make_job_posting(**overrides) -> JobPosting:
    """JobPosting válido con valores por defecto; override por campo."""
    now = datetime.now(timezone.utc)
    defaults = dict(
        title="Software Engineer",
        company="Test Corp",
        location="Remote",
        url=None,
        description="Descripción",
        salary=None,
        portal="telegram",
        category_id="stem_cr",
        source_channel="test_channel",
        source_message_id=1,
        raw_text="Mensaje crudo",
        ingested_at=now,
        expires_at=now + timedelta(hours=72),
        dedup_hash=None,
    )
    defaults.update(overrides)
    return JobPosting(**defaults)


class FakeTelegram:
    """Sustituto de TelegramFetcher: respuestas guionadas por canal.

    - messages_by_channel: dict channel -> list[TelegramMessage]
    - default_messages: lista usada para canales sin entrada
    - errors: dict channel -> Exception (get_messages lanza para ese canal)
    - calls: registra (channel, limit) de cada get_messages que se ejecuta
    """

    def __init__(
        self,
        messages_by_channel: dict | None = None,
        default_messages: list | None = None,
        errors: dict | None = None,
    ):
        self.messages_by_channel = messages_by_channel or {}
        self.default_messages = default_messages or []
        self.errors = errors or {}
        self.calls: list[tuple[str, int]] = []

    async def start(self):
        pass

    async def stop(self):
        pass

    async def get_messages(self, channel: str, limit: int = 50):
        self.calls.append((channel, limit))
        if channel in self.errors:
            raise self.errors[channel]
        return self.messages_by_channel.get(channel, self.default_messages)


class FakeOrchestrator:
    """Sustituto del IngestOrchestrator para pruebas de contrato HTTP.

    Registra las llamadas a run_ingest y (opcionalmente) marca el job como
    hecho en la DB de test, para verificar que el background task se ejecutó.
    """

    def __init__(self, session_factory=None):
        self.session_factory = session_factory
        self.calls: list[tuple[str, str]] = []

    async def run_ingest(self, ingest_job_id: str, category_id: str):
        from sqlalchemy import select

        from app.models import IngestJob

        self.calls.append((ingest_job_id, category_id))
        if self.session_factory is None:
            return
        async with self.session_factory() as db:
            result = await db.execute(
                select(IngestJob).where(IngestJob.id == ingest_job_id)
            )
            job = result.scalar_one_or_none()
            if job:
                job.status = "done"
                job.result_count = 0
                job.completed_at = datetime.now(timezone.utc)
                await db.commit()