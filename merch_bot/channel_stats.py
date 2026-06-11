"""
Обновляет (или создаёт) три сообщения в канале статистики:
  revenue — выручка итого + по мероприятиям
  stock   — остатки и кол-во продаж по позициям
  recent  — последние 10 продаж
"""

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest
from database import (
    get_stats_overall, get_stats_by_event,
    get_stats_by_item, get_last_sales,
    get_channel_message_id, set_channel_message_id
)
from datetime import datetime


def _variant(category, subgroup, size):
    parts = [category, subgroup]
    if size:
        parts.append(size)
    return " · ".join(parts)


def _fmt_revenue() -> str:
    overall = get_stats_overall()
    by_event = get_stats_by_event()

    lines = [
        "💰 <b>ВЫРУЧКА</b>",
        "",
        f"Итого продаж:  <b>{overall['units']} шт</b>",
        f"Итого выручка: <b>{overall['revenue']:,} ₽</b>".replace(",", " "),
        "",
        "<b>По мероприятиям:</b>",
    ]
    for row in by_event:
        lines.append(
            f"  {row['event']}: {row['units']} шт → {row['revenue']:,} ₽".replace(",", " ")
        )

    lines += ["", f"<i>Обновлено: {datetime.now().strftime('%d.%m %H:%M')}</i>"]
    return "\n".join(lines)


def _fmt_stock() -> str:
    rows = get_stats_by_item()

    lines = ["📦 <b>ОСТАТКИ И ПРОДАЖИ</b>", ""]

    current_cat = None
    for r in rows:
        if r["category"] != current_cat:
            if current_cat is not None:
                lines.append("")
            lines.append(f"<b>{r['category']}</b>")
            current_cat = r["category"]

        label = r["subgroup"]
        if r["size"]:
            label += f" · {r['size']}"

        stock = r["stock"]
        sold = r["sold"]
        stock_str = f"<b>{stock}</b>" if stock > 0 else "<b>0</b> ⚠️"
        lines.append(f"  {label}: осталось {stock_str}, продано {sold}")

    lines += ["", f"<i>Обновлено: {datetime.now().strftime('%d.%m %H:%M')}</i>"]
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
