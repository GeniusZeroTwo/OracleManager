import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from config import ADMIN_ID
from utils import get_bj_now, get_short_id
from data import storage
from jobs.background import backup_to_github

def register_bot_handlers(bot: telebot.TeleBot, oci_svc):
    
    def is_whitelisted(user_id):
        if str(user_id) == ADMIN_ID: return True 
        return str(user_id) in storage.get_permissions()

    @bot.message_handler(commands=['backup'])
    def admin_manual_backup(message):
        uid = str(message.chat.id)
        if uid != ADMIN_ID: return
        msg = bot.send_message(uid, "⏳ 正在打包并加密上传数据至 GitHub...")
        success, res = backup_to_github()
        bot.edit_message_text(res, chat_id=uid, message_id=msg.message_id)

    @bot.message_handler(commands=['start', 'menu'])
    def user_menu(message):
        uid = str(message.chat.id)
        if not is_whitelisted(uid): return

        perms = storage.get_permissions().get(uid, {})
        ocids_dict = perms.get('ocids', {})
        remaining = perms.get('max_changes', 0) - perms.get('used_changes', 0)

        if not ocids_dict and uid != ADMIN_ID:
            return bot.send_message(uid, "❌ 您当前没有任何授权可操作的服务器。")

        loading_msg = bot.send_message(uid, "⏳ 正在拉取面板信息...")
        now_dt = get_bj_now()
        msg_text = f"🎛️ **专属控制台**\n📊 剩余额度：`{remaining}` 次\n\n"
        markup = InlineKeyboardMarkup()

        for ocid, exp_str in ocids_dict.items():
            info = oci_svc.all_instances.get(ocid, {})
            s_name = info.get("name", "未知节点")
            state = info.get("state", "UNKNOWN")
            
            is_expired = False
            if exp_str:
                try:
                    exp_dt = datetime.strptime(exp_str + " 23:59:59", "%Y-%m-%d %H:%M:%S").replace(tzinfo=now_dt.tzinfo)
                    if now_dt > exp_dt: is_expired = True
                except: pass
                
            msg_text += f"🖥️ **节点：{s_name}**\n"
            if state == 'STOPPED': msg_text += "⛔ 状态：`系统已关机`\n\n"
            elif is_expired: msg_text += f"⛔ 状态：`已到期停用` ({exp_str})\n\n"
            elif state == 'RUNNING':
                current_ip = oci_svc.get_or_fetch_ip(ocid)
                msg_text += f"🌐 当前IP：`{current_ip}`\n📅 到期：{exp_str or '永久'}\n\n"
                markup.add(InlineKeyboardButton(f"🔄 换IP | {current_ip}", callback_data=f"ip_{get_short_id(ocid)}"))
            else: msg_text += f"⚠️ 状态：`{state}`\n\n"

        bot.edit_message_text(text=msg_text, chat_id=uid, message_id=loading_msg.message_id, reply_markup=markup, parse_mode="Markdown")

    @bot.callback_query_handler(func=lambda call: call.data.startswith('ip_'))
    def handle_change_ip(call):
        uid = str(call.message.chat.id)
        if not is_whitelisted(uid): return

        short_id = call.data[3:] 
        target_ocid = next((ocid for ocid in oci_svc.all_instances if get_short_id(ocid) == short_id), None)
        if not target_ocid: return bot.answer_callback_query(call.id, "❌ 找不到实例", show_alert=True)

        user_data = storage.get_permissions().get(uid, {})
        if target_ocid not in user_data.get('ocids', {}):
            return bot.answer_callback_query(call.id, "❌ 授权已失效", show_alert=True)

        if user_data.get('used_changes', 0) >= user_data.get('max_changes', 0) and uid != ADMIN_ID:
            return bot.answer_callback_query(call.id, "❌ 额度耗尽", show_alert=True)

        s_name = oci_svc.all_instances[target_ocid].get("name", "未知")
        bot.edit_message_text(f"⏳ 正在为 `{s_name}` 更换 IP...", chat_id=uid, message_id=call.message.message_id, parse_mode="Markdown")

        try:
            old_ip, new_ip = oci_svc.change_oracle_ip(target_ocid)
            if new_ip:
                user_data['used_changes'] += 1
                storage.update_user(
                    tg_id=uid,
                    max_changes=user_data.get('max_changes', 0),
                    used_changes=user_data['used_changes'],
                    ocids_dict=user_data.get('ocids', {})
                )
                storage.log_change(uid, s_name, old_ip, new_ip, get_bj_now().strftime("%Y-%m-%d %H:%M:%S"))
                
                bot.edit_message_text(f"✅ **换IP成功！**\n节点: `{s_name}`\n新 IP: `{new_ip}`", chat_id=uid, message_id=call.message.message_id, parse_mode="Markdown")
            else:
                bot.edit_message_text("❌ 更换失败 (API异常)，未扣除额度。", chat_id=uid, message_id=call.message.message_id)
        except Exception as e:
            bot.edit_message_text(f"❌ 发生异常: {e}", chat_id=uid, message_id=call.message.message_id)
