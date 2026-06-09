import os
import logging
import asyncio
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, types, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import ReplyKeyboardBuilder, InlineKeyboardBuilder
import google.generativeai as genai

# Load environment variables
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DIRECTOR_CHAT_ID = os.getenv("DIRECTOR_CHAT_ID")

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configure Gemini API
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY is not set. AI assistant features will be unavailable.")

# Initialize router
router = Router()

# In-memory dictionary to store conversation histories for Gemini
# Format: {user_id: [{'role': 'user', 'parts': [...]}, {'role': 'model', 'parts': [...]}]}
chat_histories = {}

# Define Gemini System Prompt
SYSTEM_INSTRUCTION = """
Ты — лучший эксперт по продажам в учебном центре Salymbekov Business School (SBS) в городе Каракол.
Твоя миссия — не просто отвечать на вопросы, а вовлекать каждого пользователя и помогать ему принять решение о записи на наши курсы.

Твои правила работы:
1. НИКОГДА не отправляй пользователя к менеджеру, если можешь ответить сам. Твоя задача — закрыть потребность пользователя внутри диалога.
2. В каждом ответе деликатно связывай запрос пользователя с пользой от обучения на наших курсах. Например, если спрашивают про стоимость — сделай упор на ценность навыков, развитие мышления и будущие перспективы/высокую зарплату ребенка.
3. Используй убедительный, вдохновляющий и дружелюбный тон. Пиши на том же языке, на котором написан вопрос, используй уместные эмодзи.
4. В конце каждого ответа используй призыв к действию (CTA). Например: "Чтобы закрепить за собой место на курсе по выгодной цене, просто нажмите кнопку 'Записаться' ниже!" или "Давайте сделаем первый шаг к успеху вашего ребенка уже сегодня! Просто нажмите кнопку 'Записаться'".
5. Ты владеешь следующей информацией о центре:
   - Название центра: Salymbekov Business School (SBS) / Бизнес Школа Салымбекова
   - Адрес центра: г. Каракол, ул. Алыбакова 158, 0-й этаж (цокольный этаж)
   - Контакты (WhatsApp/Telegram): +996 701 000 712
   - Наши курсы и цены:
     * Смартик (подготовка к школе, 5-6 лет) — 4000 сом в месяц. Программа: развитие речи, математика, логика, письмо, психологическая адаптация к школе без стресса.
     * Ораторское искусство (8-16 лет) — 3500 сом в месяц. Программа: дикция, дикционные зажимы, актерское мастерство, уверенность на сцене и публике.
     * Будущие Лидеры Кыргызстана (БЛК, 12-17 лет) — 3500 сом в месяц. Программа: лидерство, проектный менеджмент, стартапы, финансовая грамотность, тайм-менеджмент.
     * Английский язык (7-16 лет) — 3500 сом в месяц. Программа: разговорная методика, снятие языкового барьера, грамматика в играх.
     * Летний лагерь (8-14 лет, 5в1) — 3500 сом за смену (2 недели, Пн-Пт с 09:00 до 13:00). Программа: ораторское искусство, английский язык, скорочтение, лидерство, творчество.
6. Если пользователь сомневается, подчеркни уникальность нашей школы, современные интерактивные методики обучения, отсутствие скучной школьной зубрежки и индивидуальный подход к каждому студенту.
"""

# FSM States for registration
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_child_name = State()
    waiting_for_child_age = State()
    waiting_for_phone = State()
    waiting_for_course = State()


# KEYBOARDS CREATOR functions
def get_main_keyboard():
    kb = [
        [types.KeyboardButton(text="📚 Наши курсы"), types.KeyboardButton(text="ℹ️ О центре")],
        [types.KeyboardButton(text="✍️ Записаться")],
        [types.KeyboardButton(text="💬 Задать вопрос ИИ")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_cancel_keyboard():
    kb = [
        [types.KeyboardButton(text="❌ Отмена")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_phone_keyboard():
    kb = [
        [types.KeyboardButton(text="📱 Поделиться контактом", request_contact=True)],
        [types.KeyboardButton(text="❌ Отмена")]
    ]
    return types.ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_courses_inline_keyboard():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="🏫 Смартик (5-6 лет)", callback_data="course_smartik"))
    builder.row(types.InlineKeyboardButton(text="🗣️ Ораторское искусство (8-16 лет)", callback_data="course_orator"))
    builder.row(types.InlineKeyboardButton(text="👑 Будущие Лидеры БЛК (12-17 лет)", callback_data="course_blk"))
    builder.row(types.InlineKeyboardButton(text="🇬🇧 Английский язык (7-16 лет)", callback_data="course_english"))
    builder.row(types.InlineKeyboardButton(text="☀️ Летний лагерь (8-14 лет)", callback_data="course_camp"))
    builder.row(types.InlineKeyboardButton(text="❌ Отменить запись", callback_data="course_cancel"))
    return builder.as_markup()


# HANDLERS: Commands and Menu buttons

@router.message(CommandStart())
async def cmd_start(message: types.Message):
    # Welcome message
    welcome_text = (
        f"Приветствуем вас в боте **Salymbekov Business School (SBS)**! 🎓🌟\n\n"
        f"Я — умный ИИ-менеджер. Отвечу на любые ваши вопросы о центре и курсах.\n\n"
        f"Используйте кнопки меню ниже для навигации или просто напишите мне ваш вопрос!"
    )
    await message.answer(welcome_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")


@router.message(F.text == "ℹ️ О центре")
async def cmd_about(message: types.Message, state: FSMContext):
    # Auto-cancel FSM if active
    await state.clear()
    
    about_text = (
        f"🏫 **Salymbekov Business School (SBS)** — современный центр обучения и развития детей и подростков в Караколе.\n\n"
        f"Мы создаем условия для развития гибких навыков (soft skills), критического мышления, ораторского мастерства и лидерства.\n\n"
        f"📍 **Адрес:** г. Каракол, ул. Алыбакова 158, 0-й этаж (цокольный).\n"
        f"📞 **WhatsApp/Telegram:** +996 701 000 712\n\n"
        f"Вы всегда можете задать мне любой вопрос о центре прямо здесь!"
    )
    await message.answer(about_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")


@router.message(F.text == "📚 Наши курсы")
async def cmd_courses(message: types.Message, state: FSMContext):
    # Auto-cancel FSM if active
    await state.clear()
    
    courses_text = (
        f"📚 **Курсы учебного центра SBS:**\n\n"
        f"1️⃣ **Смартик (подготовка к школе)**\n"
        f"👶 Возраст: 5-6 лет\n"
        f"💰 Стоимость: 4000 сом/месяц\n\n"
        f"2️⃣ **Ораторское искусство**\n"
        f"🗣️ Возраст: 8-16 лет\n"
        f"💰 Стоимость: 3500 сом/месяц\n\n"
        f"3️⃣ **Будущие Лидеры Кыргызстана (БЛК)**\n"
        f"👑 Возраст: 12-17 лет\n"
        f"💰 Стоимость: 3500 сом/месяц\n\n"
        f"4️⃣ **Английский язык**\n"
        f"🇬🇧 Возраст: 7-16 лет\n"
        f"💰 Стоимость: 3500 сом/месяц\n\n"
        f"5️⃣ **Летний лагерь (8-14 лет, 5в1)**\n"
        f"☀️ Возраст: 8-14 лет\n"
        f"💰 Стоимость: 3500 сом/смена (2 недели)\n\n"
        f"✨ Чтобы записаться на курс, нажмите кнопку **Записаться** ниже."
    )
    await message.answer(courses_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")


@router.message(F.text == "💬 Задать вопрос ИИ")
async def cmd_ask_ai_info(message: types.Message):
    await message.answer(
        "Вы можете спросить меня о чём угодно! Просто напишите ваш вопрос текстовым сообщением "
        "(например: _'Какая стоимость курса Смартик?'_ или _'Где вы находитесь?'_), и я отвечу вам.",
        reply_markup=get_main_keyboard(),
        parse_mode="Markdown"
    )


# HANDLERS: Global Cancellation
@router.message(Command("cancel"))
@router.message(F.text.casefold() == "отмена")
@router.message(F.text.casefold() == "❌ отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is None:
        await message.answer("Нет активного процесса записи.", reply_markup=get_main_keyboard())
        return
        
    await state.clear()
    await message.answer(
        "Запись отменена. Возвращаю вас в главное меню.",
        reply_markup=get_main_keyboard()
    )


# HANDLERS: FSM Registration Flow

@router.message(F.text == "✍️ Записаться")
async def start_registration(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(Registration.waiting_for_name)
    await message.answer(
        "📝 **Начинаем запись на курс**\n\n"
        "Как к вам обращаться? Пожалуйста, введите ваше имя (ФИО родителя):",
        reply_markup=get_cancel_keyboard(),
        parse_mode="Markdown"
    )


@router.message(Registration.waiting_for_name)
async def process_parent_name(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Пожалуйста, введите корректное имя (не менее 2 символов):")
        return
        
    await state.update_data(parent_name=message.text.strip())
    await state.set_state(Registration.waiting_for_child_name)
    await message.answer("Введите имя вашего ребенка:")


@router.message(Registration.waiting_for_child_name)
async def process_child_name(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        await message.answer("Пожалуйста, введите корректное имя ребенка:")
        return

    await state.update_data(child_name=message.text.strip())
    await state.set_state(Registration.waiting_for_child_age)
    await message.answer("Укажите возраст ребенка (полных лет, цифрами, например: 7):")


@router.message(Registration.waiting_for_child_age)
async def process_child_age(message: types.Message, state: FSMContext):
    age_text = message.text.strip()
    if not age_text.isdigit():
        await message.answer("Пожалуйста, введите возраст цифрами (например, 6 или 12):")
        return
        
    age = int(age_text)
    if age < 1 or age > 25:
        await message.answer("Пожалуйста, введите корректный возраст (от 2 до 20 лет):")
        return

    await state.update_data(child_age=age)
    await state.set_state(Registration.waiting_for_phone)
    await message.answer(
        "Пожалуйста, укажите ваш контактный номер телефона.\n"
        "Вы можете отправить свой контакт, нажав кнопку ниже, или ввести его вручную:",
        reply_markup=get_phone_keyboard()
    )


@router.message(Registration.waiting_for_phone)
async def process_phone(message: types.Message, state: FSMContext):
    phone = ""
    if message.contact:
        phone = message.contact.phone_number
    elif message.text:
        phone = message.text.strip()
        if len(phone) < 6:
            await message.answer("Пожалуйста, введите корректный номер телефона (например, +996 701 000 712):")
            return
    else:
        await message.answer("Пожалуйста, отправьте контакт с помощью кнопки или напишите телефон текстом.")
        return

    await state.update_data(phone=phone)
    await state.set_state(Registration.waiting_for_course)
    await message.answer(
        "Какой курс вас интересует? Выберите из списка ниже:",
        reply_markup=get_courses_inline_keyboard()
    )


@router.callback_query(Registration.waiting_for_course)
async def process_course_selection(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "course_cancel":
        await state.clear()
        await callback.answer("Запись отменена.")
        await callback.message.answer("Запись отменена. Возвращаю вас в главное меню.", reply_markup=get_main_keyboard())
        return

    courses_map = {
        "course_smartik": "Смартик (подготовка к школе, 5-6 лет)",
        "course_orator": "Ораторское искусство",
        "course_blk": "Будущие Лидеры Кыргызстана (БЛК)",
        "course_english": "Английский язык",
        "course_camp": "Летний лагерь (8-14 лет, 5в1)",
    }

    course_title = courses_map.get(callback.data)
    if not course_title:
        await callback.answer("Ошибка выбора курса. Пожалуйста, попробуйте еще раз.", show_alert=True)
        return

    await state.update_data(course=course_title)
    data = await state.get_data()
    await state.clear()

    parent_name = data.get("parent_name")
    child_name = data.get("child_name")
    child_age = data.get("child_age")
    phone = data.get("phone")

    # Send confirmation to the parent
    confirmation_text = (
        f"🎉 **Запись успешно оформлена!**\n\n"
        f"Наши менеджеры свяжутся с вами в ближайшее время для подтверждения.\n\n"
        f"📋 **Ваши данные:**\n"
        f"👤 Имя родителя: {parent_name}\n"
        f"👦 Имя ребенка: {child_name}\n"
        f"🎂 Возраст ребенка: {child_age} лет\n"
        f"📞 Телефон: {phone}\n"
        f"📚 Выбранный курс: {course_title}"
    )
    await callback.message.answer(confirmation_text, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    await callback.answer()

    # Send notification to the Director
    if DIRECTOR_CHAT_ID:
        director_msg = (
            f"🔔 **Новая запись на курс в SBS!**\n\n"
            f"👤 **Родитель:** {parent_name}\n"
            f"👦 **Ребенок:** {child_name}\n"
            f"🎂 **Возраст:** {child_age} лет\n"
            f"📞 **Телефон:** {phone}\n"
            f"📚 **Курс:** {course_title}"
        )
        try:
            # We send via callback.bot
            await callback.bot.send_message(chat_id=DIRECTOR_CHAT_ID, text=director_msg, parse_mode="Markdown")
            logger.info("Successfully sent enrollment notification to the Director.")
        except Exception as e:
            logger.error(f"Failed to send notification to Director (ID: {DIRECTOR_CHAT_ID}): {e}")
    else:
        logger.warning("DIRECTOR_CHAT_ID is not configured. Enrollment data logged but notification not sent.")


# HANDLERS: Fallback to Gemini AI for any other questions

@router.message(F.text)
async def handle_ai_query(message: types.Message, state: FSMContext):
    # Check if the user is in FSM
    current_state = await state.get_state()
    if current_state is not None:
        # If user is in FSM, prompt them to complete or cancel it
        await message.answer(
            "Вы находитесь в процессе записи на курс.\n\n"
            "Пожалуйста, ответьте на вопрос выше или напишите **Отмена** для выхода в меню.",
            reply_markup=get_cancel_keyboard()
        )
        return

    # User message text
    user_query = message.text.strip()
    
    if not GEMINI_API_KEY:
        await message.answer(
            "Извините, сейчас ИИ-помощник временно недоступен.\n\n"
            "Пожалуйста, задайте ваш вопрос администратору по телефону или WhatsApp: **+996 701 000 712**.",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )
        return

    # Show typing status while fetching response
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    user_id = message.from_user.id
    history = chat_histories.get(user_id, [])

    # Append user question to history
    history.append({'role': 'user', 'parts': [user_query]})

    try:
        # Construct and call Gemini model
        # GenerativeModel initialization
        model = genai.GenerativeModel(
            model_name="gemini-1.5-flash",
            system_instruction=SYSTEM_INSTRUCTION
        )
        
        # Start chat session with historical context
        # We pass history before the current message
        chat = model.start_chat(history=history[:-1])
        
        # Call the API asynchronously to avoid blocking the bot process
        response = await asyncio.to_thread(chat.send_message, user_query)
        model_reply = response.text

        # Append model response to history
        history.append({'role': 'model', 'parts': [model_reply]})

        # Prune history if it grows too long (keep last 12 messages / 6 turns)
        if len(history) > 12:
            history = history[-12:]
            
        chat_histories[user_id] = history

        # Send response to the user
        await message.answer(model_reply, reply_markup=get_main_keyboard())

    except Exception as e:
        logger.error(f"Gemini API Error: {e}")
        await message.answer(
            "Извините, произошла ошибка при обработке вашего запроса.\n"
            "Свяжитесь с нами напрямую по номеру **+996 701 000 712**.",
            reply_markup=get_main_keyboard(),
            parse_mode="Markdown"
        )


# Main starting loop
async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set in environment variables! Exiting...")
        return

    # Initialize Bot and Dispatcher
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)

    # Delete any webhooks to handle long polling cleanly
    await bot.delete_webhook(drop_pending_updates=True)

    logger.info("Bot starting with polling...")
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
