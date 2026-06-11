import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

import database as db
from channel_stats import update_channel_stats

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

BOT_TOKEN  = os.environ["BOT_TOKEN"]
CHANNEL_ID = int(os.environ["CHANNEL_ID"])   # -100xxxxxxxxxx

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ── FSM states ────────────────────────────────────────────────────────────────

class SaleFlow(StatesGroup):
    choose_event = State()
    choose_item  = State()
    confirm      = State()

class AddItemFlow(StatesGroup):
    name   = State()
    color  = State()
    size   = State()
    price  = State()
    stock  = State()

class AddEventFlow(StatesGroup):
    name = State()

class StockFlow(StatesGroup):
    choose_item = State()
    enter_qty   = State()


# ── helpers ───────────────────────────────────────────────────────────────────

def kb(*rows):
    """rows = list of list of (text, callback_data)"""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
            for row in rows
        ]
    )


def item_label(item) -> str:
    parts = [item["name"]]
    if item["color"]:
        parts.append(item["color"])
    if item["size"]:
        parts.append(item["size"])
    parts.append(f"[{item['stock']} шт]")
    return " · ".join(parts)


def event_keyboard():
    events = db.get_all_events()
    rows = [[( e["name"], f"event:{e['id']}" )] for e in events]
    rows.append([("❌ Отмена", "cancel")])
    return kb(*rows)


def items_keyboard(page=0, page_size=8):
    items = [i for i in db.get_all_items() if i["stock"] > 0]
    start = page * page_size
    chunk = items[start: start + page_size]

    rows = []
    for item in chunk:
        rows.append([(item_label(item), f"item:{item['id']}")])

    nav = []
    if page > 0:
        nav.append(("⬅️", f"page:{page-1}"))
    if start + page_size < len(items):
        nav.append(("➡️", f"page:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([("❌ Отмена", "cancel")])
    return kb(*rows)


def all_items_keyboard(page=0, page_size=8):
    """Все позиции, включая с нулевым остатком (для пополнения)"""
    items = db.get_all_items()
    start = page * page_size
    chunk = items[start: start + page_size]

    rows = []
    for item in chunk:
        rows.append([(item_label(item), f"stockitem:{item['id']}")])

    nav = []
    if page > 0:
        nav.append(("⬅️", f"stockpage:{page-1}"))
    if start + page_size < len(items):
        nav.append(("➡️", f"stockpage:{page+1}"))
    if nav:
        rows.append(nav)

    rows.append([("❌ Отмена", "cancel")])
    return kb(*rows)


async def push_stats():
    await update_channel_stats(bot, CHANNEL_ID)


# ── main menu ─────────────────────────────────────────────────────────────────

MAIN_KB = kb(
    [("🛍 Продал", "sell"), ("📦 Остатки", "view_stock")],
    [("➕ Добавить позицию", "add_item"), ("🎪 Добавить мероприятие", "add_event")],
    [("📊 Обновить статистику", "refresh_stats")],
)


@dp.message(Command("start", "menu"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Merch-бот Водопады. Выбери действие:", reply_markup=MAIN_KB)


@dp.callback_query(F.data == "cancel")
async def cb_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Отменено.", reply_markup=None)
    await call.message.answer("Выбери действие:", reply_markup=MAIN_KB)
    await call.answer()


# ── SELL flow ─────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "sell")
async def cb_sell_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SaleFlow.choose_event)
    await call.message.edit_text("Выбери мероприятие:", reply_markup=event_keyboard())
    await call.answer()


@dp.callback_query(SaleFlow.choose_event, F.data.startswith("event:"))
async def cb_sell_event(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(":")[1])
    await state.update_data(event_id=event_id, page=0)
    await state.set_state(SaleFlow.choose_item)
    await call.message.edit_text("Выбери позицию:", reply_markup=items_keyboard(0))
    await call.answer()


@dp.callback_query(SaleFlow.choose_item, F.data.startswith("page:"))
async def cb_sell_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(":")[1])
    await state.update_data(page=page)
    await call.message.edit_reply_markup(reply_markup=items_keyboard(page))
    await call.answer()


@dp.callback_query(SaleFlow.choose_item, F.data.startswith("item:"))
async def cb_sell_item(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[1])
    item = db.get_item(item_id)
    await state.update_data(item_id=item_id)
    await state.set_state(SaleFlow.confirm)

    data = await state.get_data()
    events = {e["id"]: e["name"] for e in db.get_all_events()}
    event_name = events.get(data["event_id"], "?")

    text = (
        f"Подтверди продажу:\n\n"
        f"Позиция: <b>{item_label(item)}</b>\n"
        f"Мероприятие: <b>{event_name}</b>\n"
        f"Цена: <b>{item['price']:,} ₽</b>".replace(",", " ")
    )
    await call.message.edit_text(
        text,
        parse_mode="HTML",
        reply_markup=kb(
            [("✅ Подтвердить", "confirm_sale"), ("❌ Отмена", "cancel")]
        )
    )
    await call.answer()


@dp.callback_query(SaleFlow.confirm, F.data == "confirm_sale")
async def cb_sell_confirm(call: CallbackQuery, state: FSMContext):
    data  = await state.get_data()
    item  = db.get_item(data["item_id"])
    sold_by = call.from_user.first_name or call.from_user.username or "?"

    db.record_sale(
        item_id=data["item_id"],
        event_id=data["event_id"],
        quantity=1,
        price=item["price"],
        sold_by=sold_by
    )
    await state.clear()

    await call.message.edit_text(
        f"✅ Продажа записана: <b>{item['name']}</b>\nОсталось: {item['stock'] - 1} шт",
        parse_mode="HTML",
        reply_markup=None
    )
    await call.message.answer("Выбери действие:", reply_markup=MAIN_KB)
    await call.answer()

    await push_stats()


# ── VIEW STOCK ────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "view_stock")
async def cb_view_stock(call: CallbackQuery, state: FSMContext):
    rows = db.get_stats_by_item()
    lines = ["📦 <b>Остатки</b>\n"]

    current_name = None
    for r in rows:
        if r["name"] != current_name:
            if current_name:
                lines.append("")
            lines.append(f"<b>{r['name']}</b>")
            current_name = r["name"]
        variant_parts = []
        if r["color"]:
            variant_parts.append(r["color"])
        if r["size"]:
            variant_parts.append(r["size"])
        variant = " / ".join(variant_parts) if variant_parts else "—"
        stock_str = str(r["stock"]) if r["stock"] > 0 else "0 ⚠️"
        lines.append(f"  {variant}: {stock_str} шт (продано {r['sold']})")

    await call.message.edit_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=kb(
            [("🔧 Обновить остаток", "update_stock"), ("◀️ Меню", "back_menu")]
        )
    )
    await call.answer()


@dp.callback_query(F.data == "back_menu")
async def cb_back_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Выбери действие:", reply_markup=MAIN_KB)
    await call.answer()


# ── UPDATE STOCK flow ─────────────────────────────────────────────────────────

@dp.callback_query(F.data == "update_stock")
async def cb_update_stock_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(StockFlow.choose_item)
    await call.message.edit_text("Выбери позицию для обновления остатка:", reply_markup=all_items_keyboard(0))
    await call.answer()


@dp.callback_query(StockFlow.choose_item, F.data.startswith("stockpage:"))
async def cb_stock_page(call: CallbackQuery, state: FSMContext):
    page = int(call.data.split(":")[1])
    await call.message.edit_reply_markup(reply_markup=all_items_keyboard(page))
    await call.answer()


@dp.callback_query(StockFlow.choose_item, F.data.startswith("stockitem:"))
async def cb_stock_item(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[1])
    item = db.get_item(item_id)
    await state.update_data(item_id=item_id)
    await state.set_state(StockFlow.enter_qty)
    await call.message.edit_text(
        f"<b>{item_label(item)}</b>\n\nВведи новый остаток (целое число):",
        parse_mode="HTML", reply_markup=None
    )
    await call.answer()


@dp.message(StockFlow.enter_qty)
async def msg_stock_qty(message: Message, state: FSMContext):
    try:
        qty = int(message.text.strip())
        assert qty >= 0
    except Exception:
        await message.answer("Нужно целое число ≥ 0")
        return

    data = await state.get_data()
    db.set_stock(data["item_id"], qty)
    item = db.get_item(data["item_id"])
    await state.clear()

    await message.answer(
        f"✅ Остаток обновлён: <b>{item_label(item)}</b>",
        parse_mode="HTML",
        reply_markup=MAIN_KB
    )
    await push_stats()


# ── ADD ITEM flow ─────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "add_item")
async def cb_add_item(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddItemFlow.name)
    await call.message.edit_text(
        "Новая позиция.\n\nВведи название (например: Футболка Депрессия):",
        reply_markup=None
    )
    await call.answer()


@dp.message(AddItemFlow.name)
async def msg_item_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddItemFlow.color)
    await message.answer("Цвет (или «-» если не нужен):")


@dp.message(AddItemFlow.color)
async def msg_item_color(message: Message, state: FSMContext):
    val = message.text.strip()
    await state.update_data(color=val if val != "-" else "")
    await state.set_state(AddItemFlow.size)
    await message.answer("Размер (или «-» если не нужен):")


@dp.message(AddItemFlow.size)
async def msg_item_size(message: Message, state: FSMContext):
    val = message.text.strip()
    await state.update_data(size=val if val != "-" else "")
    await state.set_state(AddItemFlow.price)
    await message.answer("Цена в рублях (число):")


@dp.message(AddItemFlow.price)
async def msg_item_price(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip())
        assert price > 0
    except Exception:
        await message.answer("Нужно целое число > 0")
        return
    await state.update_data(price=price)
    await state.set_state(AddItemFlow.stock)
    await message.answer("Начальный остаток (число):")


@dp.message(AddItemFlow.stock)
async def msg_item_stock(message: Message, state: FSMContext):
    try:
        stock = int(message.text.strip())
        assert stock >= 0
    except Exception:
        await message.answer("Нужно целое число ≥ 0")
        return

    data = await state.get_data()
    db.add_item(data["name"], data.get("size"), data.get("color"), data["price"], stock)
    await state.clear()

    await message.answer(
        f"✅ Позиция добавлена:\n<b>{data['name']}</b> | {data.get('color','')} | {data.get('size','')} | {data['price']} ₽ | {stock} шт",
        parse_mode="HTML",
        reply_markup=MAIN_KB
    )
    await push_stats()


# ── ADD EVENT flow ────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "add_event")
async def cb_add_event(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddEventFlow.name)
    await call.message.edit_text("Введи название мероприятия:", reply_markup=None)
    await call.answer()


@dp.message(AddEventFlow.name)
async def msg_event_name(message: Message, state: FSMContext):
    name = message.text.strip()
    db.add_event(name)
    await state.clear()
    await message.answer(f"✅ Мероприятие «{name}» добавлено.", reply_markup=MAIN_KB)


# ── REFRESH STATS ─────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "refresh_stats")
async def cb_refresh_stats(call: CallbackQuery, state: FSMContext):
    await call.answer("Обновляю...")
    await push_stats()
    await call.message.answer("✅ Статистика обновлена в канале.", reply_markup=MAIN_KB)


# ── startup ───────────────────────────────────────────────────────────────────

async def main():
    db.init_db()
    db.seed_initial_data()
    log.info("DB ready. Starting polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
