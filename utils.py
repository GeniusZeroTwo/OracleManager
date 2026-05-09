import hashlib
from datetime import datetime
from config import BJ_TZ

def get_bj_now():
    return datetime.now(BJ_TZ)

def get_short_id(text):
    return hashlib.md5(str(text).encode()).hexdigest()[:16]
