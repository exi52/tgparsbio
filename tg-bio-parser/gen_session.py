"""Запусти локально один раз, чтобы получить строку сессии.
   python gen_session.py
   Вставь вывод в Railway как TG_SESSION."""

import asyncio

from telethon import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("API_ID: ").strip())
api_hash = input("API_HASH: ").strip()


async def main():
    async with TelegramClient(StringSession(), api_id, api_hash) as client:
        print("\nВставь это в Railway как TG_SESSION:\n")
        print(client.session.save())


if __name__ == "__main__":
    asyncio.run(main())
