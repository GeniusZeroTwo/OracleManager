# data/storage.py
import json
import os
import threading

# 全局读写锁
_file_lock = threading.Lock()

STATS_FILE = 'stats.json'
PERMS_FILE = 'permissions.json'
IP_CACHE_FILE = 'ip_cache.json'
TRAFFIC_CACHE_FILE = 'traffic_cache.json'
TRAFFIC_LIMITS_FILE = 'traffic_limits.json'

def load_json(filename):
    """带锁的安全读取"""
    with _file_lock:
        if not os.path.exists(filename): return {}
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

def save_json(filename, data):
    """带锁的安全写入，使用临时文件防止断电损坏"""
    with _file_lock:
        temp_file = filename + ".tmp"
        try:
            with open(temp_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4)
            os.replace(temp_file, filename) # 原子替换
        except Exception as e:
            print(f"写入 {filename} 失败: {e}")

# 封装具体的业务读取方法
def get_permissions():
    return load_json(PERMS_FILE)

def update_permissions(user_id, data):
    perms = get_permissions()
    perms[user_id] = data
    save_json(PERMS_FILE, perms)
