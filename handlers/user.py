from aiogram import Router, Bot, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, LabeledPrice, PreCheckoutQuery,
    ReplyKeyboardMarkup, KeyboardButton
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import BOT_USERNAME, ADMIN_ID, WELCOME_PHOTO

router = Router()

REVEAL_PRICE = 299  # Telegram Stars


class AskState(StatesGroup):
    waiting_question = State()


# ─── HELPERS ──────────────────────────────────────────────────────────────────

async def check_subscriptions(bot: Bot, user_id: int) -> list[dict]:
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


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔗 Моя анонимка — поделиться ссылкой")]],
        resize_keyboard=True,
        one_time_keyboard=False
    )


def question_keyboard(qid: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✉️ Ответить", callback_data=f"reply:{qid}"),
        InlineKeyboardButton(text="🕵️ Узнать автора", callback_data=f"reveal:{qid}"),
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

    user_data = db.get_or_create_user(user_id, username, full_name)

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

    token = user_data["link_token"]
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    text = (
        "👋 <b>Привет!</b> Добро пожаловать в <b>WhisperLink</b> — место, где говорят правду.\n\n"
        "🤫 Здесь тебе могут написать анонимно — никто не узнает кто это был.\n"
        "💌 Делись ссылкой, собирай вопросы, отвечай на них.\n\n"
        "🔗 <b>Твоя личная ссылка:</b>\n"
        f"<blockquote>{link}</blockquote>\n"
        "Поделись ею — и пусть начнётся!\n\n"
        "<i>💡 Команды: /mystats — твоя статистика, /link — обновить ссылку</i>"
    )
    if WELCOME_PHOTO:
        await message.answer_photo(
            photo=WELCOME_PHOTO,
            caption=text,
            parse_mode="HTML",
            reply_markup=my_link_keyboard(token)
        )
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=my_link_keyboard(token))

    await message.answer(
        "👇 Кнопка ниже всегда под рукой — нажми чтобы получить свою ссылку.",
        reply_markup=main_keyboard()
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

    # Deanon mode: show asker identity if enabled
    deanon = db.get_deanon_mode(owner_id)
    if deanon and asker_id:
        asker = db.get_user_by_id(asker_id)
        if asker:
            a_name = asker.get("full_name") or "Без имени"
            a_uname = f" (@{asker['username']})" if asker.get("username") else ""
            deanon_line = f"\n\n👤 <b>Отправитель:</b> {a_name}{a_uname}"
        else:
            deanon_line = ""
    else:
        deanon_line = ""

    await bot.send_message(
        owner_id,
        f"📩 <b>Новый анонимный вопрос #{qid}</b>\n\n{text}{deanon_line}",
        parse_mode="HTML",
        reply_markup=question_keyboard(qid)
    )

    await message.answer("✅ Твой вопрос отправлен анонимно! Ответ придёт сюда, если владелец ответит.")


# ─── Кнопка "Моя анонимка" ────────────────────────────────────────────────────

@router.message(F.text == "🔗 Моя анонимка — поделиться ссылкой")
async def btn_my_link(message: Message):
    user_id = message.from_user.id
    user_data = db.get_user_by_id(user_id)
    if not user_data:
        await message.answer("❌ Сначала отправь /start.")
        return
    token = user_data["link_token"]
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    await message.answer(
        f"🔗 Вот твоя личная ссылка для анонимных вопросов:\n\n"
        f"<code>{link}</code>\n\n"
        f"📲 Скопируй и поделись с друзьями — пусть пишут!",
        parse_mode="HTML",
        reply_markup=my_link_keyboard(token)
    )


# ─── /mystats ─────────────────────────────────────────────────────────────────

@router.message(Command("mystats"))
async def cmd_mystats(message: Message):
    user_id = message.from_user.id
    stats = db.get_user_stats(user_id)
    user_data = db.get_user_by_id(user_id)
    if not user_data:
        await message.answer("❌ Сначала отправь /start.")
        return

    unanswered = stats["received"] - stats["answered"]
    await message.answer(
        "📊 <b>Твоя статистика</b>\n\n"
        f"📥 Получено вопросов: <b>{stats['received']}</b>\n"
        f"✅ Отвечено: <b>{stats['answered']}</b>\n"
        f"⏳ Без ответа: <b>{unanswered}</b>\n"
        f"📤 Отправлено анонимок: <b>{stats['sent']}</b>",
        parse_mode="HTML"
    )


# ─── /link ────────────────────────────────────────────────────────────────────

@router.message(Command("link"))
async def cmd_link(message: Message):
    user_id = message.from_user.id
    user_data = db.get_user_by_id(user_id)
    if not user_data:
        await message.answer("❌ Сначала отправь /start.")
        return
    token = user_data["link_token"]
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    await message.answer(
        "🔗 <b>Твоя ссылка для анонимных вопросов:</b>\n\n"
        f"<blockquote>{link}</blockquote>\n"
        "Поделись ею с друзьями!",
        parse_mode="HTML",
        reply_markup=my_link_keyboard(token)
    )


# ─── /qs — deanon mode toggle ─────────────────────────────────────────────────

@router.message(Command("qs"))
async def cmd_qs(message: Message):
    user_id = message.from_user.id

    current = db.get_deanon_mode(user_id)
    new_state = not current
    db.set_deanon_mode(user_id, new_state)

    if not new_state:
        await message.answer(
            "🔒 <b>Режим деанона ВЫКЛЮЧЕН.</b>\n\n"
            "Теперь новые вопросы будут приходить без информации об отправителе.",
            parse_mode="HTML"
        )
        return

    await message.answer(
        "🔓 <b>Режим деанона ВКЛЮЧЁН.</b>\n\n"
        "Теперь при каждом новом вопросе ты увидишь, кто его задал. "
        "Отправители по-прежнему думают, что анонимны.\n\n"
        "Чтобы выключить — отправь /qs ещё раз.",
        parse_mode="HTML"
    )

    questions = db.get_questions_for_owner(user_id, limit=10)

    if not questions:
        await message.answer("📭 Вопросов пока нет — но как только появятся, ты сразу узнаешь кто.")
        return

    lines = ["👁 <b>Последние вопросы — личности раскрыты:</b>\n"]
    for q in questions:
        asker = db.get_user_by_id(q["asker_id"]) if q["asker_id"] else None
        if asker:
            name = asker.get("full_name") or "Без имени"
            uname = f" (@{asker['username']})" if asker.get("username") else ""
            asker_str = f"{name}{uname}"
        else:
            asker_str = "Удалённый аккаунт"

        answered = "✅" if q["answer_text"] else "⏳"
        lines.append(
            f"{answered} <b>#{q['id']}</b> — <b>{asker_str}</b>\n"
            f"<i>{q['question_text'][:80]}{'...' if len(q['question_text']) > 80 else ''}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Reveal identity — send invoice ───────────────────────────────────────────

@router.callback_query(F.data.startswith("reveal:"))
async def cb_reveal(call: CallbackQuery, bot: Bot):
    await call.answer()
    qid = int(call.data.split(":")[1])
    question = db.get_question(qid)

    if not question:
        await call.message.answer("❌ Вопрос не найден.")
        return

    if question["owner_id"] != call.from_user.id:
        await call.message.answer("⛔ Это не твой вопрос.")
        return

    if question["identity_revealed"]:
        asker = db.get_user_by_id(question["asker_id"]) if question["asker_id"] else None
        if asker:
            name = asker.get("full_name") or "Неизвестно"
            uname = f" @{asker['username']}" if asker.get("username") else ""
            await call.message.answer(
                f"ℹ️ Автор вопроса #{qid}: <b>{name}</b>{uname}",
                parse_mode="HTML"
            )
        return

    await bot.send_invoice(
        chat_id=call.from_user.id,
        title="🕵️ Узнать автора вопроса",
        description=f"Раскрыть личность автора анонимного вопроса #{qid}",
        payload=f"reveal_identity:{qid}",
        currency="XTR",
        prices=[LabeledPrice(label="Звёзды", amount=REVEAL_PRICE)],
        provider_token=""
    )


# ─── Pre-checkout ──────────────────────────────────────────────────────────────

@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


# ─── Successful payment ───────────────────────────────────────────────────────

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    payload = message.successful_payment.invoice_payload

    if payload.startswith("reveal_identity:"):
        qid = int(payload.split(":")[1])
        question = db.get_question(qid)

        if question and question["asker_id"]:
            db.mark_identity_revealed(qid)
            asker = db.get_user_by_id(question["asker_id"])
            if asker:
                name = asker.get("full_name") or "Неизвестно"
                uname = f" @{asker['username']}" if asker.get("username") else ""
                tg_link = f' <a href="tg://user?id={asker["user_id"]}">открыть профиль</a>'
                await message.answer(
                    f"✅ Оплата прошла!\n\n"
                    f"🕵️ Автор вопроса <b>#{qid}</b>:\n"
                    f"<b>{name}</b>{uname}\n{tg_link}",
                    parse_mode="HTML"
                )
