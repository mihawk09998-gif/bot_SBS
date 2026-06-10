import os
import json
import logging
import asyncio
from datetime import datetime, date
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, Router, F
from aiogram import types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.filters import CommandStart, Command
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.utils.keyboard import InlineKeyboardBuilder
from google import genai
from google.genai import types as genai_types
import gspread
from google.oauth2.service_account import Credentials

# ============================================================
#  CONFIG
# ============================================================
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
DIRECTOR_CHAT_ID = os.getenv("DIRECTOR_CHAT_ID")
ADMIN_CHAT_ID = os.getenv("ADMIN_CHAT_ID")
ADMIN_PASSWORD = "200903ss"  # <-- впишите свой пароль

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data.json")
USERS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.json")

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CREDENTIALS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credentials.json")
google_creds_env = os.getenv("GOOGLE_CREDENTIALS")
if google_creds_env:
    try:
        creds_data = json.loads(google_creds_env)
        with open(CREDENTIALS_FILE, "w", encoding="utf-8") as f:
            json.dump(creds_data, f, ensure_ascii=False, indent=2)
        logger.info("Successfully created credentials.json from GOOGLE_CREDENTIALS environment variable.")
    except Exception as e:
        logger.error(f"Failed to create credentials.json from GOOGLE_CREDENTIALS: {e}")

# Gemini client
client = None
if GEMINI_API_KEY:
    client = genai.Client(api_key=GEMINI_API_KEY)
else:
    logger.warning("GEMINI_API_KEY is not set.")

router = Router()
chat_histories: dict = {}

# ============================================================
#  JSON DATA STORE
# ============================================================
DEFAULT_DATA = {
    "courses": [
        {"id": "smartik",  "name": "Смартик (подготовка к школе)", "age": "5-6 лет", "price": "4000 сом/мес", "desc": "Развитие речи, математика, логика, письмо, психологическая адаптация к школе."},
        {"id": "orator",   "name": "Ораторское искусство",        "age": "8-16 лет", "price": "3500 сом/мес", "desc": "Дикция, актерское мастерство, уверенность на сцене."},
        {"id": "blk",      "name": "Будущие Лидеры Кыргызстана (БЛК)", "age": "12-17 лет", "price": "3500 сом/мес", "desc": "Лидерство, проектный менеджмент, стартапы, финграмотность."},
        {"id": "english",  "name": "Английский язык",             "age": "7-16 лет", "price": "3500 сом/мес", "desc": "Разговорная методика, снятие языкового барьера, грамматика в играх."},
        {"id": "camp",     "name": "Летний лагерь (5в1)",         "age": "8-14 лет", "price": "3500 сом/смена", "desc": "Ораторское искусство, английский, скорочтение, лидерство, творчество."},
    ],
    "ai_rules": [],
    "enrollments": [],
    "faq": [
        {
            "keywords": ["цена", "стоимость", "сколько стоит"],
            "answer": "📋 Наши курсы:\n🎒 Смартик (5-6 лет) — 4000 сом\n🎤 Ораторское — 3500 сом\n👑 БЛК — 3500 сом\n🇬🇧 Английский — 3500 сом\n☀️ Летний лагерь — 3500 сом"
        },
        {
            "keywords": ["адрес", "где", "находитесь", "как найти"],
            "answer": "📍 Каракол, ул. Алыбакова 158, 0-этаж\nОриентир: напротив тойкана Алтын Казына"
        },
        {
            "keywords": ["телефон", "номер", "контакт", "связь"],
            "answer": "📞 +996 701 000 712 (связь только по WhatsApp), 0505091285 (для обычных звонков)"
        },
        {
            "keywords": ["расписание", "время", "когда", "занятия"],
            "answer": "🕐 Занятия 5 дней в неделю\nпо 1-2 часа в день"
        },
        {
            "keywords": ["возраст", "лет", "сколько лет ребенку"],
            "answer": "👶 Смартик: 5-6 лет\n🎤 Ораторское: 8-16 лет\n👑 БЛК: 12-17 лет\n🇬🇧 Английский: 7-16 лет\n☀️ Летний лагерь: 8-14 лет"
        },
        {
            "keywords": ["сертификат", "документ", "свидетельство"],
            "answer": "🎓 По окончании курса выдаётся сертификат SBS"
        },
        {
            "keywords": ["запись", "записаться", "как записать"],
            "answer": "✍️ Нажмите кнопку Записаться ниже или напишите нам:\n📞 +996 701 000 712 (связь только по WhatsApp), 0505091285 (для обычных звонков)"
        }
    ]
}

def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            # ensure all keys exist
            for key in DEFAULT_DATA:
                if key not in data:
                    data[key] = DEFAULT_DATA[key]
            return data
        except Exception as e:
            logger.error(f"Failed to load data.json: {e}")
    return json.loads(json.dumps(DEFAULT_DATA))

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_sheet():
    scope = [
        'https://spreadsheets.google.com/feeds',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = Credentials.from_service_account_file(CREDENTIALS_FILE, scopes=scope)
    client = gspread.authorize(creds)
    return client.open("SBS_Bot").sheet1

def save_user(chat_id: int):
    # Local save for broadcasting
    users = []
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load users.json: {e}")
    
    if chat_id not in users:
        users.append(chat_id)
        try:
            with open(USERS_FILE, "w", encoding="utf-8") as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"Failed to save users.json: {e}")

    # Google Sheets save
    try:
        sheet = get_sheet()
        existing = sheet.col_values(1)
        if str(chat_id) not in existing:
            sheet.append_row([str(chat_id)])
    except Exception as e:
        logger.error(f"Sheets error: {e}")

app_data = load_data()

# ============================================================
#  DYNAMIC SYSTEM PROMPT BUILDER
# ============================================================
BASE_SYSTEM_PROMPT = """
Ты — лучший эксперт по продажам в учебном центре Salymbekov Business School (SBS) в городе Каракол.
Твоя миссия — не просто отвечать на вопросы, а вовлекать каждого пользователя и помогать ему принять решение о записи на наши курсы.

Твои правила работы:
1. НИКОГДА не отправляй пользователя к менеджеру, если можешь ответить сам.
2. В каждом ответе деликатно связывай запрос пользователя с пользой от обучения на наших курсах.
3. Используй убедительный, вдохновляющий и дружелюбный тон. Пиши на языке вопроса, используй эмодзи.
4. В конце каждого ответа используй призыв к действию (CTA): "Нажмите кнопку 'Записаться'".
5. Если пользователь сомневается — подчеркни уникальность школы, интерактивные методики и индивидуальный подход.

Информация о центре:
- Название: Salymbekov Business School (SBS)
- Адрес: г. Каракол, ул. Алыбакова 158, 0-й этаж
- Контакты: +996 701 000 712 (связь только по WhatsApp), 0505091285 (для обычных звонков)
"""

def build_system_instruction() -> str:
    parts = [BASE_SYSTEM_PROMPT.strip()]

    # Courses from data
    courses = app_data.get("courses", [])
    if courses:
        lines = ["\nНаши курсы и цены:"]
        for i, c in enumerate(courses, 1):
            lines.append(f"  {i}. {c['name']} ({c['age']}) — {c['price']}. {c['desc']}")
        parts.append("\n".join(lines))

    # Custom AI rules from admin
    rules = app_data.get("ai_rules", [])
    if rules:
        lines = ["\nДополнительные правила (ОБЯЗАТЕЛЬНО соблюдай):"]
        for i, rule in enumerate(rules, 1):
            lines.append(f"  {i}. {rule}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)

# ============================================================
#  FSM STATES
# ============================================================
class Registration(StatesGroup):
    waiting_for_name = State()
    waiting_for_child_name = State()
    waiting_for_child_age = State()
    waiting_for_phone = State()
    waiting_for_course = State()

class AdminStates(StatesGroup):
    waiting_password = State()
    # Course management
    add_course_name = State()
    add_course_age = State()
    add_course_price = State()
    add_course_desc = State()
    edit_course_field = State()
    edit_course_value = State()
    # AI rules
    add_rule = State()
    # Broadcast
    waiting_broadcast_text = State()
    waiting_broadcast_confirm = State()
    # FAQ
    add_faq_keywords = State()
    add_faq_answer = State()

# ============================================================
#  KEYBOARDS — CLIENT
# ============================================================
def get_main_keyboard():
    kb = [
        [KeyboardButton(text="📚 Наши курсы"), KeyboardButton(text="ℹ️ О центре")],
        [KeyboardButton(text="✍️ Записаться")],
        [KeyboardButton(text="💬 Задать вопрос ИИ")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_cancel_keyboard():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="❌ Отмена")]], resize_keyboard=True)

def get_phone_keyboard():
    kb = [
        [KeyboardButton(text="📱 Поделиться контактом", request_contact=True)],
        [KeyboardButton(text="❌ Отмена")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def get_courses_inline_keyboard():
    builder = InlineKeyboardBuilder()
    for c in app_data.get("courses", []):
        builder.row(types.InlineKeyboardButton(
            text=f"{c['name']} ({c['age']})",
            callback_data=f"enroll_{c['id']}"
        ))
    builder.row(types.InlineKeyboardButton(text="❌ Отменить запись", callback_data="enroll_cancel"))
    return builder.as_markup()

# ============================================================
#  KEYBOARDS — ADMIN
# ============================================================
def admin_main_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📚 Курсы", callback_data="adm_courses"))
    builder.row(types.InlineKeyboardButton(text="🤖 Правила ИИ", callback_data="adm_rules"))
    builder.row(types.InlineKeyboardButton(text="❓ Частые вопросы", callback_data="adm_faq"))
    builder.row(types.InlineKeyboardButton(text="📊 Статистика", callback_data="adm_stats"))
    builder.row(types.InlineKeyboardButton(text="📢 Рассылка", callback_data="adm_broadcast"))
    builder.row(types.InlineKeyboardButton(text="🚪 Выйти", callback_data="adm_exit"))
    return builder.as_markup()

def admin_courses_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📋 Все курсы", callback_data="adm_courses_list"))
    builder.row(types.InlineKeyboardButton(text="➕ Добавить курс", callback_data="adm_course_add"))
    builder.row(types.InlineKeyboardButton(text="✏️ Изменить курс", callback_data="adm_course_edit_pick"))
    builder.row(types.InlineKeyboardButton(text="🗑 Удалить курс", callback_data="adm_course_del_pick"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back"))
    return builder.as_markup()

def admin_rules_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📋 Все правила", callback_data="adm_rules_list"))
    builder.row(types.InlineKeyboardButton(text="➕ Добавить правило", callback_data="adm_rule_add"))
    builder.row(types.InlineKeyboardButton(text="🗑 Удалить правило", callback_data="adm_rule_del_pick"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back"))
    return builder.as_markup()

def courses_pick_kb(prefix: str):
    builder = InlineKeyboardBuilder()
    for c in app_data.get("courses", []):
        builder.row(types.InlineKeyboardButton(text=c["name"], callback_data=f"{prefix}_{c['id']}"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_courses"))
    return builder.as_markup()

def rules_del_kb():
    builder = InlineKeyboardBuilder()
    for i, rule in enumerate(app_data.get("ai_rules", [])):
        short = rule[:40] + ("…" if len(rule) > 40 else "")
        builder.row(types.InlineKeyboardButton(text=f"🗑 {short}", callback_data=f"adm_rule_del_{i}"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_rules"))
    return builder.as_markup()

def course_edit_fields_kb(course_id: str):
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="Название", callback_data=f"adm_cedit_name_{course_id}"))
    builder.row(types.InlineKeyboardButton(text="Возраст",  callback_data=f"adm_cedit_age_{course_id}"))
    builder.row(types.InlineKeyboardButton(text="Цена",     callback_data=f"adm_cedit_price_{course_id}"))
    builder.row(types.InlineKeyboardButton(text="Описание", callback_data=f"adm_cedit_desc_{course_id}"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_courses"))
    return builder.as_markup()

# ============================================================
#  ADMIN AUTH HELPER
# ============================================================
def is_admin(user_id: int) -> bool:
    if ADMIN_CHAT_ID and str(user_id) == str(ADMIN_CHAT_ID):
        return True
    return False

# ============================================================
#  CLIENT HANDLERS
# ============================================================
@router.message(CommandStart())
async def cmd_start(message: types.Message, state: FSMContext):
    save_user(message.chat.id)
    await state.clear()
    await message.answer(
        "Приветствуем вас в боте **Salymbekov Business School (SBS)**! 🎓🌟\n\n"
        "Я — менеджер. Отвечу на любые ваши вопросы о центре и курсах.\n\n"
        "Используйте кнопки меню ниже или просто напишите мне ваш вопрос!",
        reply_markup=get_main_keyboard(), parse_mode="Markdown"
    )

@router.message(F.text == "ℹ️ О центре")
async def cmd_about(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🏫 **Salymbekov Business School (SBS)**\n\n"
        "Современный центр обучения и развития детей и подростков в Караколе.\n\n"
        "📍 **Адрес:** г. Каракол, ул. Алыбакова 158, 0-й этаж\n"
        "📞 **Контакты:** +996 701 000 712 (связь только по WhatsApp), 0505091285 (для обычных звонков)",
        reply_markup=get_main_keyboard(), parse_mode="Markdown"
    )

@router.message(F.text == "📚 Наши курсы")
async def cmd_courses(message: types.Message, state: FSMContext):
    await state.clear()
    courses = app_data.get("courses", [])
    if not courses:
        await message.answer("Пока курсов нет. Загляните позже!", reply_markup=get_main_keyboard())
        return
    lines = ["📚 **Курсы учебного центра SBS:**\n"]
    emojis = ["1️⃣","2️⃣","3️⃣","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    for i, c in enumerate(courses):
        e = emojis[i] if i < len(emojis) else f"{i+1}."
        lines.append(f"{e} **{c['name']}**\n🎯 Возраст: {c['age']}\n💰 Стоимость: {c['price']}\n")
    lines.append("✨ Чтобы записаться, нажмите **Записаться** ниже.")
    await message.answer("\n".join(lines), reply_markup=get_main_keyboard(), parse_mode="Markdown")

@router.message(F.text == "💬 Задать вопрос ИИ")
async def cmd_ask_ai(message: types.Message):
    await message.answer(
        "Просто напишите ваш вопрос текстовым сообщением, и я отвечу! 😊",
        reply_markup=get_main_keyboard()
    )

# ============================================================
#  CANCEL
# ============================================================
@router.message(Command("cancel"))
@router.message(F.text.casefold() == "отмена")
@router.message(F.text.casefold() == "❌ отмена")
async def cancel_handler(message: types.Message, state: FSMContext):
    current = await state.get_state()
    if current is None:
        await message.answer("Нет активного процесса.", reply_markup=get_main_keyboard())
        return
    await state.clear()
    await message.answer("Отменено. Возвращаю в главное меню.", reply_markup=get_main_keyboard())

# ============================================================
#  REGISTRATION FSM
# ============================================================
@router.message(F.text == "✍️ Записаться")
async def start_reg(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(Registration.waiting_for_name)
    await message.answer("📝 **Запись на курс**\n\nВаше имя (ФИО родителя):", reply_markup=get_cancel_keyboard(), parse_mode="Markdown")

@router.message(Registration.waiting_for_name)
async def reg_name(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        return await message.answer("Введите корректное имя (минимум 2 символа):")
    await state.update_data(parent_name=message.text.strip())
    await state.set_state(Registration.waiting_for_child_name)
    await message.answer("Имя ребенка:")

@router.message(Registration.waiting_for_child_name)
async def reg_child(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) < 2:
        return await message.answer("Введите корректное имя ребенка:")
    await state.update_data(child_name=message.text.strip())
    await state.set_state(Registration.waiting_for_child_age)
    await message.answer("Возраст ребенка (цифрой):")

@router.message(Registration.waiting_for_child_age)
async def reg_age(message: types.Message, state: FSMContext):
    t = message.text.strip()
    if not t.isdigit() or not (1 <= int(t) <= 25):
        return await message.answer("Введите корректный возраст цифрой (2-20):")
    await state.update_data(child_age=int(t))
    await state.set_state(Registration.waiting_for_phone)
    await message.answer("Контактный телефон:", reply_markup=get_phone_keyboard())

@router.message(Registration.waiting_for_phone)
async def reg_phone(message: types.Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    elif message.text and len(message.text.strip()) >= 6:
        phone = message.text.strip()
    else:
        return await message.answer("Введите корректный номер телефона или нажмите кнопку:")
    await state.update_data(phone=phone)
    await state.set_state(Registration.waiting_for_course)
    await message.answer("Выберите курс:", reply_markup=get_courses_inline_keyboard())

@router.callback_query(Registration.waiting_for_course)
async def reg_course(callback: types.CallbackQuery, state: FSMContext):
    if callback.data == "enroll_cancel":
        await state.clear()
        await callback.answer("Запись отменена.")
        return await callback.message.answer("Запись отменена.", reply_markup=get_main_keyboard())

    course_id = callback.data.replace("enroll_", "")
    course = next((c for c in app_data.get("courses", []) if c["id"] == course_id), None)
    if not course:
        return await callback.answer("Курс не найден.", show_alert=True)

    await state.update_data(course=course["name"])
    data = await state.get_data()
    await state.clear()

    pn, cn, ca, ph = data["parent_name"], data["child_name"], data["child_age"], data["phone"]

    # Save enrollment to data.json
    enrollment = {
        "parent": pn, "child": cn, "age": ca, "phone": ph,
        "course": course["name"], "course_id": course_id,
        "date": datetime.now().isoformat()
    }
    app_data.setdefault("enrollments", []).append(enrollment)
    save_data(app_data)

    confirm = (
        f"🎉 **Запись оформлена!**\n\n"
        f"👤 Родитель: {pn}\n👦 Ребенок: {cn}\n🎂 Возраст: {ca}\n"
        f"📞 Телефон: {ph}\n📚 Курс: {course['name']}"
    )
    await callback.message.answer(confirm, reply_markup=get_main_keyboard(), parse_mode="Markdown")
    await callback.answer()

    # Notify director
    if DIRECTOR_CHAT_ID:
        try:
            await callback.bot.send_message(
                chat_id=DIRECTOR_CHAT_ID,
                text=f"🔔 **Новая заявка SBS!**\n\n👤 {pn}\n👦 {cn} ({ca} лет)\n📞 {ph}\n📚 {course['name']}",
                parse_mode="Markdown"
            )
        except Exception as e:
            logger.error(f"Director notify error: {e}")

# ============================================================
#  ADMIN — /admin COMMAND + PASSWORD
# ============================================================
@router.message(Command("admin"))
async def cmd_admin(message: types.Message, state: FSMContext):
    await state.clear()
    if is_admin(message.from_user.id):
        # Already verified by chat ID
        if ADMIN_PASSWORD:
            await state.set_state(AdminStates.waiting_password)
            return await message.answer("🔐 Введите пароль администратора:", reply_markup=get_cancel_keyboard())
        return await message.answer("⚙️ **Админ-панель SBS**", reply_markup=admin_main_kb(), parse_mode="Markdown")
    await message.answer("⛔ Доступ запрещен.")

@router.message(AdminStates.waiting_password)
async def admin_password(message: types.Message, state: FSMContext):
    if message.text and message.text.strip() == ADMIN_PASSWORD:
        await state.clear()
        return await message.answer("⚙️ **Админ-панель SBS**", reply_markup=admin_main_kb(), parse_mode="Markdown")
    await state.clear()
    await message.answer("❌ Неверный пароль.", reply_markup=get_main_keyboard())

# ============================================================
#  ADMIN — NAVIGATION CALLBACKS
# ============================================================
@router.callback_query(F.data == "adm_back")
async def adm_back(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await cb.message.edit_text("⚙️ **Админ-панель SBS**", reply_markup=admin_main_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "adm_exit")
async def adm_exit(cb: types.CallbackQuery):
    await cb.message.edit_text("Вы вышли из админ-панели.")
    await cb.answer()

# ============================================================
#  ADMIN — COURSES
# ============================================================
@router.callback_query(F.data == "adm_courses")
async def adm_courses(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await cb.message.edit_text("📚 **Управление курсами**", reply_markup=admin_courses_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "adm_courses_list")
async def adm_courses_list(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    courses = app_data.get("courses", [])
    if not courses:
        text = "Курсов пока нет."
    else:
        lines = []
        for i, c in enumerate(courses, 1):
            lines.append(f"{i}. **{c['name']}**\n   Возраст: {c['age']} | Цена: {c['price']}\n   {c['desc']}")
        text = "\n\n".join(lines)
    await cb.message.edit_text(text, reply_markup=admin_courses_kb(), parse_mode="Markdown")

# --- Add course ---
@router.callback_query(F.data == "adm_course_add")
async def adm_course_add(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await state.set_state(AdminStates.add_course_name)
    await cb.message.answer("Введите **название** нового курса:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await cb.answer()

@router.message(AdminStates.add_course_name)
async def adm_add_name(message: types.Message, state: FSMContext):
    await state.update_data(new_name=message.text.strip())
    await state.set_state(AdminStates.add_course_age)
    await message.answer("Введите **возраст** (например: 8-14 лет):", parse_mode="Markdown")

@router.message(AdminStates.add_course_age)
async def adm_add_age(message: types.Message, state: FSMContext):
    await state.update_data(new_age=message.text.strip())
    await state.set_state(AdminStates.add_course_price)
    await message.answer("Введите **цену** (например: 3500 сом/мес):", parse_mode="Markdown")

@router.message(AdminStates.add_course_price)
async def adm_add_price(message: types.Message, state: FSMContext):
    await state.update_data(new_price=message.text.strip())
    await state.set_state(AdminStates.add_course_desc)
    await message.answer("Введите **описание** курса:", parse_mode="Markdown")

@router.message(AdminStates.add_course_desc)
async def adm_add_desc(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    course_id = data["new_name"].lower().replace(" ", "_")[:20] + f"_{len(app_data['courses'])}"
    new_course = {
        "id": course_id,
        "name": data["new_name"],
        "age": data["new_age"],
        "price": data["new_price"],
        "desc": message.text.strip()
    }
    app_data["courses"].append(new_course)
    save_data(app_data)
    await message.answer(f"✅ Курс **{new_course['name']}** добавлен!", reply_markup=admin_main_kb(), parse_mode="Markdown")

# --- Delete course ---
@router.callback_query(F.data == "adm_course_del_pick")
async def adm_course_del_pick(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await cb.message.edit_text("Выберите курс для удаления:", reply_markup=courses_pick_kb("adm_cdel"))

@router.callback_query(F.data.startswith("adm_cdel_"))
async def adm_course_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    cid = cb.data.replace("adm_cdel_", "")
    course = next((c for c in app_data["courses"] if c["id"] == cid), None)
    if course:
        app_data["courses"].remove(course)
        save_data(app_data)
        await cb.message.edit_text(f"🗑 Курс **{course['name']}** удален.", reply_markup=admin_courses_kb(), parse_mode="Markdown")
    else:
        await cb.answer("Курс не найден", show_alert=True)

# --- Edit course ---
@router.callback_query(F.data == "adm_course_edit_pick")
async def adm_course_edit_pick(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await cb.message.edit_text("Выберите курс для редактирования:", reply_markup=courses_pick_kb("adm_cedit"))

@router.callback_query(F.data.startswith("adm_cedit_") & ~F.data.startswith("adm_cedit_name_") & ~F.data.startswith("adm_cedit_age_") & ~F.data.startswith("adm_cedit_price_") & ~F.data.startswith("adm_cedit_desc_"))
async def adm_course_edit_select(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    cid = cb.data.replace("adm_cedit_", "")
    course = next((c for c in app_data["courses"] if c["id"] == cid), None)
    if not course:
        return await cb.answer("Курс не найден", show_alert=True)
    await cb.message.edit_text(
        f"Редактирование: **{course['name']}**\nВыберите поле:",
        reply_markup=course_edit_fields_kb(cid), parse_mode="Markdown"
    )

@router.callback_query(F.data.regexp(r"^adm_cedit_(name|age|price|desc)_(.+)$"))
async def adm_course_edit_field(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    parts = cb.data.split("_", 3)  # adm, cedit, field, course_id
    field = parts[2]
    course_id = cb.data.split(f"adm_cedit_{field}_", 1)[1]
    labels = {"name": "название", "age": "возраст", "price": "цену", "desc": "описание"}
    await state.set_state(AdminStates.edit_course_value)
    await state.update_data(edit_course_id=course_id, edit_field=field)
    await cb.message.answer(f"Введите новое **{labels[field]}**:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
    await cb.answer()

@router.message(AdminStates.edit_course_value)
async def adm_course_edit_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await state.clear()
    cid = data["edit_course_id"]
    field = data["edit_field"]
    course = next((c for c in app_data["courses"] if c["id"] == cid), None)
    if not course:
        return await message.answer("Курс не найден.", reply_markup=admin_main_kb())
    course[field] = message.text.strip()
    save_data(app_data)
    await message.answer(f"✅ Поле обновлено: **{course['name']}**", reply_markup=admin_main_kb(), parse_mode="Markdown")

# ============================================================
#  ADMIN — AI RULES
# ============================================================
@router.callback_query(F.data == "adm_rules")
async def adm_rules(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await cb.message.edit_text("🤖 **Правила для ИИ**", reply_markup=admin_rules_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "adm_rules_list")
async def adm_rules_list(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    rules = app_data.get("ai_rules", [])
    if not rules:
        text = "Дополнительных правил нет."
    else:
        text = "\n".join([f"{i}. {r}" for i, r in enumerate(rules, 1)])
    await cb.message.edit_text(f"📋 **Правила ИИ:**\n\n{text}", reply_markup=admin_rules_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "adm_rule_add")
async def adm_rule_add(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await state.set_state(AdminStates.add_rule)
    await cb.message.answer("Введите новое правило для ИИ:", reply_markup=get_cancel_keyboard())
    await cb.answer()

@router.message(AdminStates.add_rule)
async def adm_rule_add_text(message: types.Message, state: FSMContext):
    await state.clear()
    rule = message.text.strip()
    app_data.setdefault("ai_rules", []).append(rule)
    save_data(app_data)
    await message.answer(f"✅ Правило добавлено:\n\"{rule}\"", reply_markup=admin_main_kb())

@router.callback_query(F.data == "adm_rule_del_pick")
async def adm_rule_del_pick(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    rules = app_data.get("ai_rules", [])
    if not rules:
        return await cb.answer("Правил нет", show_alert=True)
    await cb.message.edit_text("Выберите правило для удаления:", reply_markup=rules_del_kb())

@router.callback_query(F.data.startswith("adm_rule_del_"))
async def adm_rule_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    idx = int(cb.data.replace("adm_rule_del_", ""))
    rules = app_data.get("ai_rules", [])
    if 0 <= idx < len(rules):
        removed = rules.pop(idx)
        save_data(app_data)
        await cb.message.edit_text(f"🗑 Правило удалено:\n\"{removed}\"", reply_markup=admin_rules_kb())
    else:
        await cb.answer("Правило не найдено", show_alert=True)

# ============================================================
#  ADMIN — STATISTICS
# ============================================================
@router.callback_query(F.data == "adm_stats")
async def adm_stats(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    enrollments = app_data.get("enrollments", [])
    total = len(enrollments)
    today_str = date.today().isoformat()
    today_count = sum(1 for e in enrollments if e.get("date", "").startswith(today_str))

    # Course popularity
    course_counts: dict = {}
    for e in enrollments:
        cname = e.get("course", "Неизвестно")
        course_counts[cname] = course_counts.get(cname, 0) + 1
    if course_counts:
        popular = sorted(course_counts.items(), key=lambda x: x[1], reverse=True)
        pop_lines = "\n".join([f"  • {name}: {cnt} заявок" for name, cnt in popular])
    else:
        pop_lines = "  Заявок пока нет."

    text = (
        f"📊 **Статистика SBS**\n\n"
        f"📅 Заявок сегодня: **{today_count}**\n"
        f"📈 Всего заявок: **{total}**\n\n"
        f"🏆 **Популярность курсов:**\n{pop_lines}"
    )
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back"))
    await cb.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")

# ============================================================
#  ADMIN — BROADCAST (РАССЫЛКА)
# ============================================================
@router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await state.set_state(AdminStates.waiting_broadcast_text)
    await cb.message.answer("📝 Введите текст сообщения для рассылки:", reply_markup=get_cancel_keyboard())
    await cb.answer()

@router.message(AdminStates.waiting_broadcast_text)
async def adm_broadcast_text_received(message: types.Message, state: FSMContext):
    if not message.text:
        return await message.answer("Пожалуйста, отправьте текстовое сообщение для рассылки:")
    
    broadcast_text = message.text.strip()
    await state.update_data(broadcast_text=broadcast_text)
    await state.set_state(AdminStates.waiting_broadcast_confirm)
    
    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(text="✅ Да, отправить", callback_data="confirm_broadcast_yes"),
        types.InlineKeyboardButton(text="❌ Отмена", callback_data="confirm_broadcast_no")
    )
    
    await message.answer(
        f"⚠️ **Подтвердите отправку сообщения всем пользователям:**\n\n💬 {broadcast_text}",
        reply_markup=builder.as_markup()
    )

@router.callback_query(F.data == "confirm_broadcast_no")
async def adm_broadcast_cancel(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await state.clear()
    await cb.message.edit_text("❌ Рассылка отменена.", reply_markup=admin_main_kb())
    await cb.answer()

@router.callback_query(F.data == "confirm_broadcast_yes")
async def adm_broadcast_execute(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    
    data = await state.get_data()
    broadcast_text = data.get("broadcast_text")
    await state.clear()
    
    if not broadcast_text:
        await cb.answer("Ошибка: пустое сообщение.", show_alert=True)
        return await cb.message.edit_text("❌ Не удалось отправить пустое сообщение.", reply_markup=admin_main_kb())
    
    # Read users
    users = []
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load users.json: {e}")
            
    if not users:
        await cb.answer("Нет пользователей в базе данных.", show_alert=True)
        return await cb.message.edit_text("❌ База данных пользователей пуста.", reply_markup=admin_main_kb())
        
    await cb.message.edit_text("⏳ Идет рассылка сообщений...")
    await cb.answer()
    
    success = 0
    errors = 0
    
    for chat_id in users:
        try:
            await cb.bot.send_message(chat_id=chat_id, text=broadcast_text)
            success += 1
            await asyncio.sleep(0.05) # Respect limits
        except Exception as e:
            logger.error(f"Failed to send broadcast to {chat_id}: {e}")
            errors += 1
            
    stats_text = (
        f"📢 **Рассылка завершена!**\n\n"
        f"✅ Отправлено: {success}\n"
        f"❌ Ошибок: {errors}"
    )
    await cb.message.answer(stats_text, reply_markup=admin_main_kb(), parse_mode="Markdown")

# ============================================================
#  ADMIN — FAQ (ЧАСТЫЕ ВОПРОСЫ)
# ============================================================
def admin_faq_kb():
    builder = InlineKeyboardBuilder()
    builder.row(types.InlineKeyboardButton(text="📋 Список вопросов", callback_data="adm_faq_list"))
    builder.row(types.InlineKeyboardButton(text="➕ Добавить вопрос", callback_data="adm_faq_add"))
    builder.row(types.InlineKeyboardButton(text="🗑 Удалить вопрос", callback_data="adm_faq_del_pick"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_back"))
    return builder.as_markup()

def faq_del_kb():
    builder = InlineKeyboardBuilder()
    faq_list = app_data.get("faq", [])
    for i, item in enumerate(faq_list):
        keywords_str = ", ".join(item["keywords"])
        short = keywords_str[:40] + ("…" if len(keywords_str) > 40 else "")
        builder.row(types.InlineKeyboardButton(text=f"🗑 {short}", callback_data=f"adm_faq_del_{i}"))
    builder.row(types.InlineKeyboardButton(text="◀️ Назад", callback_data="adm_faq"))
    return builder.as_markup()

@router.callback_query(F.data == "adm_faq")
async def adm_faq(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await cb.message.edit_text("❓ **Управление частыми вопросами (FAQ)**", reply_markup=admin_faq_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "adm_faq_list")
async def adm_faq_list(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    faq_list = app_data.get("faq", [])
    if not faq_list:
        text = "Список частых вопросов пуст."
    else:
        lines = []
        for i, item in enumerate(faq_list, 1):
            kw_str = ", ".join(item["keywords"])
            lines.append(f"{i}. **Ключевые слова:** {kw_str}\n   **Ответ:** {item['answer']}")
        text = "\n\n".join(lines)
    await cb.message.edit_text(f"❓ **Частые вопросы (FAQ):**\n\n{text}", reply_markup=admin_faq_kb(), parse_mode="Markdown")

@router.callback_query(F.data == "adm_faq_add")
async def adm_faq_add(cb: types.CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    await state.set_state(AdminStates.add_faq_keywords)
    await cb.message.answer(
        "Введите ключевые слова **через запятую**:\n"
        "*(пример: цена, стоимость, сколько)*",
        parse_mode="Markdown", reply_markup=get_cancel_keyboard()
    )
    await cb.answer()

@router.message(AdminStates.add_faq_keywords)
async def adm_add_faq_keywords(message: types.Message, state: FSMContext):
    raw_text = message.text or ""
    keywords = [kw.strip().lower() for kw in raw_text.split(",") if kw.strip()]
    if not keywords:
        return await message.answer("Пожалуйста, введите хотя бы одно ключевое слово:")
    await state.update_data(faq_keywords=keywords)
    await state.set_state(AdminStates.add_faq_answer)
    await message.answer("Теперь введите **текст ответа** для этих ключевых слов:", parse_mode="Markdown")

@router.message(AdminStates.add_faq_answer)
async def adm_add_faq_answer(message: types.Message, state: FSMContext):
    answer = (message.text or "").strip()
    if not answer:
        return await message.answer("Ответ не может быть пустым. Введите текст ответа:")
    data = await state.get_data()
    await state.clear()
    
    new_faq = {
        "keywords": data["faq_keywords"],
        "answer": answer
    }
    app_data.setdefault("faq", []).append(new_faq)
    save_data(app_data)
    await message.answer("✅ Частый вопрос успешно добавлен!", reply_markup=admin_main_kb())

@router.callback_query(F.data == "adm_faq_del_pick")
async def adm_faq_del_pick(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    faq_list = app_data.get("faq", [])
    if not faq_list:
        return await cb.answer("Список вопросов пуст", show_alert=True)
    await cb.message.edit_text("Выберите частый вопрос для удаления:", reply_markup=faq_del_kb())

@router.callback_query(F.data.startswith("adm_faq_del_"))
async def adm_faq_del(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id): return await cb.answer("⛔")
    idx = int(cb.data.replace("adm_faq_del_", ""))
    faq_list = app_data.get("faq", [])
    if 0 <= idx < len(faq_list):
        removed = faq_list.pop(idx)
        save_data(app_data)
        kw_str = ", ".join(removed["keywords"])
        await cb.message.edit_text(f"🗑 Удален вопрос с ключевыми словами:\n\"{kw_str}\"", reply_markup=admin_faq_kb())
    else:
        await cb.answer("Вопрос не найден", show_alert=True)

# ============================================================
#  GEMINI AI HANDLER (fallback for free text)
# ============================================================
@router.message(F.text)
async def handle_ai_query(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return await message.answer(
            "Пожалуйста, ответьте на вопрос выше или напишите Отмена.",
            reply_markup=get_cancel_keyboard()
        )

    user_query = message.text.strip()
    user_query_lower = user_query.lower()

    # FAQ Interception Layer
    faq_list = app_data.get("faq", [])
    for item in faq_list:
        keywords = item.get("keywords", [])
        for kw in keywords:
            if kw and kw in user_query_lower:
                try:
                    await message.answer(item["answer"], reply_markup=get_main_keyboard(), parse_mode="Markdown")
                except Exception:
                    await message.answer(item["answer"], reply_markup=get_main_keyboard())
                return

    if not client:
        return await message.answer(
            "Этот вопрос вы можете обговорить, связавшись с директором по тел: +996 701 000 712 (связь только по WhatsApp), 0505091285 (для обычных звонков)",
            reply_markup=get_main_keyboard()
        )

    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")

    user_id = message.from_user.id
    history = chat_histories.get(user_id, [])

    try:
        contents = list(history) + [
            genai_types.Content(role="user", parts=[genai_types.Part(text=user_query)])
        ]

        system_instruction = build_system_instruction()

        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=contents,
            config=genai_types.GenerateContentConfig(
                system_instruction=system_instruction
            )
        )
        model_reply = response.text

        history.append(genai_types.Content(role="user", parts=[genai_types.Part(text=user_query)]))
        history.append(genai_types.Content(role="model", parts=[genai_types.Part(text=model_reply)]))
        if len(history) > 12:
            history = history[-12:]
        chat_histories[user_id] = history

        try:
            await message.answer(model_reply, reply_markup=get_main_keyboard(), parse_mode="Markdown")
        except Exception:
            await message.answer(model_reply, reply_markup=get_main_keyboard())

    except Exception as e:
        logger.error(f"Gemini API Error: {e}", exc_info=True)
        await message.answer(
            "Этот вопрос вы можете обговорить, связавшись с директором по тел: +996 701 000 712 (связь только по WhatsApp), 0505091285 (для обычных звонков)",
            reply_markup=get_main_keyboard()
        )

# ============================================================
#  MAIN
# ============================================================
async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not set!")
        return
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
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
