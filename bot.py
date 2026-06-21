import asyncio
import logging
import os
import random
import re
import tempfile
import time

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandObject
from aiogram.types import FSInputFile, LinkPreviewOptions, Message
from telethon import TelegramClient
from telethon.sessions import StringSession

import config
from scraper import export_txt, leads_lines, leave_chat, resolve_target, scrape

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("bio-parser")

bot = Bot(config.BOT_TOKEN)
dp = Dispatcher()
tele = TelegramClient(StringSession(config.TG_SESSION), config.API_ID, config.API_HASH)
scrape_lock = asyncio.Lock()


def authorized(uid):
    return not config.ALLOWED_USERS or uid in config.ALLOWED_USERS


def parse_targets(text):
    parts = re.split(r"[\s,]+", text.strip())
    return [p for p in parts if p]


async def _safe_edit(msg, text):
    try:
        await msg.edit_text(text)
    except Exception:
        pass


def make_progress(status, prefix):
    state = {"last": 0.0}

    async def progress(done, total, flood_wait=None):
        now = time.monotonic()
        if flood_wait:
            await _safe_edit(status, f"{prefix}\nFloodWait {flood_wait} сек. {done}/{total}.")
            state["last"] = now
            return
        if now - state["last"] < 3:
            return
        state["last"] = now
        await _safe_edit(status, f"{prefix}\nЧитаю bio: {done}/{total}")

    return progress


async def _batch_pause(idx, total):
    if idx >= total:
        return
    delay = random.uniform(config.BATCH_MIN_DELAY, config.BATCH_MAX_DELAY)
    await asyncio.sleep(delay)


def _chunk_text(lines, limit=3500):
    chunks, buf = [], ""
    for line in lines:
        candidate = f"{buf}\n{line}" if buf else line
        if len(candidate) > limit:
            if buf:
                chunks.append(buf)
            buf = line
        else:
            buf = candidate
    if buf:
        chunks.append(buf)
    return chunks


@dp.message(Command("start"))
async def start(message: Message):
    if not authorized(message.from_user.id):
        await message.answer("Доступ закрыт.")
        return
    await message.answer(
        "Парсер участников по bio.\n\n"
        "Кидай один или несколько чатов, каждый с новой строки. "
        "Аккаунт сам зайдёт, спарсит и выйдет:\n\n"
        "@durov_chat\n"
        "t.me/another_chat\n"
        "t.me/+AbCdEf... (приватный инвайт)\n\n"
        "Отбираю тех, у кого в bio есть twitter.com, x.com или linktr.ee, "
        "и отдаю xlsx по каждому чату. Дубли между чатами не повторяю."
    )


@dp.message(Command("scrape"))
async def scrape_cmd(message: Message, command: CommandObject):
    await run_scrape(message, command.args or "")


@dp.message(F.text & ~F.text.startswith("/"))
async def scrape_plain(message: Message):
    await run_scrape(message, message.text)


async def run_scrape(message: Message, raw):
    if not authorized(message.from_user.id):
        await message.answer("Доступ закрыт.")
        return
    targets = parse_targets(raw)
    if not targets:
        await message.answer("Дай хотя бы один чат.")
        return
    if scrape_lock.locked():
        await message.answer("Уже идёт парсинг. Дождись завершения.")
        return

    async with scrape_lock:
        seen_ids = set()
        total_chats = len(targets)
        total_leads = 0

        for idx, target in enumerate(targets, 1):
            prefix = f"[{idx}/{total_chats}] {target}"
            status = await message.answer(f"{prefix}\nЗахожу в чат...")

            try:
                entity, joined = await resolve_target(tele, target)
            except Exception as exc:
                await _safe_edit(status, f"{prefix}\nНе зашёл: {exc}")
                await _batch_pause(idx, total_chats)
                continue

            await _safe_edit(status, f"{prefix}\nЗашёл. Собираю участников...")
            await asyncio.sleep(4)

            try:
                results, total = await scrape(
                    tele,
                    entity,
                    progress_cb=make_progress(status, prefix),
                    min_delay=config.MIN_DELAY,
                    max_delay=config.MAX_DELAY,
                )
            except Exception as exc:
                await _safe_edit(status, f"{prefix}\nОшибка: {exc}")
                if config.AUTO_LEAVE and joined:
                    await leave_chat(tele, entity)
                await _batch_pause(idx, total_chats)
                continue

            new = [r for r in results if r["user_id"] not in seen_ids]
            for r in new:
                seen_ids.add(r["user_id"])
            total_leads += len(new)

            if new:
                txt_path = os.path.join(
                    tempfile.gettempdir(), f"leads_{message.from_user.id}_{idx}.txt"
                )
                export_txt(new, txt_path)
                await _safe_edit(status, f"{prefix}\nГотово. {len(new)} новых из {total}.")
                await message.answer_document(
                    FSInputFile(txt_path), caption=f"{target}: {len(new)} лидов"
                )
                for chunk in _chunk_text(leads_lines(new)):
                    await message.answer(
                        chunk, link_preview_options=LinkPreviewOptions(is_disabled=True)
                    )
                try:
                    os.remove(txt_path)
                except OSError:
                    pass
            else:
                await _safe_edit(status, f"{prefix}\nГотово. Новых нет (просмотрено {total}).")

            if config.AUTO_LEAVE and joined:
                await leave_chat(tele, entity)

            await _batch_pause(idx, total_chats)

        await message.answer(f"Очередь закончилась. Всего лидов: {total_leads}.")


async def main():
    await tele.connect()
    if not await tele.is_user_authorized():
        raise RuntimeError("TG_SESSION недействителен. Перегенерируй через gen_session.py.")
    me = await tele.get_me()
    log.info("Telethon active: %s", me.username or me.id)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
