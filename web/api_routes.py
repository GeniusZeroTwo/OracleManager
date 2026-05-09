import time
import random
import secrets
from flask import request, jsonify, render_template
from config import ADMIN_ID, load_oci_accounts
from data import storage

admin_session = {"code": None, "expires": 0, "attempts": 0}

def register_api_routes(app, oci_svc, bot):
    
    def check_auth(req):
        code = str(req.json.get('code', ''))
        acode = admin_session.get('code')
        if not code or not acode: return False
        if time.time() > admin_session['expires']: return False
        return secrets.compare_digest(code, acode)

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/admin/send-code', methods=['POST'])
    def admin_send_code():
        code = str(random.randint(100000, 999999))
        admin_session.update({"code": code, "expires": time.time() + 3600, "attempts": 0})
        try:
            bot.send_message(ADMIN_ID, f"🔐 **登录验证码**：`{code}`", parse_mode="Markdown")
            return jsonify({"success": True})
        except: return jsonify({"success": False, "error": "TG发送失败"})

    @app.route('/api/admin/data', methods=['POST'])
    def admin_data():
        if not check_auth(request): return jsonify({"success": False, "error": "验证码错误"})
        return jsonify({"success": True, "instances": oci_svc.all_instances, "permissions": storage.get_permissions()})

    @app.route('/api/admin/sync', methods=['POST'])
    def admin_sync():
        if not check_auth(request): return jsonify({"success": False})
        success, msg = oci_svc.fetch_all_instances(load_oci_accounts())
        return jsonify({"success": success, "message": msg, "instances": oci_svc.all_instances})

    @app.route('/api/admin/instance-action', methods=['POST'])
    def admin_instance_action():
        if not check_auth(request): return jsonify({"success": False})
        try:
            oci_svc.instance_action(request.json.get('ocid'), request.json.get('action'))
            return jsonify({"success": True})
        except Exception as e: return jsonify({"success": False, "error": str(e)})

    @app.route('/api/admin/save', methods=['POST'])
    def admin_save():
        if not check_auth(request): return jsonify({"success": False})
        data = request.json
        tg_id = str(data.get('tg_id', '')).strip()
        if not tg_id: return jsonify({"success": False})

        perms = storage.get_permissions()
        used = perms.get(tg_id, {}).get('used_changes', 0)
        perms[tg_id] = {
            "ocids": data.get('ocids', {}),
            "max_changes": int(data.get('max_changes', 0)),
            "used_changes": used
        }
        storage.save_permissions(perms)
        return jsonify({"success": True})
        
    @app.route('/api/admin/delete', methods=['POST'])
    def admin_delete():
        if not check_auth(request): return jsonify({"success": False})
        tg_id = str(request.json.get('tg_id', '')).strip()
        perms = storage.get_permissions()
        if tg_id in perms:
            del perms[tg_id]
            storage.save_permissions(perms)
        return jsonify({"success": True})
