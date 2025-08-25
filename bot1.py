import asyncio
import json
import os
import datetime
import contextlib
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
    ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove
)
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.filters import StateFilter

API_TOKEN = "8138182283:AAHSnvgi5j4ksM2--jr1b31SsVpI2qGF-YM"
ADMINS = [1295147526, 1235984904]

def is_admin(user_id):
    return user_id in ADMINS

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

FLOWERS_FILE = "flowers.json"
USERS_FILE = "users.json"
flowers = []
users = set()

def save_flowers():
    with open(FLOWERS_FILE, "w", encoding="utf-8") as f:
        json.dump(flowers, f, ensure_ascii=False, indent=2)

def load_flowers():
    global flowers
    if os.path.exists(FLOWERS_FILE):
        try:
            with open(FLOWERS_FILE, "r", encoding="utf-8") as f:
                flowers = json.load(f)
        except Exception:
            flowers = []
            save_flowers()
    else:
        flowers = []

def save_users():
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(list(users), f)

def load_users():
    global users
    if os.path.exists(USERS_FILE):
        try:
            with open(USERS_FILE, "r", encoding="utf-8") as f:
                users = set(json.load(f))
        except Exception:
            users = set()
            save_users()
    else:
        users = set()

load_flowers()
load_users()

carts = {}

CATEGORIES = ["Букеты"]
category_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=cat)] for cat in CATEGORIES],
    resize_keyboard=True,
    one_time_keyboard=True
)

main_menu = ReplyKeyboardMarkup(
    keyboard=[
        [
            KeyboardButton(text="🌸 Каталог"),
            KeyboardButton(text="ℹ️ О нас")
        ],
        [
            KeyboardButton(text="📱 Соц.сети"),
            KeyboardButton(text="👤 Связаться с менеджером")
        ]
    ],
    resize_keyboard=True
)

@dp.message(lambda m: m.text == "👤 Связаться с менеджером")
async def contact_admin(msg: Message):
    await msg.answer(
        "Вы можете написать менеджеру напрямую:\n"
        "WhatsApp:https://clck.ru/3Nh8rH\n"
        "Или позвонить: +79214070906"
    )

pickup_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Доставка 🚚"), KeyboardButton(text="Самовывоз 🏪")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

payment_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Оплата при получении"), KeyboardButton(text="Оплата менеджеру")]
    ],
    resize_keyboard=True,
    one_time_keyboard=True
)

DELIVERY_REGIONS = [
    "г. Тосно",
    "Тосненский район",
    "Ленинградская область",
    "г. Санкт-Петербург"
]
region_kb = ReplyKeyboardMarkup(
    keyboard=[[KeyboardButton(text=region)] for region in DELIVERY_REGIONS],
    resize_keyboard=True,
    one_time_keyboard=True
)

def with_back_kb(keyboard):
    kb = keyboard.keyboard.copy()
    kb.append([KeyboardButton(text="⬅️ Назад")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True, one_time_keyboard=True)

category_kb_with_back = with_back_kb(category_kb)
pickup_kb_with_back = with_back_kb(pickup_kb)
region_kb_with_back = with_back_kb(region_kb)
payment_kb_with_back = with_back_kb(payment_kb)

PRICE_RANGES = {
    "Букеты": [
        ("1000₽ — 3000₽", 1000, 3000),
        ("3000₽ — 6000₽", 3000, 6000),
        ("6000₽ и выше", 6000, 999999)
    ],
}

class AddFlower(StatesGroup):
    waiting_for_photo = State()
    waiting_for_name = State()
    waiting_for_price = State()
    waiting_for_emoji = State()
    waiting_for_category = State()

class EditFlowerFSM(StatesGroup):
    waiting_for_action = State()
    waiting_for_new_name = State()
    waiting_for_new_price = State()
    waiting_for_new_emoji = State()
    waiting_for_new_category = State()

class OrderFSM(StatesGroup):
    choosing_delivery = State()
    choosing_region = State()
    entering_address = State()
    choosing_date = State()
    choosing_time = State()
    entering_phone = State()
    entering_name = State()
    asking_card = State()
    entering_card_text = State()
    choosing_payment = State()
    waiting_for_order_confirm = State()

class BroadcastFSM(StatesGroup):
    waiting_for_text = State()

async def send_disappearing_message(user_id, text, state, **kwargs):
    data = await state.get_data()
    last_id = data.get("last_bot_message_id")
    if last_id:
        with contextlib.suppress(Exception):
            await bot.delete_message(user_id, last_id)
    msg = await bot.send_message(user_id, text, **kwargs)
    await state.update_data(last_bot_message_id=msg.message_id)
    return msg

def get_quantity_kb(idx, quantity=1):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="➖", callback_data=f"decrease_{idx}_{quantity}"),
                InlineKeyboardButton(text=str(quantity), callback_data="noop"),
                InlineKeyboardButton(text="➕", callback_data=f"increase_{idx}_{quantity}")
            ],
            [InlineKeyboardButton(text="Добавить в корзину", callback_data=f"addcart_{idx}_{quantity}")],
            [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_price_range")]
        ]
    )

def get_delivery_price(region, address, date, time):
    hour = int(time.split(":")[0]) if time else 12
    if region == "г. Тосно":
        if 22 <= hour or hour < 9:
            return 500
        return 250
    elif region == "Тосненский район":
        return 400
    elif region == "Ленинградская область":
        return 600
    elif region == "г. Санкт-Петербург":
        return 800
    return 0

@dp.message(Command("start"))
async def start(msg: Message):
    if msg.from_user.id not in users:
        users.add(msg.from_user.id)
        save_users()
    await msg.answer(
        "Добро пожаловать в магазин цветов! Мы рады видеть Вас здесь.\nВыберите действие:",
        reply_markup=main_menu
    )

@dp.message(lambda m: m.text == "🌸 Каталог")
async def menu_catalog(msg: Message, state: FSMContext):
    await msg.answer("Выберите категорию:", reply_markup=category_kb_with_back)
    await state.set_state("waiting_for_catalog_category")

@dp.message(lambda m: m.text == "ℹ️ О нас")
async def about(msg: Message):
    await msg.answer('- Круглосуточная доставка цветов по г. Тосно, Тосненскому району и Санкт-Петербургу \n-Сотрудничаем напрямую с плантациями Ленинградской области и Краснодарского края\n-Осуществляем корпоративные заказы (возможно заключение договора)\n-Полностью дистанционное оформление заказа\n\nОплата\nПосле согласования всех нюансов заказа, необходимо произвести оплату.  Если заказан товар из наличия с экспресс доставкой, оплата возможна при получении наличными или переводом.\nДоставка\nДОСТАВКА осуществляется 24 часа! Доставка по г. Тосно от 250₽ Доставка по Тосненскому району, Ленинградской области, г. Санкт-Петербургу согласна тарифам Яндекса или другой службы доставки.  Временной интервал для доставки по Тосно - 30 минут По Ленинградской обл��сти и г. Санкт-Петербургу - 2-3 часа Экспресс доставка (только по г. Тосно) - доставка товара из наличия в течение часа с момента заказа - от 250₽ руб. Ночной тариф (с 22-9:00) по Тосно - от 500₽\nВозврат\n❗️Проверяйте качество цветов при получении Цветы являются живым товаром.  В соответствии с Законом Российской Федерации «О защите прав потребителей» от 07.02.1992 № 2300-1 и Постановлением Правительства Российской Федерации от 19.01.1998 № 55 срезанные цветы и горшечные растения обмену и возврату не подлежат (указаны в Перечне непродовольственных товаров надлежащего качества, не подлежащих возврату или обмену). Покупатель имеет право отказаться от получения товара в момент доставки, если доставлен товар ненадлежащего качес��ва (на основании п.3 ст. 497 ГК РФ, статья 21 Закона "О защите прав потребителей").')

@dp.message(lambda m: m.text == "📱 Соц.сети")
async def contacts(msg: Message):
    await msg.answer("Телефон: +79201860779\nVK: https://vk.com/bar_flower\nWhatsApp:https://clck.ru/3Nh8rH")

@dp.message(StateFilter("waiting_for_catalog_category"))
async def show_category(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    if msg.text not in CATEGORIES:
        await msg.answer("Пожалуйста, выберите категорию кнопкой.")
        return
    await state.update_data(selected_category=msg.text)
    ranges = PRICE_RANGES[msg.text]
    price_range_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label, _, _ in ranges] + [[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await msg.answer("Выберите диапазон цен:", reply_markup=price_range_kb)
    await state.set_state("waiting_for_price_range")

@dp.message(StateFilter("waiting_for_price_range"))
async def show_price_range(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Выберите категорию:", reply_markup=category_kb_with_back)
        await state.set_state("waiting_for_catalog_category")
        return
    data = await state.get_data()
    category = data.get("selected_category")
    ranges = PRICE_RANGES[category]
    selected = None
    for label, min_price, max_price in ranges:
        if msg.text == label:
            selected = (min_price, max_price)
            break
    if not selected:
        await msg.answer("Пожалуйста, выберите диапазон кнопкой.")
        return
    min_price, max_price = selected

    items = [
        (i, f) for i, f in enumerate(flowers)
        if f.get("category") == category and f.get("price") is not None
           and min_price <= int(f["price"]) <= max_price
    ]
    if not items:
        await msg.answer("Нет товаров в этом диапазоне.", reply_markup=main_menu)
        await state.clear()
        return

    product_message_ids = []
    for idx, f in items:
        kb = get_quantity_kb(idx)
        sent = await msg.answer_photo(
            f["photo"],
            caption=f"{f['emoji']} {f['name']}\nЦена: {f['price']} руб.",
            reply_markup=kb
        )
        product_message_ids.append(sent.message_id)
    await state.update_data(product_message_ids=product_message_ids)
    await state.set_state("waiting_for_price_range_back")

@dp.message(StateFilter("waiting_for_price_range_back"))
async def price_range_back(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        data = await state.get_data()
        category = data.get("selected_category")
        ranges = PRICE_RANGES[category]
        price_range_kb = ReplyKeyboardMarkup(
            keyboard=[[KeyboardButton(text=label)] for label, _, _ in ranges] + [[KeyboardButton(text="⬅️ Назад")]],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await msg.answer("Выберите диапазон цен:", reply_markup=price_range_kb)
        await state.set_state("waiting_for_price_range")
    else:
        await msg.answer("Пожалуйста, используйте кнопки.")

@dp.callback_query(F.data == "back_to_price_range")
async def back_to_price_range(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    category = data.get("selected_category")
    ranges = PRICE_RANGES[category]
    price_range_kb = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=label)] for label, _, _ in ranges] + [[KeyboardButton(text="⬅️ Назад")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    # Удаляем сообщения с товарами
    product_message_ids = data.get("product_message_ids", [])
    for mid in product_message_ids:
        with contextlib.suppress(Exception):
            await bot.delete_message(callback.from_user.id, mid)
    await callback.message.answer("Выберите диапазон цен:", reply_markup=price_range_kb)
    await state.set_state("waiting_for_price_range")
    await callback.answer()

@dp.callback_query(F.data.startswith("increase_"))
async def increase_quantity(callback: CallbackQuery):
    _, idx, quantity = callback.data.split("_")
    idx = int(idx)
    quantity = int(quantity) + 1
    await callback.message.edit_reply_markup(reply_markup=get_quantity_kb(idx, quantity))
    await callback.answer()

@dp.callback_query(F.data.startswith("decrease_"))
async def decrease_quantity(callback: CallbackQuery):
    _, idx, quantity = callback.data.split("_")
    idx = int(idx)
    quantity = max(1, int(quantity) - 1)
    await callback.message.edit_reply_markup(reply_markup=get_quantity_kb(idx, quantity))
    await callback.answer()

@dp.callback_query(F.data.startswith("addcart_"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext):
    _, idx, quantity = callback.data.split("_")
    idx = int(idx)
    quantity = int(quantity)
    user_id = callback.from_user.id
    carts.setdefault(user_id, [])
    for _ in range(quantity):
        carts[user_id].append(flowers[idx])
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕Добавить ещё", callback_data="add_more")],
            [InlineKeyboardButton(text="📋Перейти к оформлению", callback_data="checkout")]
        ]
    )
    await callback.message.answer(
        f"Товар добавлен в корзину. В корзине {len(carts[user_id])} товаров.\nЧто дальше?",
        reply_markup=kb
    )
    await callback.answer()

@dp.callback_query(F.data == "add_more")
async def add_more(callback: CallbackQuery, state: FSMContext):
    # Удаляем старые сообщения с товарами, если есть
    data = await state.get_data()
    product_message_ids = data.get("product_message_ids", [])
    for mid in product_message_ids:
        with contextlib.suppress(Exception):
            await bot.delete_message(callback.from_user.id, mid)
    await state.update_data(product_message_ids=[])
    # Сброс состояния на выбор категории
    await callback.message.answer("Выберите категорию:", reply_markup=category_kb_with_back)
    await state.set_state("waiting_for_catalog_category")
    await callback.answer()

@dp.callback_query(F.data == "checkout")
async def checkout(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    product_message_ids = data.get("product_message_ids", [])
    for mid in product_message_ids:
        with contextlib.suppress(Exception):
            await bot.delete_message(callback.from_user.id, mid)
    await send_disappearing_message(
        callback.from_user.id,
        "Выберите способ получения:",
        state,
        reply_markup=pickup_kb_with_back
    )
    await state.set_state(OrderFSM.choosing_delivery)

@dp.message(OrderFSM.choosing_delivery)
async def choose_delivery(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await send_disappearing_message(msg.from_user.id, "Главное меню:", state, reply_markup=main_menu)
        await state.clear()
        return
    if msg.text.startswith("Доставка"):
        await state.update_data(delivery="Доставка")
        await send_disappearing_message(msg.from_user.id, "Выберите регион доставки:", state, reply_markup=region_kb_with_back)
        await state.set_state(OrderFSM.choosing_region)
    elif msg.text.startswith("Самовывоз"):
        await state.update_data(delivery="Самовывоз", address="Самовывоз", region="г. Тосно")
        await send_disappearing_message(msg.from_user.id, "Введите дату (например, 2024-06-10, где ГГГГ-ММ-ДД):", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_date)
    else:
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, выберите способ получения кнопкой.", state)

@dp.message(OrderFSM.choosing_region)
async def choose_region(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await send_disappearing_message(msg.from_user.id, "Выберите способ получения:", state, reply_markup=pickup_kb_with_back)
        await state.set_state(OrderFSM.choosing_delivery)
        return
    if msg.text not in DELIVERY_REGIONS:
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, выберите регион кнопкой.", state)
        return
    await state.update_data(region=msg.text)
    await send_disappearing_message(msg.from_user.id, "Введите адрес доставки:", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(OrderFSM.entering_address)

@dp.message(OrderFSM.entering_address)
async def enter_address(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await send_disappearing_message(msg.from_user.id, "Выберите регион доставки:", state, reply_markup=region_kb_with_back)
        await state.set_state(OrderFSM.choosing_region)
        return
    await state.update_data(address=msg.text)
    await send_disappearing_message(msg.from_user.id, "Введите дату (например, 2024-06-10):", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(OrderFSM.choosing_date)

@dp.message(OrderFSM.choosing_date)
async def choose_date(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        data = await state.get_data()
        if data.get("delivery") == "Доставка":
            await send_disappearing_message(msg.from_user.id, "Введите адрес доставки:", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
            await state.set_state(OrderFSM.entering_address)
        else:
            await send_disappearing_message(msg.from_user.id, "Главное меню:", state, reply_markup=main_menu)
            await state.clear()
        return
    try:
        datetime.datetime.strptime(msg.text, "%Y-%m-%d")
        await state.update_data(date=msg.text)
        await send_disappearing_message(msg.from_user.id, "Введите время (например, 15:30):", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_time)
    except ValueError:
        await send_disappearing_message(msg.from_user.id, "Неверный формат даты. Введите в формате ГГГГ-ММ-ДД.", state)

@dp.message(OrderFSM.choosing_time)
async def choose_time(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await send_disappearing_message(msg.from_user.id, "Введите дату (например, 2024-06-10):", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_date)
        return
    try:
        datetime.datetime.strptime(msg.text, "%H:%M")
        await state.update_data(time=msg.text)
        phone_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Отправить номер", request_contact=True)],
                [KeyboardButton(text="⬅️ Назад")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, отправьте свой номер телефона для связи (в формате +79119523847):", state, reply_markup=phone_kb)
        await state.set_state(OrderFSM.entering_phone)
    except ValueError:
        await send_disappearing_message(msg.from_user.id, "Неверный формат времени. Введите в формате ЧЧ:ММ.", state)

@dp.message(OrderFSM.entering_phone)
async def get_phone(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await send_disappearing_message(msg.from_user.id, "Введите время (например, 15:30):", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.choosing_time)
        return
    phone = None
    if msg.contact and msg.contact.phone_number:
        phone = msg.contact.phone_number
    elif msg.text and msg.text.startswith("+") and len(msg.text) >= 10:
        phone = msg.text
    if not phone:
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, отправьте номер через кнопку или в формате +79991234567.", state)
        return
    await state.update_data(phone=phone)
    await send_disappearing_message(msg.from_user.id, "Пожалуйста, введите ваше имя:", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(OrderFSM.entering_name)

@dp.message(OrderFSM.entering_name)
async def get_name(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        phone_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Отправить номер", request_contact=True)],
                [KeyboardButton(text="⬅️ Назад")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, отправьте свой номер телефона для связи:", state, reply_markup=phone_kb)
        await state.set_state(OrderFSM.entering_phone)
        return
    await state.update_data(user_name=msg.text)
    card_kb = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )
    await send_disappearing_message(msg.from_user.id, "Желаете добавить открытку к заказу?", state, reply_markup=card_kb)
    await state.set_state(OrderFSM.asking_card)

@dp.message(OrderFSM.asking_card)
async def ask_card(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, введите ваше имя:", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.entering_name)
        return
    if msg.text == "Да":
        await send_disappearing_message(msg.from_user.id, "Введите текст для открытки:", state, reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(OrderFSM.entering_card_text)
    elif msg.text == "Нет":
        await state.update_data(card_text=None)
        await send_disappearing_message(msg.from_user.id, "Выберите способ оплаты:", state, reply_markup=payment_kb_with_back)
        await state.set_state(OrderFSM.choosing_payment)
    else:
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, выберите вариант кнопкой.", state)

@dp.message(OrderFSM.entering_card_text)
async def get_card_text(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        card_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
                [KeyboardButton(text="⬅️ Назад")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await send_disappearing_message(msg.from_user.id, "Желаете добавить открытку к заказу?", state, reply_markup=card_kb)
        await state.set_state(OrderFSM.asking_card)
        return
    await state.update_data(card_text=msg.text)
    await send_disappearing_message(msg.from_user.id, "Выберите способ оплаты:", state, reply_markup=payment_kb_with_back)
    await state.set_state(OrderFSM.choosing_payment)

@dp.message(OrderFSM.choosing_payment)
async def choose_payment(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        card_kb = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Да"), KeyboardButton(text="Нет")],
                [KeyboardButton(text="⬅️ Назад")]
            ],
            resize_keyboard=True,
            one_time_keyboard=True
        )
        await send_disappearing_message(msg.from_user.id, "Желаете добавить открытку к заказу?", state, reply_markup=card_kb)
        await state.set_state(OrderFSM.asking_card)
        return
    if msg.text not in ["Оплата при получении", "Оплата менеджеру"]:
        await send_disappearing_message(msg.from_user.id, "Пожалуйста, выберите способ оплаты кнопкой.", state)
        return
    await state.update_data(payment=msg.text)
    data = await state.get_data()
    user_id = msg.from_user.id
    cart = carts.get(user_id, [])
    total = sum(int(f["price"]) for f in cart)
    delivery_price = 0
    if data.get("delivery") == "Доставка":
        delivery_price = get_delivery_price(
            data.get("region"), data.get("address"), data.get("date"), data.get("time")
        )
        total += delivery_price

    cart_items = []
    for f in cart:
        cart_items.append(f"{f['emoji']} {f['name']} — {f['price']} руб.")
    
    card_text_line = f"\nОткрытка: {data.get('card_text', '')}" if data.get('card_text') else ""
    
    order_text = (
        f"Ваш заказ:\n"
        f"{chr(10).join(cart_items)}"
        + (f"\nДоставка: {delivery_price} руб." if delivery_price else "") +
        f"\nИтого к оплате: {total} руб."
        f"\nТелефон: {data.get('phone', '-')}"
        + card_text_line
        + "\n\nПодтвердите заказ?"
    )
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Подтвердить", callback_data="confirm_order")],
            [InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_order")]
        ]
    )
    await send_disappearing_message(user_id, order_text, state, reply_markup=kb)
    await state.update_data(total=total, delivery_price=delivery_price, cart=cart)
    await state.set_state(OrderFSM.waiting_for_order_confirm)

@dp.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    msg = callback.message
    user_id = callback.from_user.id
    username = callback.from_user.username
    
    cart_items = []
    for f in data['cart']:
        cart_items.append(f"{f['emoji']} {f['name']} — {f['price']} руб.")
    
    card_text_line = f"\nОткрытка: {data.get('card_text', '')}" if data.get('card_text') else ""
    
    order_text = (
        f"Новый заказ!\n"
        f"Пользователь: {data.get('user_name', '-')}\n"
        f"Ник: @{username if username else '-'}\n"
        f"Товары:\n" +
        "\n".join(cart_items) +
        (f"\nДоставка: {data.get('delivery_price', 0)} руб." if data.get('delivery_price') else "") +
        f"\nИтого: {data.get('total', 0)} руб."
        f"\nТелефон: {data.get('phone', '-')}"
        + card_text_line +
        f"\nРегион: {data.get('region', '-')}" +
        f"\nСпособ: {data.get('delivery', '-')}\n"
        f"Адрес: {data.get('address', '-')}\n"
        f"Дата: {data.get('date', '-')}\n"
        f"Время: {data.get('time', '-')}\n"
        f"Оплата: {data.get('payment', '-')}"
    )
    
    # Отправляем заказ всем админам
    for admin_id in ADMINS:
        await bot.send_message(admin_id, order_text)
    
    # Отправляем подтверждение пользователю
    await send_disappearing_message(user_id, "Ваш заказ отправлен менеджеру! Спасибо!", state, reply_markup=main_menu)
    carts[user_id] = []
    await state.clear()

@dp.callback_query(F.data == "cancel_order")
async def cancel_order(callback: CallbackQuery, state: FSMContext):
    await send_disappearing_message(callback.from_user.id, "Заказ отменён.", state, reply_markup=main_menu)
    await state.clear()

# --- Остальной код (админка, рассылка, редактирование) оставьте как есть ---

@dp.message(Command("add"))
async def add_flower(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    await msg.answer("Отправьте фото товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_photo)

@dp.message(AddFlower.waiting_for_photo)
async def add_flower_photo(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    if not msg.photo:
        await msg.answer("Пожалуйста, отправьте фото.")
        return
    await state.update_data(photo=msg.photo[-1].file_id)
    await msg.answer("Введите название товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_name)

@dp.message(AddFlower.waiting_for_name)
async def add_flower_name(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Отправьте фото товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_photo)
        return
    await state.update_data(name=msg.text)
    await msg.answer("Введите цену:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_price)

@dp.message(AddFlower.waiting_for_price)
async def add_flower_price(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите название товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_name)
        return
    await state.update_data(price=msg.text)
    await msg.answer("Добавьте смайлик для товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(AddFlower.waiting_for_emoji)

@dp.message(AddFlower.waiting_for_emoji)
async def add_flower_emoji(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите цену:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_price)
        return
    await state.update_data(emoji=msg.text)
    await msg.answer("Выберите категорию:", reply_markup=category_kb_with_back)
    await state.set_state(AddFlower.waiting_for_category)

@dp.message(AddFlower.waiting_for_category)
async def add_flower_category(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Добавьте смайлик для товара:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(AddFlower.waiting_for_emoji)
        return
    if msg.text not in CATEGORIES:
        await msg.answer("Пожалуйста, выберите категорию кнопкой.")
        return
    data = await state.get_data()
    flowers.append({
        'photo': data['photo'],
        'name': data['name'],
        'price': data['price'],
        'emoji': data['emoji'],
        'category': msg.text
    })
    save_flowers()
    await msg.answer("Товар добавлен в каталог!", reply_markup=main_menu)
    await state.clear()

@dp.message(Command("edit"))
async def edit_catalog(msg: Message):
    if not is_admin(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    if not flowers:
        await msg.answer("Каталог пуст.")
        return
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"{f['emoji']} {f['name']}", callback_data=f"edit_{i}")]
            for i, f in enumerate(flowers)
        ]
    )
    await msg.answer("Выберите товар для редактирования или удаления:", reply_markup=kb)

@dp.callback_query(F.data.startswith("edit_"))
async def choose_edit(callback: CallbackQuery, state: FSMContext):
    idx = int(callback.data.split("_")[1])
    await state.update_data(idx=idx)
    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Удалить", callback_data="edit_delete")],
            [InlineKeyboardButton(text="Изменить", callback_data="edit_change")]
        ]
    )
    flower = flowers[idx]
    await callback.message.answer(
        f"Товар: {flower['emoji']} {flower['name']} — {flower['price']} руб.\nЧто сделать?",
        reply_markup=kb
    )
    await state.set_state(EditFlowerFSM.waiting_for_action)

@dp.callback_query(F.data == "edit_delete")
async def delete_flower(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    idx = data["idx"]
    flower = flowers.pop(idx)
    save_flowers()
    await callback.message.answer(f"Товар {flower['name']} удалён.", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.callback_query(F.data == "edit_change")
async def change_flower(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите новое название (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(EditFlowerFSM.waiting_for_new_name)

@dp.message(EditFlowerFSM.waiting_for_new_name)
async def edit_name(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    await state.update_data(new_name=msg.text)
    await msg.answer("Введите новую цену (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(EditFlowerFSM.waiting_for_new_price)

@dp.message(EditFlowerFSM.waiting_for_new_price)
async def edit_price(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите новое название (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(EditFlowerFSM.waiting_for_new_name)
        return
    await state.update_data(new_price=msg.text)
    await msg.answer("Введите новый смайлик (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(EditFlowerFSM.waiting_for_new_emoji)

@dp.message(EditFlowerFSM.waiting_for_new_emoji)
async def edit_emoji(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите новую цену (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(EditFlowerFSM.waiting_for_new_price)
        return
    await state.update_data(new_emoji=msg.text)
    await msg.answer("Выберите новую категорию (или '-' чтобы не менять):", reply_markup=category_kb_with_back)
    await state.set_state(EditFlowerFSM.waiting_for_new_category)

@dp.message(EditFlowerFSM.waiting_for_new_category)
async def edit_category(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Введите новый смайлик (или '-' чтобы не менять):", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
        await state.set_state(EditFlowerFSM.waiting_for_new_emoji)
        return
    data = await state.get_data()
    idx = data["idx"]
    if data["new_name"] != "-":
        flowers[idx]["name"] = data["new_name"]
    if data["new_price"] != "-":
        flowers[idx]["price"] = data["new_price"]
    if data["new_emoji"] != "-":
        flowers[idx]["emoji"] = data["new_emoji"]
    if msg.text in CATEGORIES:
        flowers[idx]["category"] = msg.text
    save_flowers()
    await msg.answer("Товар обновлён!", reply_markup=ReplyKeyboardRemove())
    await state.clear()

@dp.message(Command("broadcast"))
async def start_broadcast(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await msg.answer("Доступ запрещён.")
        return
    await msg.answer("Введите текст рассылки:", reply_markup=with_back_kb(ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)))
    await state.set_state(BroadcastFSM.waiting_for_text)

@dp.message(StateFilter(BroadcastFSM.waiting_for_text))
async def do_broadcast(msg: Message, state: FSMContext):
    if msg.text == "⬅️ Назад":
        await msg.answer("Главное меню:", reply_markup=main_menu)
        await state.clear()
        return
    text = msg.text
    count = 0
    for uid in users:
        try:
            await bot.send_message(uid, text)
            count += 1
        except Exception:
            pass
    await msg.answer(f"Рассылка завершена. Отправлено {count} пользователям.")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
