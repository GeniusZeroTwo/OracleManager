# app.py
import threading
from flask import Flask
from flask_cors import CORS
import telebot

# 导入拆分后的模块
from config import load_oci_accounts, TG_BOT_TOKEN
from services.oci_service import OCIService
from bot.tg_handlers import register_bot_handlers
from web.api_routes import register_api_routes
from jobs.background import background_jobs_loop

# 1. 初始化核心实例
app = Flask(__name__)
CORS(app)
bot = telebot.TeleBot(TG_BOT_TOKEN)
oci_svc = OCIService()

# 2. 注册路由和处理器 (将实例注入进去)
register_bot_handlers(bot, oci_svc)
register_api_routes(app, oci_svc)

# 3. 启动后台线程
def start_background_threads():
    # 启动前先同步一次 OCI 数据
    oci_svc.fetch_all_instances(load_oci_accounts())
    
    threading.Thread(target=bot.infinity_polling, kwargs={"timeout": 10}, daemon=True).start()
    threading.Thread(target=background_jobs_loop, args=(oci_svc, bot), daemon=True).start()

if __name__ == '__main__':
    start_background_threads()
    # 启动 Flask 主线程
    app.run(host='0.0.0.0', port=5000)
