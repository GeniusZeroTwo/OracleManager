# services/oci_service.py
import oci
import time
from data.storage import get_permissions, save_json, IP_CACHE_FILE, load_json

class OCIService:
    def __init__(self):
        self.all_instances = {}
        self.instance_config_map = {}
        
    def fetch_all_instances(self, accounts_config):
        """拉取所有实例，替代原来的全局变量操作"""
        new_instances, new_config, errors = {}, {}, []
        for acc_name, config in accounts_config.items():
            try:
                compute_client = oci.core.ComputeClient(config)
                data = compute_client.list_instances(compartment_id=config["tenancy"]).data
                for i in data:
                    if i.lifecycle_state in ['TERMINATED', 'TERMINATING']: continue
                    new_config[i.id] = config
                    new_instances[i.id] = {
                        "name": f"[{acc_name}] {i.display_name}",
                        "state": i.lifecycle_state,
                        "account": acc_name
                    }
            except Exception as e:
                errors.append(f"{acc_name}: {str(e)}")
                
        self.all_instances = new_instances
        self.instance_config_map = new_config
        return len(errors) == 0, errors

    def change_ip(self, target_ocid):
        """执行换IP逻辑并返回 (old_ip, new_ip)"""
        config = self.instance_config_map.get(target_ocid)
        if not config: raise ValueError("实例配置不存在")
        # ... 这里放入原 app.py 中 change_oracle_ip 的逻辑 ...
        return old_ip, new_ip
