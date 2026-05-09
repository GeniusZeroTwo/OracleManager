import sqlite3
import threading

DB_FILE = 'oracle_manager.db'
_db_lock = threading.Lock()

def get_conn():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;") 
    return conn

def init_db():
    with _db_lock:
        conn = get_conn()
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        tg_id TEXT PRIMARY KEY,
                        max_changes INTEGER DEFAULT 0,
                        used_changes INTEGER DEFAULT 0
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS user_instances (
                        tg_id TEXT,
                        ocid TEXT,
                        expire_date TEXT,
                        PRIMARY KEY (tg_id, ocid),
                        FOREIGN KEY(tg_id) REFERENCES users(tg_id) ON DELETE CASCADE
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS ip_cache (
                        ocid TEXT PRIMARY KEY,
                        ip_address TEXT
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS traffic_data (
                        account_name TEXT PRIMARY KEY,
                        limit_gb INTEGER DEFAULT 0,
                        usage_gb REAL DEFAULT -1,
                        update_time TEXT
                     )''')
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tg_id TEXT,
                        server_name TEXT,
                        old_ip TEXT,
                        new_ip TEXT,
                        change_time TEXT
                     )''')
        conn.commit()
        conn.close()

# ================= 业务接口 =================

def get_permissions():
    with _db_lock:
        conn = get_conn()
        c = conn.cursor()
        c.execute("SELECT tg_id, max_changes, used_changes FROM users")
        users = c.fetchall()
        perms = {}
        for u in users:
            tg_id, max_changes, used_changes = u
            c.execute("SELECT ocid, expire_date FROM user_instances WHERE tg_id=?", (tg_id,))
            ocids = {row[0]: row[1] for row in c.fetchall()}
            perms[tg_id] = {"max_changes": max_changes, "used_changes": used_changes, "ocids": ocids}
        conn.close()
        return perms

def update_user(tg_id, max_changes, used_changes, ocids_dict):
    with _db_lock:
        conn = get_conn()
        c = conn.cursor()
        c.execute('''INSERT INTO users (tg_id, max_changes, used_changes) 
                     VALUES (?, ?, ?) 
                     ON CONFLICT(tg_id) DO UPDATE SET 
                     max_changes=excluded.max_changes, used_changes=excluded.used_changes''', 
                  (tg_id, max_changes, used_changes))
        c.execute("DELETE FROM user_instances WHERE tg_id=?", (tg_id,))
        for ocid, exp in ocids_dict.items():
            c.execute("INSERT INTO user_instances (tg_id, ocid, expire_date) VALUES (?, ?, ?)", (tg_id, ocid, exp))
        conn.commit()
        conn.close()

def delete_user(tg_id):
    with _db_lock:
        conn = get_conn()
        conn.execute("DELETE FROM users WHERE tg_id=?", (tg_id,))
        conn.commit()
        conn.close()

def log_change(user_id, server_name, old_ip, new_ip, now_time_str):
    with _db_lock:
        conn = get_conn()
        conn.execute("INSERT INTO logs (tg_id, server_name, old_ip, new_ip, change_time) VALUES (?, ?, ?, ?, ?)",
                     (user_id, server_name, old_ip, new_ip, now_time_str))
        conn.commit()
        conn.close()

def get_ip_cache():
    with _db_lock:
        conn = get_conn()
        res = {row[0]: row[1] for row in conn.execute("SELECT ocid, ip_address FROM ip_cache").fetchall()}
        conn.close()
        return res

def save_ip_cache(data_dict):
    with _db_lock:
        conn = get_conn()
        for ocid, ip in data_dict.items():
            conn.execute("INSERT INTO ip_cache (ocid, ip_address) VALUES (?, ?) ON CONFLICT(ocid) DO UPDATE SET ip_address=excluded.ip_address", (ocid, ip))
        conn.commit()
        conn.close()

def get_traffic_limits():
    with _db_lock:
        conn = get_conn()
        res = {row[0]: row[1] for row in conn.execute("SELECT account_name, limit_gb FROM traffic_data").fetchall()}
        conn.close()
        return res

def get_traffic_cache():
    with _db_lock:
        conn = get_conn()
        res = {row[0]: {"usage_gb": row[1], "update_time": row[2]} 
               for row in conn.execute("SELECT account_name, usage_gb, update_time FROM traffic_data").fetchall()}
        conn.close()
        return res

def save_traffic_limits(data_dict):
    with _db_lock:
        conn = get_conn()
        for acc, limit in data_dict.items():
            conn.execute("INSERT INTO traffic_data (account_name, limit_gb) VALUES (?, ?) ON CONFLICT(account_name) DO UPDATE SET limit_gb=excluded.limit_gb", (acc, limit))
        conn.commit()
        conn.close()

def save_traffic_cache(data_dict):
    with _db_lock:
        conn = get_conn()
        for acc, data in data_dict.items():
            conn.execute("INSERT INTO traffic_data (account_name, usage_gb, update_time) VALUES (?, ?, ?) ON CONFLICT(account_name) DO UPDATE SET usage_gb=excluded.usage_gb, update_time=excluded.update_time", 
                         (acc, data.get('usage_gb', -1), data.get('update_time', '')))
        conn.commit()
        conn.close()
