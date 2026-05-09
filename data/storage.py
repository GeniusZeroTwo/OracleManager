import os
import json
import threading

_file_lock = threading.Lock()

STATS_FILE = 'stats.json'
PERMS_FILE = 'permissions.json'
IP_CACHE_FILE = 'ip_cache.json'
TRAFFIC_CACHE_FILE = 'traffic_cache.json'
TRAFFIC_LIMITS_FILE = 'traffic_limits.json'

def load_json(filename):
    with _file_lock:
        if not os.path.exists(filename): return {}
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return {}

def save_json(filename, data):
    with _file_lock:
        try:
            temp_file = filename + ".tmp"
            with open(temp_file, 'w', encoding='utf-8') as f: 
                json.dump(data, f, indent=4)
            os.replace(temp_file, filename)
        except Exception as e: 
            print(f"保存 {filename} 失败: {e}")

# --- 具体的业务读取快捷方法 ---
def get_permissions():
    perms = load_json(PERMS_FILE)
    # 兼容老数据结构
    migrated = False
    for uid, data in perms.items():
        if 'ocids' in data and isinstance(data['ocids'], list):
            old_expire = data.get('expire_time', '')
            data['ocids'] = {ocid: old_expire for ocid in data['ocids']}
            if 'expire_time' in data: del data['expire_time']
            migrated = True
    if migrated: save_json(PERMS_FILE, perms)
    return perms

def save_permissions(data):
    save_json(PERMS_FILE, data)

def get_ip_cache(): return load_json(IP_CACHE_FILE)
def save_ip_cache(data): save_json(IP_CACHE_FILE, data)

def get_traffic_limits(): return load_json(TRAFFIC_LIMITS_FILE)
def save_traffic_limits(data): save_json(TRAFFIC_LIMITS_FILE, data)

def get_traffic_cache(): return load_json(TRAFFIC_CACHE_FILE)
def save_traffic_cache(data): save_json(TRAFFIC_CACHE_FILE, data)

def log_change(user_id, server_name, old_ip, new_ip, now_time_str):
    stats = load_json(STATS_FILE)
    if "total_changes" not in stats: stats["total_changes"] = 0
    if "history" not in stats: stats["history"] = []
    
    stats["total_changes"] += 1
    stats["history"].append({
        "time": now_time_str,
        "user_id": user_id, "server": server_name, "old_ip": old_ip, "new_ip": new_ip
    })
    save_json(STATS_FILE, stats)
    return stats["total_changes"]
