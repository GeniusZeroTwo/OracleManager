import oci
import time
import threading
import concurrent.futures
from datetime import datetime, timezone
from data import storage

class OCIService:
    def __init__(self):
        self.all_instances = {}
        self.instance_config_map = {}
        # 内存级缓存，减少读盘
        self._mem_ip_cache = storage.get_ip_cache()

    def fetch_single_account_instances(self, acc_name, config):
        local_instances = {}
        local_config_map = {}
        try:
            compute_client = oci.core.ComputeClient(config)
            data = compute_client.list_instances(compartment_id=config["tenancy"]).data
            for i in data:
                if i.lifecycle_state in ['TERMINATED', 'TERMINATING']: continue
                local_config_map[i.id] = config
                local_instances[i.id] = {
                    "name": f"[{acc_name}] {i.display_name}",
                    "state": i.lifecycle_state,
                    "account": acc_name
                }
            return acc_name, local_instances, local_config_map, None
        except Exception as e:
            return acc_name, {}, {}, f"{acc_name} 错误: {str(e)}"

    def fetch_all_instances(self, accounts):
        new_all_instances = {}
        new_config_map = {}
        error_msgs = []

        # 使用多线程并发拉取多账号节点，大幅提升速度
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = {executor.submit(self.fetch_single_account_instances, name, conf): name for name, conf in accounts.items()}
            for future in concurrent.futures.as_completed(futures):
                acc_name, local_inst, local_conf, err = future.result()
                if err: error_msgs.append(err)
                else:
                    new_all_instances.update(local_inst)
                    new_config_map.update(local_conf)

        self.all_instances = new_all_instances
        self.instance_config_map = new_config_map
        return len(error_msgs) == 0, " | ".join(error_msgs) if error_msgs else "同步成功"

    def get_instance_public_ip_safe(self, target_ocid):
        config = self.instance_config_map.get(target_ocid)
        if not config: return None
        try:
            compute_client = oci.core.ComputeClient(config)
            vnc_client = oci.core.VirtualNetworkClient(config)
            vnic_attach = compute_client.list_vnic_attachments(compartment_id=config["tenancy"], instance_id=target_ocid).data
            if not vnic_attach: return None
            
            p_ips = vnc_client.list_private_ips(vnic_id=vnic_attach[0].vnic_id).data
            if not p_ips: return None
            
            get_details = oci.core.models.GetPublicIpByPrivateIpIdDetails(private_ip_id=p_ips[0].id)
            pub_ip = vnc_client.get_public_ip_by_private_ip_id(get_details).data
            return pub_ip.ip_address
        except Exception: return None

    def get_or_fetch_ip(self, ocid):
        if ocid in self._mem_ip_cache: return self._mem_ip_cache[ocid]
        real_ip = self.get_instance_public_ip_safe(ocid)
        if real_ip:
            self._mem_ip_cache[ocid] = real_ip
            threading.Thread(target=storage.save_ip_cache, args=(self._mem_ip_cache,), daemon=True).start()
            return real_ip
        return "未知 IP"

    def change_oracle_ip(self, target_ocid):
        config = self.instance_config_map.get(target_ocid)
        if not config: raise Exception("找不到对应配置")
            
        compute_client = oci.core.ComputeClient(config)
        vnc_client = oci.core.VirtualNetworkClient(config)
        vnic_attach = compute_client.list_vnic_attachments(compartment_id=config["tenancy"], instance_id=target_ocid).data
        if not vnic_attach: raise Exception("未找到网卡")
        
        p_ips = vnc_client.list_private_ips(vnic_id=vnic_attach[0].vnic_id).data
        if not p_ips: raise Exception("未找到内网IP")
        p_ip_id = p_ips[0].id

        old_ip = "Unknown"
        try:
            get_details = oci.core.models.GetPublicIpByPrivateIpIdDetails(private_ip_id=p_ip_id)
            pub_ip = vnc_client.get_public_ip_by_private_ip_id(get_details).data
            old_ip = pub_ip.ip_address
            if pub_ip.lifetime == 'RESERVED':
                vnc_client.update_public_ip(pub_ip.id, oci.core.models.UpdatePublicIpDetails(private_ip_id=""))
            else:
                vnc_client.delete_public_ip(pub_ip.id)
            time.sleep(2)
        except oci.exceptions.ServiceError as e:
            if e.status == 404: old_ip = "None"
            else: raise e

        create_info = oci.core.models.CreatePublicIpDetails(compartment_id=config["tenancy"], lifetime="EPHEMERAL", private_ip_id=p_ip_id)
        new_ip = vnc_client.create_public_ip(create_info).data.ip_address
        
        self._mem_ip_cache[target_ocid] = new_ip
        threading.Thread(target=storage.save_ip_cache, args=(self._mem_ip_cache,), daemon=True).start()
        return old_ip, new_ip

    def fetch_traffic_for_account(self, config):
        try:
            monitoring_client = oci.monitoring.MonitoringClient(config)
            now_utc = datetime.now(timezone.utc)
            start_time = now_utc.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            
            response = monitoring_client.summarize_metrics_data(
                compartment_id=config["tenancy"],
                summarize_metrics_data_details=oci.monitoring.models.SummarizeMetricsDataDetails(
                    namespace="oci_vcn", query="VnicToNetworkBytes[1h].sum()", 
                    start_time=start_time.strftime('%Y-%m-%dT%H:%M:%S.000Z'),
                    end_time=now_utc.strftime('%Y-%m-%dT%H:%M:%S.000Z')
                ),
                compartment_id_in_subtree=True
            )
            total_bytes = sum(dp.value for item in response.data for dp in item.aggregated_datapoints)
            return total_bytes / (1024**3) 
        except Exception: return -1

    def suspend_account_instances(self, acc_name, config):
        try:
            compute_client = oci.core.ComputeClient(config)
            instances = compute_client.list_instances(compartment_id=config["tenancy"]).data
            stopped_names = []
            for i in instances:
                if i.lifecycle_state == 'RUNNING':
                    compute_client.instance_action(i.id, "SOFTSTOP")
                    stopped_names.append(i.display_name)
                    time.sleep(1)
            return len(stopped_names), stopped_names
        except Exception as e: return 0, []
        
    def instance_action(self, target_ocid, action):
        config = self.instance_config_map.get(target_ocid)
        if not config: raise Exception("找不到对应配置")
        compute_client = oci.core.ComputeClient(config)
        compute_client.instance_action(target_ocid, action)
