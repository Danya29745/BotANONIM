from aiogram import Router, Bot, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import BOT_USERNAME, ADMIN_ID, WELCOME_PHOTO

router = Router()


class AskState(StatesGroup):
    waiting_question = State()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

async def check_subscriptions(bot: Bot, user_id: int) -> list[dict]:
    """Returns list of channels user is NOT subscribed to."""
    channels = db.get_all_channels()
    not_subbed = []
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch["channel_id"], user_id)
            if member.status in ("left", "kicked", "banned"):
                not_subbed.append(ch)
            else:
                db.record_sub(user_id, ch["channel_id"])
        except Exception:
            not_subbed.append(ch)
    return not_subbed


def sub_keyboard(channels: list[dict], token: str = "") -> InlineKeyboardMarkup:
    buttons = []
    for ch in channels:
        buttons.append([InlineKeyboardButton(
            text=f"📢 {ch['title']}",
            url=ch["invite_link"]
        )])
    check_data = f"check_sub:{token}" if token else "check_sub:"
    buttons.append([InlineKeyboardButton(text="✅ Я подписался", callback_data=check_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def my_link_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔗 Моя ссылка", url=f"https://t.me/{BOT_USERNAME}?start={token}")
    ]])


# ─── /start ───────────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name or ""

    args = message.text.split(maxsplit=1)
    token_arg = args[1].strip() if len(args) > 1 else None

    # Register user
    user_data = db.get_or_create_user(user_id, username, full_name)

    # Check sponsor subscriptions
    not_subbed = await check_subscriptions(bot, user_id)
    if not_subbed:
        payload = token_arg or ""
        await message.answer(
            "👋 Добро пожаловать в <b>WhisperLink</b>!\n\n"
            "Чтобы пользоваться ботом, подпишись на наших спонсоров:",
            reply_markup=sub_keyboard(not_subbed, payload),
            parse_mode="HTML"
        )
        return

    # Came via someone's link — ask a question
    if token_arg and token_arg != user_data["link_token"]:
        owner = db.get_user_by_token(token_arg)
        if owner:
            await state.set_state(AskState.waiting_question)
            await state.update_data(owner_id=owner["user_id"], asker_id=user_id)
            name = owner.get("full_name") or "этого человека"
            await message.answer(
                f"🤫 Ты перешёл по ссылке пользователя <b>{name}</b>.\n\n"
                "Напиши своё анонимное сообщение — владелец не узнает, кто ты:",
                parse_mode="HTML"
            )
            return
        else:
            await message.answer("❌ Ссылка недействительна.")

    # Regular /start — show own link
    token = user_data["link_token"]
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    text = (
        f"👋 Привет, <b>{full_name}</b>!\n\n"
        f"Вот твоя личная ссылка для анонимных вопросов:\n\n"
        f"🔗 <code>{link}</code>\n\n"
        f"Поделись ею с друзьями — они смогут отправить тебе анонимные сообщения!\n\n"
        f"<i>Ответить на вопрос можно прямо в чате — нажми «Ответить» на нужном сообщении.</i>"
    )
    if WELCOME_PHOTO:
        await message.answer_photo(
            photo=WELCOME_PHOTO,
            caption=text,
            parse_mode="HTML",
            reply_markup=my_link_keyboard(token)
        )
    else:
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=my_link_keyboard(token)
        )


# ─── Check subscription callback ──────────────────────────────────────────────

@router.callback_query(F.data.startswith("check_sub:"))
async def callback_check_sub(call: CallbackQuery, bot: Bot, state: FSMContext):
    await call.answer()
    user_id = call.from_user.id
    token_arg = call.data.split(":", 1)[1] or None

    not_subbed = await check_subscriptions(bot, user_id)
    if not_subbed:
        await call.message.edit_reply_markup(reply_markup=sub_keyboard(not_subbed, token_arg or ""))
        await call.message.answer("❗ Ты ещё не подписался на все каналы. Подпишись и нажми кнопку снова.")
        return

    # Subscribed — redirect
    user_data = db.get_or_create_user(
        user_id,
        call.from_user.username or "",
        call.from_user.full_name or ""
    )

    if token_arg and token_arg != user_data["link_token"]:
        owner = db.get_user_by_token(token_arg)
        if owner:
            await state.set_state(AskState.waiting_question)
            await state.update_data(owner_id=owner["user_id"], asker_id=user_id)
            name = owner.get("full_name") or "этого человека"
            await call.message.answer(
                f"🤫 Ты перешёл по ссылке пользователя <b>{name}</b>.\n\n"
                "Напиши своё анонимное сообщение:",
                parse_mode="HTML"
            )
            return

    token = user_data["link_token"]
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    await call.message.answer(
        f"✅ Подписка подтверждена!\n\n"
        f"Вот твоя личная ссылка:\n🔗 <code>{link}</code>",
        parse_mode="HTML",
        reply_markup=my_link_keyboard(token)
    )


# ─── Receive anonymous question ───────────────────────────────────────────────

@router.message(AskState.waiting_question)
async def receive_question(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    owner_id = data["owner_id"]
    asker_id = data["asker_id"]

    text = message.text or message.caption or ""
    if not text:
        await message.answer("❗ Пожалуйста, отправь текстовое сообщение.")
        return

    qid = db.save_question(owner_id, asker_id, text)
    await state.clear()

    # Forward to owner
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"reply:{qid}")
    ]])
    await bot.send_message(
        owner_id,
        f"📩 <b>Новый анонимный вопрос #{qid}</b>\n\n{text}",
        parse_mode="HTML",
        reply_markup=kb
    )

    await message.answer("✅ Твой вопрос отправлен анонимно! Ответ придёт сюда, если владелец ответит.")
