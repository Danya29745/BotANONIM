from aiogram import Router, Bot, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
import asyncio

import database as db
from config import ADMIN_ID

router = Router()


def is_admin(user_id: int) -> bool:
    return user_id == ADMIN_ID


# ─── STATES ───────────────────────────────────────────────────────────────────

class AdminStates(StatesGroup):
    broadcast_text = State()
    add_channel_id = State()
    add_channel_title = State()
    add_channel_link = State()


# ─── KEYBOARDS ────────────────────────────────────────────────────────────────

def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin:stats")],
        [InlineKeyboardButton(text="📣 Рассылка", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="📢 Каналы", callback_data="admin:channels")],
    ])


def channels_kb(channels: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for ch in channels:
        subs = db.count_subs(ch["channel_id"])
        rows.append([InlineKeyboardButton(
            text=f"❌ {ch['title']} ({subs} подп.)",
            callback_data=f"admin:del_channel:{ch['channel_id']}"
        )])
    rows.append([InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin:add_channel")])
    rows.append([InlineKeyboardButton(text="🔙 Назад", callback_data="admin:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def back_kb(target: str = "admin:menu") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔙 Назад", callback_data=target)
    ]])


# ─── /admin command ───────────────────────────────────────────────────────────

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await message.answer("⛔ У вас нет доступа.")
        return
    await state.clear()
    await message.answer(
        "🛠 <b>Панель администратора</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=admin_menu_kb()
    )


# ─── Menu navigation ──────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:menu")
async def cb_admin_menu(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔")
        return
    await state.clear()
    await call.message.edit_text(
        "🛠 <b>Панель администратора</b>\n\nВыберите действие:",
        parse_mode="HTML",
        reply_markup=admin_menu_kb()
    )


# ─── Stats ────────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:stats")
async def cb_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔")
        return
    await call.answer()

    users = db.count_users()
    questions = db.count_questions()
    answers = db.count_answers()

    text = (
        "📊 <b>Статистика бота</b>\n\n"
        f"👥 Пользователей: <b>{users}</b>\n"
        f"❓ Всего вопросов: <b>{questions}</b>\n"
        f"✅ Отвечено: <b>{answers}</b>"
    )
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=back_kb())


# ─── Broadcast ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:broadcast")
async def cb_broadcast(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔")
        return
    await call.answer()
    await state.set_state(AdminStates.broadcast_text)
    await call.message.edit_text(
        "📣 <b>Рассылка</b>\n\nНапиши сообщение, которое получат все пользователи бота.\n\n"
        "<i>Поддерживается HTML-форматирование.</i>",
        parse_mode="HTML",
        reply_markup=back_kb()
    )


@router.message(AdminStates.broadcast_text)
async def process_broadcast(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        return
    await state.clear()

    users = db.get_all_users()
    text = message.text or message.caption or ""

    sent = 0
    failed = 0
    status_msg = await message.answer(f"⏳ Рассылка начата... 0/{len(users)}")

    for i, user in enumerate(users):
        try:
            await bot.send_message(user["user_id"], f"📢 <b>Сообщение от администратора</b>\n\n{text}", parse_mode="HTML")
            sent += 1
        except Exception:
            failed += 1
        if (i + 1) % 20 == 0:
            try:
                await status_msg.edit_text(f"⏳ Рассылка... {i+1}/{len(users)}")
            except Exception:
                pass
        await asyncio.sleep(0.05)

    await status_msg.edit_text(
        f"✅ Рассылка завершена!\n\n"
        f"✔️ Доставлено: <b>{sent}</b>\n"
        f"❌ Ошибок: <b>{failed}</b>",
        parse_mode="HTML",
        reply_markup=back_kb()
    )


# ─── Channels ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "admin:channels")
async def cb_channels(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔")
        return
    await call.answer()
    await state.clear()
    channels = db.get_all_channels()
    text = (
        "📢 <b>Спонсорские каналы</b>\n\n"
        "Пользователи должны быть подписаны на эти каналы.\n"
        "Нажми на канал, чтобы удалить его."
    )
    if not channels:
        text += "\n\n<i>Каналы не добавлены.</i>"
    await call.message.edit_text(text, parse_mode="HTML", reply_markup=channels_kb(channels))


@router.callback_query(F.data == "admin:add_channel")
async def cb_add_channel(call: CallbackQuery, state: FSMContext):
    if not is_admin(call.from_user.id):
        await call.answer("⛔")
        return
    await call.answer()
    await state.set_state(AdminStates.add_channel_id)
    await call.message.edit_text(
        "➕ <b>Добавить канал</b>\n\n"
        "Шаг 1/3: Отправь <b>ID канала</b>.\n\n"
        "Чтобы узнать ID:\n"
        "1. Добавь бота в канал как администратора\n"
        "2. Перешли любое сообщение из канала боту @userinfobot\n"
        "3. ID будет в формате <code>-100xxxxxxxxxx</code>",
        parse_mode="HTML",
        reply_markup=back_kb("admin:channels")
    )


@router.message(AdminStates.add_channel_id)
async def process_channel_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    channel_id = message.text.strip()
    if not channel_id.startswith("-100"):
        await message.answer("❗ Неверный формат ID. Должен начинаться с <code>-100</code>.", parse_mode="HTML")
        return
    await state.update_data(channel_id=channel_id)
    await state.set_state(AdminStates.add_channel_title)
    await message.answer("Шаг 2/3: Напиши <b>название канала</b> (для отображения пользователям):", parse_mode="HTML")


@router.message(AdminStates.add_channel_title)
async def process_channel_title(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.update_data(channel_title=message.text.strip())
    await state.set_state(AdminStates.add_channel_link)
    await message.answer("Шаг 3/3: Отправь <b>ссылку-приглашение</b> на канал (https://t.me/...):", parse_mode="HTML")


@router.message(AdminStates.add_channel_link)
async def process_channel_link(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    data = await state.get_data()
    await state.clear()

    invite_link = message.text.strip()
    db.add_channel(data["channel_id"], data["channel_title"], invite_link)

    channels = db.get_all_channels()
    await message.answer(
        f"✅ Канал <b>{data['channel_title']}</b> добавлен!",
        parse_mode="HTML",
        reply_markup=channels_kb(channels)
    )


@router.callback_query(F.data.startswith("admin:del_channel:"))
async def cb_del_channel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        await call.answer("⛔")
        return
    await call.answer()
    channel_id = call.data.split(":", 2)[2]
    db.remove_channel(channel_id)
    channels = db.get_all_channels()
    await call.message.edit_text(
        "📢 <b>Спонсорские каналы</b>\n\n✅ Канал удалён.",
        parse_mode="HTML",
        reply_markup=channels_kb(channels)
    )
