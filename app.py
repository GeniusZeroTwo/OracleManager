import threading
from flask import Flask
from flask_cors import CORS
import telebot

from config import TG_BOT_TOKEN, load_oci_accounts
from services.oci_service import OCIService
from bot.tg_handlers import register_bot_handlers
from web.api_routes import register_api_routes
from jobs.background import background_jobs_loop

# 1. 初始化核心组件
app = Flask(__name__)
CORS(app)
bot = telebot.TeleBot(TG_BOT_TOKEN)
oci_svc = OCIService()

# 2. 注入依赖并注册路由
register_bot_handlers(bot, oci_svc)
register_api_routes(app, oci_svc, bot)

# 3. 启动包装器
def start_services():
    print("🚀 正在预热 OCI 数据 (多线程拉取中)...")
    oci_svc.fetch_all_instances(load_oci_accounts())
    
    print("🤖 启动 Telegram 机器人线程...")
    threading.Thread(target=bot.infinity_polling, kwargs={"timeout": 10}, daemon=True).start()
    
    print("⏲️ 启动后台定时任务线程...")
    threading.Thread(target=background_jobs_loop, args=(oci_svc, bot), daemon=True).start()

if __name__ == '__main__':
    start_services()
    print("🌐 启动 Flask Web 服务...")
    app.run(host='0.0.0.0', port=5000)
