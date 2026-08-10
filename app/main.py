import asyncio
import structlog
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import init_db, close_db
from app.telegram import TelegramFetcher
from app.ingestion import IngestOrchestrator
from app.routes import router, setup_routes
from app.ttl import clean_expired_jobs


def setup_structlog():
    """Configure structlog for structured logging."""
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.dev.ConsoleRenderer(),  # Pretty console output
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


# Initialize structlog before anything else
setup_structlog()

logger = structlog.get_logger(__name__)

telegram = TelegramFetcher(
    api_id=settings.telegram_api_id,
    api_hash=settings.telegram_api_hash,
    session_dir=settings.telegram_session_dir,
)
orchestrator = IngestOrchestrator(telegram)


async def ttl_loop():
    while True:
        await asyncio.sleep(settings.ttl_cleanup_interval_minutes * 60)
        try:
            # Referencia viva: init_db() reasigna app.database.async_session_maker
            # después del import de este módulo, por lo que hay que leerla por
            # ciclo y no capturarla a nivel de módulo (donde siempre es None).
            from app.database import async_session_maker
            if async_session_maker:
                async with async_session_maker() as db:
                    await clean_expired_jobs(db, settings.job_ttl_hours)
        except Exception:
            logger.exception("ttl_cleanup_failed")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("microservice_starting")
    await init_db(settings.database_url)

    if settings.telegram_api_id and settings.telegram_api_hash:
        await telegram.start()
    else:
        logger.warning(
            "telegram_not_configured",
            message="Set TELEGRAM_API_ID and TELEGRAM_API_HASH.",
        )

    ttl_task = asyncio.create_task(ttl_loop())
    logger.info("microservice_ready")

    yield

    ttl_task.cancel()
    await telegram.stop()
    await close_db()
    logger.info("microservice_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Jobs Ingest Microservice",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    setup_routes(orchestrator)
    app.include_router(router, prefix="/api/v1")
    return app


app = create_app()
