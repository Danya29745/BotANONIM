from aiogram import Router, Bot, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

import database as db

router = Router()


class ReplyState(StatesGroup):
    waiting_answer = State()


# ─── Owner presses "Ответить" button ─────────────────────────────────────────

@router.callback_query(F.data.startswith("reply:"))
async def cb_reply(call: CallbackQuery, state: FSMContext):
    await call.answer()
    qid = int(call.data.split(":")[1])
    question = db.get_question(qid)

    if not question:
        await call.message.answer("❌ Вопрос не найден.")
        return

    if question["owner_id"] != call.from_user.id:
        await call.message.answer("⛔ Это не твой вопрос.")
        return

    if question["answer_text"]:
        await call.message.answer("ℹ️ Ты уже ответил на этот вопрос.")
        return

    await state.set_state(ReplyState.waiting_answer)
    await state.update_data(qid=qid)

    await call.message.answer(
        f"✏️ Напиши ответ на вопрос <b>#{qid}</b>:\n\n"
        f"<i>{question['question_text']}</i>",
        parse_mode="HTML"
    )


# ─── Owner sends answer ───────────────────────────────────────────────────────

@router.message(ReplyState.waiting_answer)
async def receive_answer(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    qid = data["qid"]
    question = db.get_question(qid)

    answer_text = message.text or message.caption or ""
    if not answer_text:
        await message.answer("❗ Пожалуйста, отправь текстовый ответ.")
        return

    db.save_answer(qid, answer_text)
    await state.clear()

    await message.answer(f"✅ Ответ на вопрос #{qid} отправлен!")

    # Notify asker
    asker_id = question.get("asker_id")
    if asker_id:
        try:
            await bot.send_message(
                asker_id,
                f"💬 <b>Ответ на твой вопрос:</b>\n\n"
                f"<b>Твой вопрос:</b>\n<i>{question['question_text']}</i>\n\n"
                f"<b>Ответ:</b>\n{answer_text}",
                parse_mode="HTML"
            )
        except Exception:
            pass  # User may have blocked the bot
