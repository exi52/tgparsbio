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
scrape_lock = asyncio.Lock()


def make_tele_clients():
    clients = []
    for idx, session in enumerate(config.TG_SESSIONS, 1):
        try:
            clients.append(
                TelegramClient(StringSession(session), config.API_ID, config.API_HASH)
            )
        except Exception as exc:
            preview = f"{session[:6]}...{session[-6:]}" if len(session) > 12 else session
            raise RuntimeError(
                f"TG_SESSIONS item #{idx} is not a valid Telethon StringSession. "
                f"Length={len(session)}, preview={preview!r}. "
                "Regenerate it with gen_session.py and paste only the full output line."
            ) from exc
    return clients


tele_clients = make_tele_clients()


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
        "Аккаунты сами зайдут, спарсят и выйдут:\n\n"
        "@durov_chat\n"
        "t.me/another_chat\n"
        "t.me/+AbCdEf... (приватный инвайт)\n\n"
        "Отбираю тех, у кого в bio есть twitter.com, x.com или linktr.ee, "
        "и отдаю txt по каждому чату. Дубли между чатами не повторяю."
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

            active_clients = []
            active_entities = []
            joined_refs = []

            for account_idx, client in enumerate(tele_clients, 1):
                try:
                    entity, joined = await resolve_target(client, target)
                    active_clients.append(client)
                    active_entities.append(entity)
                    if joined:
                        joined_refs.append((client, entity))
                except Exception as exc:
                    log.warning("Account #%s cannot open %s: %s", account_idx, target, exc)

            if not active_clients:
                await _safe_edit(status, f"{prefix}\nНи один аккаунт не смог открыть этот чат.")
                await _batch_pause(idx, total_chats)
                continue

            await _safe_edit(status, f"{prefix}\nЗашёл. Собираю участников...")
            await asyncio.sleep(4)

            try:
                results, total = await scrape(
                    active_clients,
                    active_entities,
                    progress_cb=make_progress(status, prefix),
                    min_delay=config.MIN_DELAY,
                    max_delay=config.MAX_DELAY,
                )
            except Exception as exc:
                await _safe_edit(status, f"{prefix}\nОшибка: {exc}")
                if config.AUTO_LEAVE:
                    for client, joined_entity in joined_refs:
                        await leave_chat(client, joined_entity)
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

            if config.AUTO_LEAVE:
                for client, joined_entity in joined_refs:
                    await leave_chat(client, joined_entity)

            await _batch_pause(idx, total_chats)

        await message.answer(f"Очередь закончилась. Всего лидов: {total_leads}.")


async def main():
    for idx, client in enumerate(tele_clients, 1):
        await client.connect()
        if not await client.is_user_authorized():
            raise RuntimeError(f"TG_SESSION #{idx} is invalid. Regenerate it with gen_session.py.")
        me = await client.get_me()
        log.info("Telethon account #%s active: %s", idx, me.username or me.id)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
