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
    add("Футболка", "VODOPADY серая",            TS, 2000, [0, 0, 4, 2])
    add("Футболка", "Депрессия бело-зеленая",    TS, 2000, [0, 0, 0, 4])
    add("Футболка", "Депрессия сливочно-розовая",TS, 2000, [0, 0, 0, 6])
    add("Футболка", "Депрессия черно-зеленая",   TS, 2000, [0, 1, 0, 0])
    add("Футболка", "Депрессия черно-розовая",   TS, 2000, [0, 1, 2, 3])

    add("Кепка", "розовая",    [None], 2000, [10])
    add("Кепка", "серая",      [None], 2000, [10])
    add("Кепка", "фиолетовая", [None], 2000, [5])
    add("Кепка", "желтая",     [None], 2000, [5])

    add("Стикерпак", "белый",   [None], 300, [6])
    add("Стикерпак", "красный", [None], 300, [50])

    # Размеры носков: [ЖЕН, МУЖ]
    SOCK = ["ЖЕН", "МУЖ"]
    add("Носки", "Травмы",  SOCK, 400, [0, 0])
    add("Носки", "Хоупкор", SOCK, 400, [50, 50])

    add("Жетон", "Хоупкор",   [None], 1000, [30])
    add("Жетон", "Депрессия", [None], 1000, [3])

    c.executemany(
        "INSERT INTO items (category, subgroup, size, price, stock) VALUES (?,?,?,?,?)",
        items
    )

    events = [("Концерт",), ("Маркет",)]
    c.executemany("INSERT INTO events (name) VALUES (?)", events)

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


# ---------- events ----------

def get_all_events():
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM events WHERE active=1 ORDER BY name"
    ).fetchall()
    conn.close()
    return rows


def add_event(name):
    conn = get_conn()
    conn.execute("INSERT INTO events (name) VALUES (?)", (name,))
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
