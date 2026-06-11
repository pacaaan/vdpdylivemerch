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
            name TEXT NOT NULL,
            size TEXT,
            color TEXT,
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
            sold_at TEXT NOT NULL,
            FOREIGN KEY (item_id) REFERENCES items(id),
            FOREIGN KEY (event_id) REFERENCES events(id)
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

    items = [
        ("Футболка VODOPADY", "XL",   "Серая",         2000, 2),
        ("Футболка VODOPADY", "XXL",  "Серая",         2000, 2),
        ("Футболка Депрессия", "M",   "Сливочная",     2000, 0),
        ("Футболка Депрессия", "L",   "Сливочная",     2000, 0),
        ("Футболка Депрессия", "XL",  "Сливочная",     2000, 0),
        ("Футболка Депрессия", "XXL", "Сливочная",     2000, 0),
        ("Футболка Депрессия", "M",   "Белая",         2000, 0),
        ("Футболка Депрессия", "L",   "Белая",         2000, 0),
        ("Футболка Депрессия", "XL",  "Белая",         2000, 0),
        ("Футболка Депрессия", "XXL", "Белая",         2000, 0),
        ("Футболка Депрессия", "M",   "Черно-зеленая", 2000, 0),
        ("Футболка Депрессия", "L",   "Черно-зеленая", 2000, 0),
        ("Футболка Депрессия", "XL",  "Черно-зеленая", 2000, 0),
        ("Футболка Депрессия", "XXL", "Черно-зеленая", 2000, 0),
        ("Футболка Депрессия", "M",   "Черно-розовая", 2000, 0),
        ("Футболка Депрессия", "L",   "Черно-розовая", 2000, 0),
        ("Футболка Депрессия", "XL",  "Черно-розовая", 2000, 0),
        ("Футболка Депрессия", "XXL", "Черно-розовая", 2000, 0),
        ("Кепка ХОУПКОР",     None,  "Серая",         2000, 10),
        ("Кепка ХОУПКОР",     None,  "Фиолетовая",    2000, 5),
        ("Кепка ХОУПКОР",     None,  "Розовая",       2000, 10),
        ("Кепка ХОУПКОР",     None,  "Желтая",        2000, 5),
        ("Носки ХОУПКОР",     None,  "Женские",       400,  50),
        ("Носки ХОУПКОР",     None,  "Мужские",       400,  50),
        ("Жетон Депрессия",   None,  None,            1000, 0),
        ("Жетон ХОУПКОР",     None,  None,            1000, 0),
        ("Стикерпак",         None,  "Белый",         300,  0),
        ("Стикерпак",         None,  "Красный",       300,  0),
    ]

    c.executemany(
        "INSERT INTO items (name, size, color, price, stock) VALUES (?,?,?,?,?)",
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
        "SELECT * FROM items WHERE active=1 ORDER BY name, color, size"
    ).fetchall()
    conn.close()
    return rows


def get_item(item_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM items WHERE id=?", (item_id,)).fetchone()
    conn.close()
    return row


def add_item(name, size, color, price, stock):
    conn = get_conn()
    conn.execute(
        "INSERT INTO items (name, size, color, price, stock) VALUES (?,?,?,?,?)",
        (name, size or None, color or None, price, stock)
    )
    conn.commit()
    conn.close()


def update_stock(item_id, delta):
    """delta negative = продажа, positive = пополнение"""
    conn = get_conn()
    conn.execute(
        "UPDATE items SET stock = MAX(0, stock + ?) WHERE id=?",
        (delta, item_id)
    )
    conn.commit()
    conn.close()


def set_stock(item_id, stock):
    conn = get_conn()
    conn.execute("UPDATE items SET stock=? WHERE id=?", (stock, item_id))
    conn.commit()
    conn.close()


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
        SELECT i.name, i.color, i.size, i.stock,
               COALESCE(SUM(s.quantity), 0) AS sold
        FROM items i
        LEFT JOIN sales s ON s.item_id = i.id
        WHERE i.active=1
        GROUP BY i.id
        ORDER BY i.name, i.color, i.size
    """).fetchall()
    conn.close()
    return rows


def get_last_sales(limit=10):
    conn = get_conn()
    rows = conn.execute("""
        SELECT i.name, i.color, i.size, s.quantity, s.price,
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
