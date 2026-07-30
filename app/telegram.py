import asyncio
import logging
from pathlib import Path
from telethon import TelegramClient
from telethon.errors import FloodWaitError

logger = logging.getLogger(__name__)


class TelegramFetcher:
    def __init__(self, api_id: int, api_hash: str, session_dir: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_dir = Path(session_dir)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self._client: TelegramClient | None = None

    async def start(self):
        session_path = str(self.session_dir / "ingesta")
        self._client = TelegramClient(session_path, self.api_id, self.api_hash)
        await self._client.start()
        me = await self._client.get_me()
        logger.info("Telethon connected as %s", me.phone or me.username or me.id)

    async def get_messages(self, channel: str, limit: int = 50):
        if not self._client:
            raise RuntimeError("Telegram client not started. Call start() first.")
        messages = []
        try:
            async for msg in self._client.iter_messages(channel, limit=limit):
                if msg.text:
                    messages.append(msg)
        except FloodWaitError as e:
            logger.warning("Flood wait on %s: %s seconds", channel, e.seconds)
            await asyncio.sleep(e.seconds)
        except ValueError as e:
            logger.error("Channel %s not accessible: %s", channel, e)
            raise
        return messages

    async def stop(self):
        if self._client:
            await self._client.disconnect()
            logger.info("Telethon disconnected")
