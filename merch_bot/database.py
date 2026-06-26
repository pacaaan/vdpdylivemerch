import sqlite3
import os
from datetime import datetime

DB_PATH = os.getenv("DB_PATH", "merch.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT NOT NULL,
            subgroup TEXT NOT NULL,
            size TEXT,
            price INTEGER NOT NULL,
            stock INTEGER NOT NULL DEFAULT 0,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            event_date TEXT,
            active INTEGER NOT NULL DEFAULT 1
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER NOT NULL,
            event_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 1,
            price INTEGER NOT NULL,
            sold_by TEXT,
            sold_at TEXT NOT NULL
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS channel_messages (
            key TEXT PRIMARY KEY,
            message_id INTEGER
        )
    """)

    # миграция: добавить event_date, если база старая (на случай подключённого volume)
    cols = [r[1] for r in c.execute("PRAGMA table_info(events)").fetchall()]
    if "event_date" not in cols:
        c.execute("ALTER TABLE events ADD COLUMN event_date TEXT")

    conn.commit()
    conn.close()


def seed_initial_data():
    conn = get_conn()
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM items")
    if c.fetchone()[0] > 0:
        conn.close()
        return

    items = []

    def add(category, subgroup, sizes, price, stocks):
        for size, st in zip(sizes, stocks):
            items.append((category, subgroup, size, price, st))

    # Размеры футболок: [M, L, XL, XXL]
    TS = ["M", "L", "XL", "XXL"]
    add("Футболка", "VODOPADY серая",            TS, 2000, [0, 0, 3, 2])
    add("Футболка", "VODOPADY белая",            TS, 2000, [0, 5, 3, 2])
    add("Футболка", "VODOPADY сливочная",        TS, 2000, [0, 5, 3, 2])
    add("Футболка", "Депрессия сливочно-розовая",TS, 1700, [0, 0, 0, 4])
    add("Футболка", "Депрессия черно-розовая",   TS, 1700, [0, 0, 1, 2])

    add("Кепка", "розовый",    [None], 1700, [8])
    add("Кепка", "желтый",     [None], 1700, [4])
    add("Кепка", "серая",      [None], 1700, [5])
    add("Кепка", "фиолетовая", [None], 1700, [3])

    add("Стикерпак", "белый",   [None], 350, [6])
    add("Стикерпак", "красный", [None], 350, [50])

    # Размеры носков: [ЖЕН, МУЖ]
    SOCK = ["ЖЕН", "МУЖ"]
    add("Носки", "Хоупкор", SOCK, 350, [50, 50])

    add("Жетон", "Хоупкор",   [None], 1000, [28])
    add("Жетон", "Депрессия", [None], 1000, [3])

    add("Сумочка", "черный",     [None], 1500, [1])
    add("Сумочка", "бежевый",    [None], 1500, [1])
    add("Сумочка", "розовый",    [None], 1500, [1])
    add("Сумочка", "коричневый", [None], 1500, [1])
    add("Сумочка", "зеленый",    [None], 1500, [0])
    add("Сумочка", "синий",      [None], 1500, [0])

    c.executemany(
        "INSERT INTO items (category, subgroup, size, price, stock) VALUES (?,?,?,?,?)",
        items
    )

    # Стартовые мероприятия (новые добавляются через бота).
    # Каждое само исчезает из списка через 7 дней после даты.
    events = [
        ("Самара — Стереолето",  "2026-06-27"),
        ("Питер — Продай душу",  "2026-06-28"),
        ("Москва — Волнения",    "2026-07-04"),
        ("Владимир — Городской", "2026-07-05"),
        ("Балаково — Смена",     "2026-08-01"),
    ]
    c.executemany("INSERT INTO events (name, event_date) VALUES (?,?)", events)

    conn.commit()
    conn.close()


# ---------- items ----------

def get_all_items():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM items WHERE active=1 ORDER BY category, subgroup, size"
    ).fetchall()
    conn.close()
    return rows


def get_item(item_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    return row


def add_item(category, subgroup, size, price, stock):
    conn = get_conn()
    conn.execute(
        "INSERT INTO items (category, subgroup, size, price, stock) VALUES (?,?,?,?,?)",
        (category, subgroup, size or None, price, stock)
    )
    conn.commit()
    conn.close()


def set_stock(item_id, stock):
    conn = get_conn()
    conn.execute("UPDATE items SET stock=? WHERE id=?", (stock, item_id))
    conn.commit()
    conn.close()


def update_price(item_id, price):
    conn = get_conn()
    conn.execute("UPDATE items SET price=? WHERE id=?", (price, item_id))
    conn.commit()
    conn.close()


def set_active(item_id, active):
    conn = get_conn()
    conn.execute("UPDATE items SET active=? WHERE id=?", (1 if active else 0, item_id))
    conn.commit()
    conn.close()


def get_hidden_items():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM items WHERE active=0 ORDER BY category, subgroup, size"
    ).fetchall()
    conn.close()
    return rows


def get_categories_all():
    conn = get_conn()
    rows = conn.execute(
        "SELECT category FROM items WHERE active=1 GROUP BY category ORDER BY category"
    ).fetchall()
    conn.close()
    return [r["category"] for r in rows]


# ---------- sell navigation ----------

def sell_get_categories():
    conn = get_conn()
    rows = conn.execute("""
        SELECT category FROM items
        WHERE active=1
        GROUP BY category
        HAVING SUM(stock) > 0
        ORDER BY category
    """).fetchall()
    conn.close()
    return [r["category"] for r in rows]


def sell_get_subgroups(category):
    conn = get_conn()
    rows = conn.execute("""
        SELECT subgroup,
               MAX(CASE WHEN size IS NOT NULL THEN 1 ELSE 0 END) AS has_size
        FROM items
        WHERE active=1 AND category=?
        GROUP BY subgroup
        HAVING SUM(stock) > 0
        ORDER BY subgroup
    """, (category,)).fetchall()
    conn.close()
    return [(r["subgroup"], r["has_size"]) for r in rows]


def sell_get_sized_items(category, subgroup):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM items
        WHERE active=1 AND category=? AND subgroup=? AND size IS NOT NULL AND stock>0
        ORDER BY
          CASE size
            WHEN 'M' THEN 1 WHEN 'L' THEN 2 WHEN 'XL' THEN 3 WHEN 'XXL' THEN 4
            WHEN 'ЖЕН' THEN 1 WHEN 'МУЖ' THEN 2 ELSE 99 END
    """, (category, subgroup)).fetchall()
    conn.close()
    return [(r["id"], r["size"], r["stock"]) for r in rows]


def sell_get_terminal_item(category, subgroup):
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM items
        WHERE active=1 AND category=? AND subgroup=? AND size IS NULL AND stock>0
        LIMIT 1
    """, (category, subgroup)).fetchone()
    conn.close()
    return row


# ---------- catalog navigation (включая позиции с нулевым остатком) ----------

def cat_get_categories():
    conn = get_conn()
    rows = conn.execute(
        "SELECT category FROM items WHERE active=1 GROUP BY category ORDER BY category"
    ).fetchall()
    conn.close()
    return [r["category"] for r in rows]


def cat_get_subgroups(category):
    conn = get_conn()
    rows = conn.execute("""
        SELECT subgroup,
               MAX(CASE WHEN size IS NOT NULL THEN 1 ELSE 0 END) AS has_size
        FROM items
        WHERE active=1 AND category=?
        GROUP BY subgroup
        ORDER BY subgroup
    """, (category,)).fetchall()
    conn.close()
    return [(r["subgroup"], r["has_size"]) for r in rows]


def cat_get_sized_items(category, subgroup):
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM items
        WHERE active=1 AND category=? AND subgroup=? AND size IS NOT NULL
        ORDER BY
          CASE size
            WHEN 'M' THEN 1 WHEN 'L' THEN 2 WHEN 'XL' THEN 3 WHEN 'XXL' THEN 4
            WHEN 'ЖЕН' THEN 1 WHEN 'МУЖ' THEN 2 ELSE 99 END
    """, (category, subgroup)).fetchall()
    conn.close()
    return [(r["id"], r["size"], r["stock"]) for r in rows]


def cat_get_terminal_item(category, subgroup):
    conn = get_conn()
    row = conn.execute("""
        SELECT * FROM items
        WHERE active=1 AND category=? AND subgroup=? AND size IS NULL
        LIMIT 1
    """, (category, subgroup)).fetchone()
    conn.close()
    return row


# ---------- events ----------

def get_all_events():
    """Только мероприятия, дата которых не прошла больше чем на 7 дней."""
    conn = get_conn()
    rows = conn.execute("""
        SELECT * FROM events
        WHERE active=1
          AND event_date IS NOT NULL
          AND date(event_date) >= date('now', '-7 days')
        ORDER BY event_date
    """).fetchall()
    conn.close()
    return rows


def add_event(name, event_date):
    conn = get_conn()
    conn.execute(
        "INSERT INTO events (name, event_date) VALUES (?,?)",
        (name, event_date)
    )
    conn.commit()
    conn.close()


# ---------- sales ----------

def record_sale(item_id, event_id, quantity, price, sold_by):
    conn = get_conn()
    conn.execute(
        "INSERT INTO sales (item_id, event_id, quantity, price, sold_by, sold_at) VALUES (?,?,?,?,?,?)",
        (item_id, event_id, quantity, price, sold_by, datetime.now().isoformat())
    )
    conn.execute(
        "UPDATE items SET stock = MAX(0, stock - ?) WHERE id=?",
        (quantity, item_id)
    )
    conn.commit()
    conn.close()


def get_stats_overall():
    conn = get_conn()
    row = conn.execute("""
        SELECT
            COALESCE(SUM(s.quantity * s.price), 0) AS revenue,
            COALESCE(SUM(s.quantity), 0)            AS units
        FROM sales s
    """).fetchone()
    conn.close()
    return row


def get_stats_by_event():
    conn = get_conn()
    rows = conn.execute("""
        SELECT e.name AS event,
               COALESCE(SUM(s.quantity), 0) AS units,
               COALESCE(SUM(s.quantity * s.price), 0) AS revenue
        FROM events e
        LEFT JOIN sales s ON s.event_id = e.id
        GROUP BY e.id
        ORDER BY revenue DESC
    """).fetchall()
    conn.close()
    return rows


def get_sales_by_category():
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.category, SUM(s.quantity) AS units
        FROM sales s
        JOIN items i ON i.id = s.item_id
        GROUP BY i.category
        HAVING units > 0
        ORDER BY units DESC
    """).fetchall()
    conn.close()
    return rows


def get_stats_by_item():
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.category, i.subgroup, i.size, i.stock,
               COALESCE(SUM(s.quantity), 0) AS sold
        FROM items i
        LEFT JOIN sales s ON s.item_id = i.id
        WHERE i.active=1
        GROUP BY i.id
        ORDER BY i.category, i.subgroup, i.size
    """).fetchall()
    conn.close()
    return rows


def get_last_sales(limit=10):
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.category, i.subgroup, i.size, s.quantity, s.price,
               e.name AS event, s.sold_by, s.sold_at
        FROM sales s
        JOIN items i ON i.id = s.item_id
        JOIN events e ON e.id = s.event_id
        ORDER BY s.id DESC
        LIMIT ?
    """, (limit,)).fetchall()
    conn.close()
    return rows


def get_last_sale():
    conn = get_conn()
    row = conn.execute("""
        SELECT s.id, s.item_id, s.quantity, s.price, s.sold_by, s.sold_at,
               i.category, i.subgroup, i.size, i.stock,
               e.name AS event
        FROM sales s
        JOIN items i ON i.id = s.item_id
        JOIN events e ON e.id = s.event_id
        ORDER BY s.id DESC
        LIMIT 1
    """).fetchone()
    conn.close()
    return row


def get_sale(sale_id):
    conn = get_conn()
    row = conn.execute("""
        SELECT s.id, s.item_id, s.quantity, s.price,
               i.category, i.subgroup, i.size
        FROM sales s
        JOIN items i ON i.id = s.item_id
        WHERE s.id = ?
    """, (sale_id,)).fetchone()
    conn.close()
    return row


def delete_sale(sale_id):
    """Удаляет продажу и возвращает остаток на склад. Одно соединение."""
    conn = get_conn()
    row = conn.execute(
        "SELECT item_id, quantity FROM sales WHERE id=?", (sale_id,)
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE items SET stock = stock + ? WHERE id=?",
            (row["quantity"], row["item_id"])
        )
        conn.execute("DELETE FROM sales WHERE id=?", (sale_id,))
        conn.commit()
    conn.close()
    return row is not None


# ---------- channel message tracking ----------

def get_channel_message_id(key):
    conn = get_conn()
    row = conn.execute(
        "SELECT message_id FROM channel_messages WHERE key=?", (key,)
    ).fetchone()
    conn.close()
    return row["message_id"] if row else None


def set_channel_message_id(key, message_id):
    conn = get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO channel_messages (key, message_id) VALUES (?,?)",
        (key, message_id)
    )
    conn.commit()
    conn.close()
