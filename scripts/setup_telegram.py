"""
Setup script for Telethon session.

Run this ONCE to create a Telegram session file.
Usage:
    python scripts/setup_telegram.py
"""

import asyncio
from pathlib import Path
from telethon import TelegramClient


async def setup():
    print("=" * 50)
    print("Telegram Session Setup")
    print("=" * 50)

    api_id = input("Enter your TELEGRAM_API_ID (from my.telegram.org): ").strip()
    api_hash = input("Enter your TELEGRAM_API_HASH: ").strip()

    if not api_id or not api_hash:
        print("Error: api_id and api_hash are required.")
        print("Get them at: https://my.telegram.org/apps")
        return

    session_dir = Path("./sessions")
    session_dir.mkdir(parents=True, exist_ok=True)
    session_path = str(session_dir / "ingesta")

    client = TelegramClient(session_path, int(api_id), api_hash)

    try:
        await client.start()
        me = await client.get_me()
        print(f"\nConnected as: {me.phone or me.username or me.id}")

        # Test reading from STEMJobsLATAM
        print("\nTesting read from STEMJobsLATAM...")
        count = 0
        async for msg in client.iter_messages("STEMJobsLATAM", limit=5):
            if msg.text:
                count += 1
                print(f"  - [{msg.id}] {msg.text[:80]}...")

        print(f"\nSuccess! Session saved at: {session_path}.session")
        print(f"Read {count} messages from STEMJobsLATAM.")
        print("\nYou can now start the microservice.")

    except Exception as e:
        print(f"\nError: {e}")
        print("\nTroubleshooting:")
        print("  1. Make sure api_id and api_hash are correct")
        print("  2. Check your phone number can access Telegram")
        print("  3. If 2FA is enabled, you'll be prompted for a password")
    finally:
        await client.disconnect()


if __name__ == "__main__":
    asyncio.run(setup())
