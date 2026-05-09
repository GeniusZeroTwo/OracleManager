import os
import yaml
from datetime import timezone, timedelta

ACCOUNTS_FILE = 'oci_accounts.yaml'

def load_full_yaml():
    if os.path.exists(ACCOUNTS_FILE):
        try:
            with open(ACCOUNTS_FILE, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"读取 {ACCOUNTS_FILE} 失败: {e}")
    return {}

_init_config = load_full_yaml()

TG_BOT_TOKEN = str(_init_config.get('bot_token', ''))
ADMIN_ID = str(_init_config.get('admin_id', ''))
GITHUB_TOKEN = str(_init_config.get('github_token', ''))
GITHUB_REPO = str(_init_config.get('github_repo', ''))

BJ_TZ = timezone(timedelta(hours=8))

def load_oci_accounts():
    """提取 OCI 账号配置"""
    config = load_full_yaml()
    accounts = {}
    for k, v in config.items():
        if isinstance(v, dict):
            accounts[k] = v
    return accounts
