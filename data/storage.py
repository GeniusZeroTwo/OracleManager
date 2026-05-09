import sqlite3
import json
import os
import threading

DB_FILE = 'oracle_manager.db'
_db_lock = threading.Lock()

def get_conn():
    # 允许多线程共享连接对象，但我们会用锁来保证写安全
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA foreign_keys = ON;") # 开启外键约束级联删除
    return conn

def init_db():
    with _db_lock:
        conn = get_conn()
        c = conn.cursor()
        
        # 1. 用户与额度表
        c.execute('''CREATE TABLE IF NOT EXISTS users (
                        tg_id TEXT PRIMARY KEY,
                        max_changes INTEGER DEFAULT 0,
                        used_changes INTEGER DEFAULT 0
                     )''')
                     
        # 2. 用户授权的实例表 (一对多)
        c.execute('''CREATE TABLE IF NOT EXISTS user_instances (
                        tg_id TEXT,
                        ocid TEXT,
                        expire_date TEXT,
                        PRIMARY KEY (tg_id, ocid),
                        FOREIGN KEY(tg_id) REFERENCES users(tg_id) ON DELETE CASCADE
                     )''')
                     
        # 3. IP 缓存表
        c.execute('''CREATE TABLE IF NOT EXISTS ip_cache (
                        ocid TEXT PRIMARY KEY,
                        ip_address TEXT
                     )''')
                     
        # 4. 流量统计与限额表
        c.execute('''CREATE TABLE IF NOT EXISTS traffic_data (
                        account_name TEXT PRIMARY KEY,
                        limit_gb INTEGER DEFAULT 0,
                        usage_gb REAL DEFAULT -1,
                        update_time TEXT
                     )''')
                     
        # 5. 换IP历史日志表
        c.execute('''CREATE TABLE IF NOT EXISTS logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        tg_id TEXT,
                        server_name TEXT,
                        old_ip TEXT,
                        new_ip TEXT,
                        change_time TEXT
                     )''')
        conn.commit()
        
        # --- 无缝自动迁移逻辑：如果发现旧JSON且数据库为空，则自动导入 ---
        c.execute("SELECT COUNT(*) FROM users")
        if c.fetchone()[0] == 0 and os.path.exists('permissions.json'):
            print("📦 检测到旧版 JSON 数据，正在自动迁移至 SQLite...")
            _auto_migrate_from_json(conn)
            print("✅ 数据库迁移完成！旧文件已备份为 .bak")
            
        conn.close()

def _auto_migrate_from_json(conn):
    c = conn.cursor()
    # 迁移 permissions.json
    if os.path.exists('permissions.json'):
        with open('permissions.json', 'r', encoding='utf-8') as f:
            perms = json.load(f)
            for tg_id, data in perms.items():
                c.execute("INSERT INTO users (tg_id, max_changes, used_changes) VALUES (?, ?, ?)",
                          (tg_id, data.get('max_changes', 0), data.get('used_changes', 0)))
                for ocid, exp in data.get('ocids', {}).items():
                    c.execute("INSERT INTO user_instances (tg_id, ocid, expire_date) VALUES (?, ?, ?)", (tg_id, ocid, exp))
        os.rename('permissions.json', 'permissions.json.bak')
        
    # 迁移 ip_cache.json
    if os.path.exists('ip_cache.json'):
        with open('ip_cache.json', 'r', encoding='utf-8') as f:
            for ocid, ip in json.load(f).items():
                c.execute("INSERT INTO ip_cache (ocid, ip_address) VALUES (?, ?)", (ocid, ip))
        os.rename('ip_cache.json', 'ip_cache.json.bak')
        
    conn.commit()

# ==========================================
# 业务接口 (与旧代码逻辑无缝对接)
# ==========================================

def get_permissions():
    """将数据库格式组装回前端需要的字典格式"""
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
    """更新单个用户的数据（替代原来的全局覆写）"""
    with _db_lock:
        conn = get_conn()
        c = conn.cursor()
        # 插入或更新主表
        c.execute('''INSERT INTO users (tg_id, max_changes, used_changes) 
                     VALUES (?, ?, ?) 
                     ON CONFLICT(tg_id) DO UPDATE SET 
                     max_changes=excluded.max_changes, used_changes=excluded.used_changes''', 
                  (tg_id, max_changes, used_changes))
        # 全量更新实例表（先删后增）
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

# --- 缓存查询接口 ---
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
