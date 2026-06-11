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
CHANNEL_ID = int(os.environ["CHANNEL_ID"])

bot = Bot(token=BOT_TOKEN)
dp  = Dispatcher(storage=MemoryStorage())


# ── FSM states ────────────────────────────────────────────────────────────────

class SaleFlow(StatesGroup):
    choose_event    = State()
    choose_type     = State()
    choose_subgroup = State()
    choose_size     = State()
    enter_amount    = State()
    confirm         = State()

class AddItemFlow(StatesGroup):
    category = State()
    subgroup = State()
    size     = State()
    price    = State()
    stock    = State()

class AddEventFlow(StatesGroup):
    name = State()

class StockFlow(StatesGroup):
    choose_item = State()
    enter_qty   = State()


# ── helpers ───────────────────────────────────────────────────────────────────

def kb(*rows):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=t, callback_data=d) for t, d in row]
            for row in rows
        ]
    )


def item_label(item) -> str:
    parts = [item["category"], item["subgroup"]]
    if item["size"]:
        parts.append(item["size"])
    parts.append(f"[{item['stock']}]")
    return " · ".join(parts)


def variant_label(item) -> str:
    parts = [item["category"], item["subgroup"]]
    if item["size"]:
        parts.append(item["size"])
    return " · ".join(parts)


def event_keyboard():
    events = db.get_all_events()
    rows = [[(e["name"], f"event:{e['id']}")] for e in events]
    rows.append([("❌ Отмена", "cancel")])
    return kb(*rows)


def type_keyboard(cats):
    rows = [[(c, f"cat:{i}")] for i, c in enumerate(cats)]
    rows.append([("❌ Отмена", "cancel")])
    return kb(*rows)


def subgroup_keyboard(subs):
    rows = [[(s[0], f"sub:{i}")] for i, s in enumerate(subs)]
    rows.append([("⬅️ Назад", "back_types"), ("❌ Отмена", "cancel")])
    return kb(*rows)


def size_keyboard(sized):
    rows = [[(f"{size} [{stock}]", f"item:{iid}")] for (iid, size, stock) in sized]
    rows.append([("⬅️ Назад", "back_subs"), ("❌ Отмена", "cancel")])
    return kb(*rows)


def all_items_keyboard(page=0, page_size=8):
    items = db.get_all_items()
    start = page * page_size
    chunk = items[start: start + page_size]

    rows = [[(item_label(item), f"stockitem:{item['id']}")] for item in chunk]

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


MAIN_KB = kb(
    [("🛍 Продал", "sell"), ("💸 Скидка", "discount")],
    [("📦 Остатки", "view_stock")],
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


@dp.callback_query(F.data == "back_menu")
async def cb_back_menu(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Выбери действие:", reply_markup=MAIN_KB)
    await call.answer()


# ── SELL flow ─────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "sell")
async def cb_sell_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SaleFlow.choose_event)
    await state.update_data(mode="sell")
    await call.message.edit_text("Выбери мероприятие:", reply_markup=event_keyboard())
    await call.answer()


@dp.callback_query(F.data == "discount")
async def cb_discount_start(call: CallbackQuery, state: FSMContext):
    await state.set_state(SaleFlow.choose_event)
    await state.update_data(mode="discount")
    await call.message.edit_text("Скидка. Выбери мероприятие:", reply_markup=event_keyboard())
    await call.answer()


@dp.callback_query(SaleFlow.choose_event, F.data.startswith("event:"))
async def cb_sell_event(call: CallbackQuery, state: FSMContext):
    event_id = int(call.data.split(":")[1])
    cats = db.sell_get_categories()
    if not cats:
        await state.clear()
        await call.message.edit_text("Нет товара в наличии.", reply_markup=None)
        await call.message.answer("Выбери действие:", reply_markup=MAIN_KB)
        await call.answer()
        return
    await state.update_data(event_id=event_id, cats=cats)
    await state.set_state(SaleFlow.choose_type)
    await call.message.edit_text("Выбери тип товара:", reply_markup=type_keyboard(cats))
    await call.answer()


async def _show_types(call, state):
    data = await state.get_data()
    await state.set_state(SaleFlow.choose_type)
    await call.message.edit_text("Выбери тип товара:", reply_markup=type_keyboard(data["cats"]))


@dp.callback_query(SaleFlow.choose_type, F.data.startswith("cat:"))
async def cb_sell_type(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[1])
    data = await state.get_data()
    category = data["cats"][idx]
    subs = db.sell_get_subgroups(category)
    await state.update_data(category=category, subs=subs)
    await state.set_state(SaleFlow.choose_subgroup)
    await call.message.edit_text(f"{category} — выбери вариант:", reply_markup=subgroup_keyboard(subs))
    await call.answer()


@dp.callback_query(SaleFlow.choose_subgroup, F.data == "back_types")
async def cb_back_types(call: CallbackQuery, state: FSMContext):
    await _show_types(call, state)
    await call.answer()


@dp.callback_query(SaleFlow.choose_subgroup, F.data.startswith("sub:"))
async def cb_sell_subgroup(call: CallbackQuery, state: FSMContext):
    idx = int(call.data.split(":")[1])
    data = await state.get_data()
    subgroup, has_size = data["subs"][idx]
    category = data["category"]

    if has_size:
        sized = db.sell_get_sized_items(category, subgroup)
        await state.update_data(subgroup=subgroup, sized=sized)
        await state.set_state(SaleFlow.choose_size)
        await call.message.edit_text(
            f"{category} · {subgroup} — выбери размер:",
            reply_markup=size_keyboard(sized)
        )
    else:
        term = db.sell_get_terminal_item(category, subgroup)
        await _go_confirm(call, state, term["id"])
    await call.answer()


@dp.callback_query(SaleFlow.choose_size, F.data == "back_subs")
async def cb_back_subs(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    await state.set_state(SaleFlow.choose_subgroup)
    await call.message.edit_text(
        f"{data['category']} — выбери вариант:",
        reply_markup=subgroup_keyboard(data["subs"])
    )
    await call.answer()


@dp.callback_query(SaleFlow.choose_size, F.data.startswith("item:"))
async def cb_sell_size(call: CallbackQuery, state: FSMContext):
    item_id = int(call.data.split(":")[1])
    await _go_confirm(call, state, item_id)
    await call.answer()


async def _go_confirm(call, state, item_id):
    data = await state.get_data()
    await state.update_data(item_id=item_id)

    if data.get("mode") == "discount":
        item = db.get_item(item_id)
        await state.set_state(SaleFlow.enter_amount)
        await call.message.edit_text(
            f"<b>{variant_label(item)}</b>\n"
            f"Розница: {item['price']:,} ₽".replace(",", " ") +
            "\n\nВведи сумму продажи со скидкой (₽):",
            parse_mode="HTML", reply_markup=None
        )
    else:
        await _show_confirm(call.message, state, edit=True)


async def _show_confirm(msg, state, edit: bool):
    data = await state.get_data()
    item = db.get_item(data["item_id"])
    price = data.get("price") or item["price"]
    is_disc = data.get("mode") == "discount"

    events = {e["id"]: e["name"] for e in db.get_all_events()}
    event_name = events.get(data["event_id"], "?")

    if is_disc:
        price_line = (
            f"Цена: <s>{item['price']:,}</s> → <b>{price:,} ₽</b>".replace(",", " ")
        )
        title = "Подтверди продажу со скидкой:"
    else:
        price_line = f"Цена: <b>{price:,} ₽</b>".replace(",", " ")
        title = "Подтверди продажу:"

    text = (
        f"{title}\n\n"
        f"Позиция: <b>{variant_label(item)}</b>\n"
        f"Мероприятие: <b>{event_name}</b>\n"
        f"{price_line}\n"
        f"Остаток сейчас: {item['stock']} шт"
    )
    markup = kb([("✅ Подтвердить", "confirm_sale"), ("❌ Отмена", "cancel")])
    await state.set_state(SaleFlow.confirm)
    if edit:
        await msg.edit_text(text, parse_mode="HTML", reply_markup=markup)
    else:
        await msg.answer(text, parse_mode="HTML", reply_markup=markup)


@dp.message(SaleFlow.enter_amount)
async def msg_sale_amount(message: Message, state: FSMContext):
    try:
        price = int(message.text.strip().replace(" ", ""))
        assert price > 0
    except Exception:
        await message.answer("Нужно целое число > 0")
        return
    await state.update_data(price=price)
    await _show_confirm(message, state, edit=False)


@dp.callback_query(SaleFlow.confirm, F.data == "confirm_sale")
async def cb_sell_confirm(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    item = db.get_item(data["item_id"])
    price = data.get("price") or item["price"]
    sold_by = call.from_user.first_name or call.from_user.username or "?"

    db.record_sale(
        item_id=data["item_id"],
        event_id=data["event_id"],
        quantity=1,
        price=price,
        sold_by=sold_by
    )
    is_disc = data.get("mode") == "discount"
    await state.clear()

    tag = " (скидка)" if is_disc else ""
    await call.message.edit_text(
        f"✅ Продажа{tag} записана: <b>{variant_label(item)}</b>\n"
        f"Сумма: {price:,} ₽".replace(",", " ") +
        f"\nОсталось: {max(0, item['stock'] - 1)} шт",
        parse_mode="HTML", reply_markup=None
    )
    await call.message.answer("Выбери действие:", reply_markup=MAIN_KB)
    await call.answer()
    await push_stats()


# ── VIEW STOCK ────────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "view_stock")
async def cb_view_stock(call: CallbackQuery, state: FSMContext):
    rows = db.get_stats_by_item()
    lines = ["📦 <b>Остатки</b>\n"]

    current_cat = None
    for r in rows:
        if r["category"] != current_cat:
            if current_cat:
                lines.append("")
            lines.append(f"<b>{r['category']}</b>")
            current_cat = r["category"]
        label = r["subgroup"]
        if r["size"]:
            label += f" · {r['size']}"
        stock_str = str(r["stock"]) if r["stock"] > 0 else "0 ⚠️"
        lines.append(f"  {label}: {stock_str} шт (продано {r['sold']})")

    await call.message.edit_text(
        "\n".join(lines), parse_mode="HTML",
        reply_markup=kb([("🔧 Обновить остаток", "update_stock"), ("◀️ Меню", "back_menu")])
    )
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
        parse_mode="HTML", reply_markup=MAIN_KB
    )
    await push_stats()


# ── ADD ITEM flow ─────────────────────────────────────────────────────────────

@dp.callback_query(F.data == "add_item")
async def cb_add_item(call: CallbackQuery, state: FSMContext):
    await state.set_state(AddItemFlow.category)
    await call.message.edit_text(
        "Новая позиция.\n\nТип (Футболка / Кепка / Носки / Жетон / Стикерпак):",
        reply_markup=None
    )
    await call.answer()


@dp.message(AddItemFlow.category)
async def msg_item_category(message: Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AddItemFlow.subgroup)
    await message.answer("Вариант (цвет или название, например «Депрессия черно-зеленая»):")


@dp.message(AddItemFlow.subgroup)
async def msg_item_subgroup(message: Message, state: FSMContext):
    await state.update_data(subgroup=message.text.strip())
    await state.set_state(AddItemFlow.size)
    await message.answer("Размер (M/L/XL/XXL или ЖЕН/МУЖ). Если размера нет — отправь «-»:")


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
    db.add_item(data["category"], data["subgroup"], data.get("size"), data["price"], stock)
    await state.clear()

    size_txt = f" · {data.get('size')}" if data.get("size") else ""
    await message.answer(
        f"✅ Добавлено: <b>{data['category']} · {data['subgroup']}{size_txt}</b> | {data['price']} ₽ | {stock} шт",
        parse_mode="HTML", reply_markup=MAIN_KB
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
