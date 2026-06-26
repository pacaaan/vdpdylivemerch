"""
Обновляет (или создаёт) три сообщения в канале статистики:
  revenue — выручка итого + по мероприятиям + продано по группам
  stock   — остатки (только в наличии, сгруппировано)
  recent  — последние 10 продаж
"""

from collections import OrderedDict
from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from database import (
    get_stats_overall, get_stats_by_event, get_sales_by_category,
    get_sales_by_payment,
    get_stats_by_item, get_last_sales,
    get_channel_message_id, set_channel_message_id
)
from datetime import datetime

SIZE_ORDER = {"M": 1, "L": 2, "XL": 3, "XXL": 4, "ЖЕН": 1, "МУЖ": 2}
PAY_LABEL = {"cash": "Наличка", "transfer": "Перевод", "tip": "Чаевые"}


def _size_key(size):
    return SIZE_ORDER.get(size, 99)


def _variant(category, subgroup, size):
    parts = [category, subgroup]
    if size:
        parts.append(size)
    return " · ".join(parts)


def _fmt_revenue() -> str:
    overall = get_stats_overall()
    by_event = [r for r in get_stats_by_event() if r["units"] > 0]
    by_cat = get_sales_by_category()

    lines = [
        "💰 <b>ВЫРУЧКА</b>",
        "",
        f"Итого продаж:  <b>{overall['units']} шт</b>",
        f"Итого выручка: <b>{overall['revenue']:,} ₽</b>".replace(",", " "),
    ]

    if by_event:
        lines += ["", "<b>По мероприятиям:</b>"]
        for r in by_event:
            lines.append(
                f"  {r['event']}: {r['units']} шт → {r['revenue']:,} ₽".replace(",", " ")
            )

    if by_cat:
        lines += ["", "<b>Продано по группам:</b>"]
        for r in by_cat:
            lines.append(f"  {r['category']} — {r['units']} шт")

    by_pay = [r for r in get_sales_by_payment() if r["units"] > 0]
    if by_pay:
        lines += ["", "<b>По оплате:</b>"]
        for r in by_pay:
            label = PAY_LABEL.get(r["payment"], "—")
            lines.append(
                f"  {label}: {r['revenue']:,} ₽".replace(",", " ")
            )

    lines += ["", f"<i>Обновлено: {datetime.now().strftime('%d.%m %H:%M')}</i>"]
    return "\n".join(lines)


def _fmt_stock() -> str:
    rows = [r for r in get_stats_by_item() if r["stock"] > 0]

    # category -> list of rows
    cats = OrderedDict()
    for r in rows:
        cats.setdefault(r["category"], []).append(r)

    lines = ["📦 <b>ОСТАТКИ</b>", ""]

    for cat, items in cats.items():
        lines.append(f"<b>{cat}</b>")

        if cat == "Футболка":
            # подгруппа по бренду (первое слово subgroup): VODOPADY / Депрессия
            brands = OrderedDict()
            for r in items:
                parts = r["subgroup"].split(" ", 1)
                brand = parts[0]
                color = parts[1] if len(parts) > 1 else r["subgroup"]
                brands.setdefault(brand, OrderedDict())
                brands[brand].setdefault(color, []).append((r["size"], r["stock"]))

            for brand, colors in brands.items():
                lines.append(f"  <u>{brand}</u>")
                for color, sizes in colors.items():
                    sizes.sort(key=lambda x: _size_key(x[0]))
                    sz = ", ".join(f"{s} - {st}" for s, st in sizes)
                    lines.append(f"    {color.capitalize()} ({sz})")
        else:
            subs = OrderedDict()
            for r in items:
                subs.setdefault(r["subgroup"], []).append((r["size"], r["stock"]))

            for sub, sizes in subs.items():
                if len(sizes) == 1 and sizes[0][0] is None:
                    lines.append(f"  {sub} - {sizes[0][1]} шт")
                else:
                    sizes.sort(key=lambda x: _size_key(x[0]))
                    sz = ", ".join(f"{s} - {st}" for s, st in sizes)
                    lines.append(f"  {sub} ({sz})")

        lines.append("")

    lines += [f"<i>Обновлено: {datetime.now().strftime('%d.%m %H:%M')}</i>"]
    return "\n".join(lines)


def _fmt_recent() -> str:
    rows = get_last_sales(10)

    lines = ["🕓 <b>ПОСЛЕДНИЕ ПРОДАЖИ</b>", ""]

    if not rows:
        lines.append("Продаж пока нет.")
    else:
        for r in rows:
            name = _variant(r["category"], r["subgroup"], r["size"])
            dt = r["sold_at"][:16].replace("T", " ")
            by = f" [{r['sold_by']}]" if r["sold_by"] else ""
            total = r["quantity"] * r["price"]
            lines.append(
                f"{dt}{by} — {name} × {r['quantity']} = {total:,} ₽".replace(",", " ")
            )

    lines += ["", f"<i>Обновлено: {datetime.now().strftime('%d.%m %H:%M')}</i>"]
    return "\n".join(lines)


def format_stock() -> str:
    """Тот же текст остатков, что в канале — для кнопки «Остатки» в боте."""
    return _fmt_stock()


async def update_channel_stats(bot: Bot, channel_id: int):
    sections = {
        "revenue": _fmt_revenue,
        "stock":   _fmt_stock,
        "recent":  _fmt_recent,
    }

    for key, fmt_fn in sections.items():
        text = fmt_fn()
        msg_id = get_channel_message_id(key)

        if msg_id:
            try:
                await bot.edit_message_text(
                    chat_id=channel_id,
                    message_id=msg_id,
                    text=text,
                    parse_mode="HTML"
                )
                continue
            except TelegramBadRequest as e:
                if "message is not modified" in str(e):
                    continue
                msg_id = None

        msg = await bot.send_message(
            chat_id=channel_id,
            text=text,
            parse_mode="HTML"
        )
        set_channel_message_id(key, msg.message_id)
