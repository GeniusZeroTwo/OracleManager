import time
import requests
import base64
import os
from datetime import datetime, timezone
from config import ADMIN_ID, GITHUB_TOKEN, GITHUB_REPO, load_oci_accounts
from utils import get_bj_now
from data import storage

def backup_to_github():
    if not GITHUB_TOKEN or not GITHUB_REPO:
        return False, "⚠️ 未配置 GITHUB，跳过备份。"

    files = [storage.PERMS_FILE, storage.STATS_FILE, storage.TRAFFIC_LIMITS_FILE]
    success_count = 0
    errors = []

    for filename in files:
        if not os.path.exists(filename): continue
        try:
            with open(filename, 'rb') as f: content = f.read()
            encoded = base64.b64encode(content).decode('utf-8')
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{filename}"
            headers = {"Authorization": f"token {GITHUB_TOKEN}", "Accept": "application/vnd.github.v3+json"}

            sha = None
            get_resp = requests.get(url, headers=headers)
            if get_resp.status_code == 200: sha = get_resp.json().get('sha')

            data = {"message": f"Auto backup {filename} by Bot", "content": encoded}
            if sha: data["sha"] = sha

            put_resp = requests.put(url, headers=headers, json=data)
            if put_resp.status_code in [200, 201, 422]: success_count += 1
            else: errors.append(f"{filename}: {put_resp.status_code}")
        except Exception as e: errors.append(f"{filename}: {str(e)}")

    if errors: return False, "\n".join(errors)
    return True, f"✅ 成功备份 {success_count} 个文件"

def background_jobs_loop(oci_svc, bot):
    def send_tg(text):
        try: bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
        except: pass

    last_report_day = None
    last_traffic_report_utc = None
    last_traffic_check_utc = None
    high_frequency_mode = False
    
    while True:
        try:
            now_bj = get_bj_now()
            today_bj_str = now_bj.strftime("%Y-%m-%d")
            now_utc = datetime.now(timezone.utc)
            today_utc_str = now_utc.strftime("%Y-%m-%d")
            
            # --- 任务 1：到期提醒 ---
            if last_report_day != today_bj_str and now_bj.hour >= 12:
                perms = storage.get_permissions()
                for uid, data in perms.items():
                    for ocid, exp_str in data.get('ocids', {}).items():
                        if not exp_str: continue
                        try:
                            s_name = oci_svc.all_instances.get(ocid, {}).get("name", "未知节点")
                            days_left = (datetime.strptime(exp_str, "%Y-%m-%d").date() - now_bj.date()).days
                            if days_left in [6, 4, 2, 0]:
                                msg = f"⏳ **服务提醒**\n您的节点 `{s_name}` 剩余 `{days_left}` 天。"
                                if days_left == 0: msg = f"⚠️ **今日到期**\n节点 `{s_name}` 将于今晚到期！"
                                try: bot.send_message(uid, msg, parse_mode="Markdown")
                                except: pass
                                send_tg(f"🔔 客户 `{uid}` 机器 `{s_name}` 剩余 {days_left} 天。")
                        except: pass
                last_report_day = today_bj_str
                
            # --- 任务 2：流量熔断检测 ---
            if last_traffic_check_utc != today_utc_str or high_frequency_mode:
                accounts = load_oci_accounts()
                limits_data = storage.get_traffic_limits()
                cache = storage.get_traffic_cache()
                any_at_risk = False
                
                for acc_name, acc_conf in accounts.items():
                    limit = int(limits_data.get(acc_name, 0))
                    usage_gb = oci_svc.fetch_traffic_for_account(acc_conf)
                    
                    if usage_gb >= 0:
                        cache[acc_name] = {"usage_gb": usage_gb, "update_time": now_utc.strftime("%Y-%m-%d %H:%M:%S UTC")}
                        if limit > 0:
                            if (usage_gb / limit) >= 0.9: any_at_risk = True
                            if usage_gb >= limit:
                                count, names = oci_svc.suspend_account_instances(acc_name, acc_conf)
                                if count > 0:
                                    oci_svc.fetch_all_instances(accounts)
                                    send_tg(f"🛑 **自动熔断**\n账号: `{acc_name}`\n超额停机 {count} 台: `{', '.join(names)}`")
                
                high_frequency_mode = any_at_risk
                last_traffic_check_utc = today_utc_str
                storage.save_traffic_cache(cache)
            
            # --- 任务 3：每日战报与备份 ---
            if last_traffic_report_utc != today_utc_str:
                success, msg = backup_to_github()
                if not success: send_tg(f"🔴 **自动备份失败**\n{msg}")
                last_traffic_report_utc = today_utc_str

        except Exception as e: print(f"后台任务错误: {e}")
        time.sleep(3600)
