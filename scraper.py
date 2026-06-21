import asyncio
import random
import re

from openpyxl import Workbook
from telethon.errors import (
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
)
from telethon.tl.functions.channels import JoinChannelRequest, LeaveChannelRequest
from telethon.tl.functions.messages import (
    CheckChatInviteRequest,
    DeleteChatUserRequest,
    ImportChatInviteRequest,
)
from telethon.tl.functions.users import GetFullUserRequest

TW_RE = re.compile(r"(?:https?://)?(?:www\.)?(?:twitter\.com|x\.com)/[A-Za-z0-9_]+/?", re.I)
LT_RE = re.compile(r"(?:https?://)?(?:www\.)?linktr\.ee/[A-Za-z0-9_.\-]+/?", re.I)
INVITE_RE = re.compile(r"(?:t\.me/joinchat/|t\.me/\+|(?:^|\s)\+)([A-Za-z0-9_\-]+)", re.I)
ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def parse_invite_hash(target):
    match = INVITE_RE.search(target)
    return match.group(1) if match else None


async def _join_private(client, invite_hash):
    try:
        updates = await client(ImportChatInviteRequest(invite_hash))
        return updates.chats[0], True
    except UserAlreadyParticipantError:
        info = await client(CheckChatInviteRequest(invite_hash))
        return info.chat, False
    except (InviteHashExpiredError, InviteHashInvalidError):
        raise RuntimeError("Инвайт-ссылка недействительна или истекла.")


async def _join_public(client, target):
    entity = await client.get_entity(target)
    joined = False
    try:
        await client(JoinChannelRequest(entity))
        joined = True
    except UserAlreadyParticipantError:
        joined = False
    except Exception:
        joined = False
    return entity, joined


async def resolve_target(client, target):
    """Возвращает (entity, joined). joined=True только если вступили в этом прогоне."""
    invite_hash = parse_invite_hash(target)
    if invite_hash:
        return await _join_private(client, invite_hash)
    return await _join_public(client, target)


async def leave_chat(client, entity):
    try:
        await client(LeaveChannelRequest(entity))
        return True
    except Exception:
        pass
    try:
        await client(DeleteChatUserRequest(chat_id=entity.id, user_id="me"))
        return True
    except Exception:
        return False


def extract_links(bio):
    if not bio:
        return {"twitter": [], "linktree": []}
    return {
        "twitter": list(dict.fromkeys(TW_RE.findall(bio))),
        "linktree": list(dict.fromkeys(LT_RE.findall(bio))),
    }


def _clean(value):
    if isinstance(value, str):
        return ILLEGAL.sub("", value)
    return value


async def _collect_members(client, entity):
    members = []
    async for user in client.iter_participants(entity, aggressive=True):
        if user.bot or user.deleted:
            continue
        members.append(user)
    return members


async def scrape(client, entity, progress_cb=None, min_delay=0.6, max_delay=1.4):
    members = await _collect_members(client, entity)
    total = len(members)
    results = []

    for i, user in enumerate(members, 1):
        bio = ""
        while True:
            try:
                full = await client(GetFullUserRequest(user.id))
                bio = full.full_user.about or ""
                break
            except FloodWaitError as exc:
                if progress_cb:
                    await progress_cb(i, total, flood_wait=exc.seconds + 2)
                await asyncio.sleep(exc.seconds + 2)
            except Exception:
                break

        links = extract_links(bio)
        if links["twitter"] or links["linktree"]:
            results.append(
                {
                    "user_id": user.id,
                    "username": user.username or "",
                    "first_name": user.first_name or "",
                    "last_name": user.last_name or "",
                    "bio": bio,
                    "twitter": links["twitter"],
                    "linktree": links["linktree"],
                }
            )

        if progress_cb and i % 25 == 0:
            await progress_cb(i, total)
        await asyncio.sleep(random.uniform(min_delay, max_delay))

    return results, total


def leads_lines(results):
    lines = []
    for r in results:
        handle = "@" + r["username"] if r["username"] else f"id{r['user_id']}"
        links = " ".join(r["twitter"] + r["linktree"])
        lines.append(f"{handle} | {links}")
    return lines


def export_txt(results, path):
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(leads_lines(results)))


def export_xlsx(results, path):
    wb = Workbook()
    ws = wb.active
    ws.title = "leads"
    ws.append(["user_id", "username", "first_name", "last_name", "bio", "twitter", "linktree"])
    for r in results:
        ws.append(
            [
                r["user_id"],
                _clean(r["username"]),
                _clean(r["first_name"]),
                _clean(r["last_name"]),
                _clean(r["bio"]),
                _clean(" ".join(r["twitter"])),
                _clean(" ".join(r["linktree"])),
            ]
        )
    wb.save(path)
