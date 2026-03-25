import xml.etree.ElementTree as ET
import re
import requests
import json
import time
import urllib.parse
import threading
import concurrent.futures
import os
from colorama import init, Fore, Style

init()

ASSET_URI_PATTERN = re.compile(r'(?:rbxassetid://|http://www\.roblox\.com/asset/\?id=|https://www\.roblox\.com/asset/\?id=)(\d+)')

class AssetMigrator:
    def __init__(self, session, config):
        self.session = session
        
        migration_cfg = config.get("migration", {})
        self.webhook_url = migration_cfg.get("webhook_url", "")
        
        grp = str(migration_cfg.get("target_group_id", "")).strip()
        self.target_group_id = int(grp) if grp.isdigit() else 0
        
        self.source_pids =[str(x).strip() for x in migration_cfg.get("source_place_ids", [])]
        if "0" not in self.source_pids:
            self.source_pids.append("0")

        self.input_file = migration_cfg.get("input_file")
        self.output_file = migration_cfg.get("output_file")
        self.target_props = config.get("target_properties",[])
        
        self.enabled = migration_cfg.get("enabled_types", {
            "animations": True,
            "audio": True,
            "images": True
        })
        
        self.mapping_file = "mappings.json"
        
        self.print_lock = threading.Lock()
        self.map_lock = threading.Lock()
        self.retry_lock = threading.Lock()
        
        self.id_mapping = self.load_mappings()
        self.asset_metadata = {} 
        self.user_id = None 
        self.retry_list =[] 
        
        self.working_key = self.source_pids[0] if self.source_pids else "0"
        self.is_key_locked = False 
        
        self.upload_semaphore = threading.Semaphore(5)
        
        self.processed_count = 0
        self.success_count = 0
        self.fail_count = 0
        self.start_time = 0

    def validate_session(self):
        print(f"{Fore.YELLOW}Validating Session...{Style.RESET_ALL}")
        try:
            res = self.session.request("GET", "https://users.roblox.com/v1/users/authenticated")
            if res.status_code == 200:
                data = res.json()
                self.user_id = str(data.get("id"))
                print(f"{Fore.GREEN}Logged in as: {data.get('name')} (ID: {self.user_id}){Style.RESET_ALL}")
                return True
            else:
                print(f"{Fore.RED}Cookie Invalid! Status: {res.status_code}{Style.RESET_ALL}")
                return False
        except Exception as e:
            print(f"{Fore.RED}Connection Error: {e}{Style.RESET_ALL}")
            return False

    def load_mappings(self):
        if os.path.exists(self.mapping_file):
            try:
                with open(self.mapping_file, "r") as f:
                    return json.load(f)
            except: pass
        return {}

    def save_mapping(self, old_id, new_id):
        with self.map_lock:
            self.id_mapping[old_id] = new_id
            if len(self.id_mapping) % 20 == 0:
                self._flush_mappings_unsafe()

    def flush_mappings(self):
        with self.map_lock:
            self._flush_mappings_unsafe()

    def _flush_mappings_unsafe(self):
        try:
            with open(self.mapping_file, "w") as f:
                json.dump(self.id_mapping, f, indent=4)
        except: pass

    def fetch_metadata_chunk(self, chunk):
        try:
            id_str = ",".join([str(x) for x in chunk])
            url = f"https://develop.roblox.com/v1/assets?assetIds={id_str}"
            res = self.session.request("GET", url, timeout=10)
            if res.status_code == 200:
                for item in res.json().get("data",[]):
                    name = item.get("name")
                    if not name or name.strip() == "":
                        name = "RestoredAsset"
                    self.asset_metadata[str(item["id"])] = {
                        "name": name,
                        "type": item.get("typeId", 0)
                    }
        except: pass

    def fetch_metadata_batch(self, ids):
        id_list = list(ids)
        if not id_list: return
        
        unknown_ids =[x for x in id_list if x not in self.asset_metadata]
        if not unknown_ids: return

        chunks = [unknown_ids[i:i + 50] for i in range(0, len(unknown_ids), 50)]
        print(f"{Fore.YELLOW}Fast-Fetching metadata for {len(unknown_ids)} assets...{Style.RESET_ALL}")
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures =[executor.submit(self.fetch_metadata_chunk, chunk) for chunk in chunks]
            concurrent.futures.wait(futures)
                    
        print(f"{Fore.GREEN}Metadata fetched.{Style.RESET_ALL}\n")

    def download_asset(self, asset_id):
        pids_to_try = [self.working_key] if self.is_key_locked else [self.working_key] +[p for p in self.source_pids if p != self.working_key]

        for pid in pids_to_try:
            if not pid: continue
            headers = {
                "User-Agent": "RobloxStudio/WinInet",
                "Roblox-Place-Id": pid,
                "Accept": "application/json",
            }
            payload =[{"assetId": int(asset_id), "requestId": "1", "clientInsert": True, "scriptInsert": True}]
            try:
                url = "https://assetdelivery.roblox.com/v2/assets/batch"
                res = self.session.request("POST", url, json=payload, headers=headers, timeout=7)
                if res.status_code == 200:
                    data = res.json()
                    if data and "locations" in data[0] and data[0]["locations"]:
                        cdn_url = data[0]["locations"][0]["location"]
                        file_res = requests.get(cdn_url, timeout=10)
                        if file_res.status_code == 200:
                            content = file_res.content
                            if content.startswith(b"\x89PNG") or content.startswith(b"JFIF"): return content, 13
                            if content.startswith(b"ID3") or content.startswith(b"OggS") or content.startswith(b"RIFF"): return content, 3
                            if b"<roblox" in content[:100] or b"roblox" in content[:100]:
                                self.working_key = pid
                                self.is_key_locked = True
                                return content, 24
            except: pass
        return None, 0

    def get_eta(self, total):
        elapsed = time.time() - self.start_time
        if self.processed_count == 0: return "Calc..."
        avg_time = elapsed / self.processed_count
        items_left = total - self.processed_count
        eta_seconds = int(avg_time * items_left)
        if eta_seconds < 0: eta_seconds = 0
        m, s = divmod(eta_seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}h {m:02d}m {s:02d}s" if h > 0 else f"{m:02d}m {s:02d}s"

    def upload_asset(self, asset_data, old_id, detected_type, meta_name, use_group=True):
        clean_name = re.sub(r'[^a-zA-Z0-9 _-]', '', meta_name).strip()
        if not clean_name: clean_name = "Restored"
        final_name = f"{clean_name}_{old_id}"[:50]

        if detected_type == 24: 
            is_group = "true" if (use_group and self.target_group_id > 0) else "false"
            url = f"https://www.roblox.com/ide/publish/UploadNewAnimation?assetTypeName=Animation&name={urllib.parse.quote(final_name)}&description=LemonSpoofed&isGroupAnim={is_group}"
            if use_group and self.target_group_id > 0: url += f"&groupId={self.target_group_id}"
            
            headers = {"User-Agent": "RobloxStudio/WinInet", "Content-Type": "application/octet-stream"}
            
            wait_time = 5
            for attempt in range(3):
                res = self.session.request("POST", url, data=asset_data, headers=headers)
                
                if res.status_code in [400, 422] or "Inappropriate" in res.text:
                    safe_url = f"https://www.roblox.com/ide/publish/UploadNewAnimation?assetTypeName=Animation&name=%5BCensored%5D&description=A&isGroupAnim={is_group}"
                    if use_group and self.target_group_id > 0: safe_url += f"&groupId={self.target_group_id}"
                    res = self.session.request("POST", safe_url, data=asset_data, headers=headers)
                
                if res.status_code == 200 and res.text.strip().isdigit(): return res.text.strip()
                
                if res.status_code == 429: 
                    time.sleep(wait_time)
                    wait_time *= 2 
                else: 
                    return f"ERR_{res.status_code}"
            return "ERR_TIMEOUT"
        
        else: 
            type_str = "Audio" if detected_type == 3 else "Decal"
            config = {
                "assetType": type_str, 
                "displayName": final_name, 
                "creationContext": {"creator": {"groupId": str(self.target_group_id)} if use_group and self.target_group_id > 0 else {"userId": str(self.user_id)}}
            }
            
            file_ext = "mp3" if detected_type == 3 else "png"
            files =[
                ('request', (None, json.dumps(config), 'application/json')),
                ('fileContent', (f"{final_name}.{file_ext}", asset_data, 'application/octet-stream'))
            ]
            
            wait_time = 5
            for attempt in range(3):
                res = self.session.request("POST", "https://apis.roblox.com/assets/user-auth/v1/assets", files=files)
                if res.status_code == 200:
                    data = res.json()
                    if "response" in data: return str(data["response"].get("assetId"))
                    path = data.get("path")
                    if path:
                        for _ in range(5):
                            time.sleep(2)
                            poll = self.session.request("GET", f"https://apis.roblox.com/assets/user-auth/v1/{path}")
                            if poll.json().get("done"): return str(poll.json().get("response", {}).get("assetId"))
                
                elif res.status_code == 429: 
                    time.sleep(wait_time)
                    wait_time *= 2
                else: 
                    return f"ERR_{res.status_code}"
            return "ERR_TIMEOUT"

    def process_asset(self, old_id, total, is_retry=False):
        if old_id in self.id_mapping and self.id_mapping[old_id] != old_id:
            with self.print_lock:
                if not is_retry:
                    self.processed_count += 1
                    self.success_count += 1
            return

        asset_data, detected_type = self.download_asset(old_id)
        
        if not asset_data:
            with self.print_lock:
                if not is_retry:
                    self.processed_count += 1
                self.fail_count += 1
            self.save_mapping(old_id, old_id)
            return

        if (detected_type == 3 and not self.enabled["audio"]) or \
           (detected_type == 13 and not self.enabled["images"]) or \
           (detected_type == 24 and not self.enabled["animations"]): 
            with self.print_lock:
                if not is_retry:
                    self.processed_count += 1
                self.fail_count += 1
            self.save_mapping(old_id, old_id)
            return

        meta = self.asset_metadata.get(old_id, {"name": "Restored", "type": detected_type})
        type_lbl = {24: "Anim", 3: "Audio", 13: "Img"}.get(detected_type, "Asset")
        
        new_id = None
        with self.upload_semaphore:
            new_id = self.upload_asset(asset_data, old_id, detected_type, meta["name"], True)
            if (not new_id or "ERR" in str(new_id)) and self.target_group_id > 0:
                new_id = self.upload_asset(asset_data, old_id, detected_type, meta["name"], False)
            time.sleep(0.1)

        with self.print_lock:
            if not is_retry:
                self.processed_count += 1
                
            curr = self.processed_count
            eta = self.get_eta(total)
            name_disp = f"{meta['name']}_{old_id}"[:30]
            
            if new_id and str(new_id).isdigit():
                self.success_count += 1
                self.save_mapping(old_id, str(new_id))
                print(f"{Fore.CYAN}[{curr}/{total} | ETA: {eta}]{Style.RESET_ALL} ID: {old_id} [{type_lbl}] ({name_disp}) {Fore.GREEN}-> SUCCESS: {new_id}{Style.RESET_ALL}")
            else:
                if not is_retry:
                    with self.retry_lock:
                        self.retry_list.append(old_id)
                    print(f"{Fore.CYAN}[{curr}/{total} | ETA: {eta}]{Style.RESET_ALL} ID: {old_id}[{type_lbl}] ({name_disp}) {Fore.YELLOW}-> QUEUED FOR RETRY{Style.RESET_ALL}")
                else:
                    self.fail_count += 1
                    self.save_mapping(old_id, old_id)
                    print(f"{Fore.CYAN}[{curr}/{total} | ETA: {eta}]{Style.RESET_ALL} ID: {old_id} [{type_lbl}] ({name_disp}) {Fore.RED}-> FAIL (Final){Style.RESET_ALL}")

    def send_webhook(self, total):
        if not self.webhook_url: return
        embed = {
            "title": "Spoofing Complete 🍋",
            "color": 65280,
            "fields":[
                {"name": "Total Processed", "value": str(total), "inline": True},
                {"name": "Reuploaded", "value": str(self.success_count), "inline": True},
                {"name": "Failed/Skipped", "value": str(self.fail_count), "inline": True}
            ]
        }
        try: requests.post(self.webhook_url, json={"embeds": [embed]})
        except: pass

    def run(self):
        if not self.validate_session(): return
        
        dest_label = ""
        if self.target_group_id > 0:
            try:
                g_res = self.session.request("GET", f"https://groups.roblox.com/v1/groups/{self.target_group_id}")
                g_name = g_res.json().get("name", "Unknown Group")
                dest_label = f"{Fore.MAGENTA}[GROUP]{Style.RESET_ALL} {g_name} ({self.target_group_id})"
            except: dest_label = f"{Fore.MAGENTA}[GROUP]{Style.RESET_ALL} ID: {self.target_group_id}"
        else:
            dest_label = f"{Fore.MAGENTA}[USER]{Style.RESET_ALL} Profile ({self.user_id})"

        print(f"Destination: {dest_label}")
        print(f"{Fore.YELLOW}Launching Lemon Spoofer v1...{Style.RESET_ALL}")

        try:
            tree = ET.parse(self.input_file); root = tree.getroot()
        except Exception as e:
            print(f"{Fore.RED}Error: {e}{Style.RESET_ALL}"); return

        all_ids = set()
        for node in root.iter():
            if node.text:
                for m in ASSET_URI_PATTERN.findall(node.text): all_ids.add(m)

        self.fetch_metadata_batch(all_ids)

        targets =[]
        for aid in all_ids:
            meta = self.asset_metadata.get(aid, {"type": 0}) 
            t_id = meta.get("typeId", meta.get("type", 0))

            if t_id == 24 and self.enabled["animations"]: targets.append(aid)
            elif t_id == 3 and self.enabled["audio"]: targets.append(aid)
            elif t_id in [1, 13] and self.enabled["images"]: targets.append(aid)
            elif t_id == 0: targets.append(aid)

        total_assets = len(targets)
        print(f"{Fore.GREEN}Queue ready: {total_assets} targets. {len(self.id_mapping)} already cached.{Style.RESET_ALL}\n")
        
        self.start_time = time.time()

        with concurrent.futures.ThreadPoolExecutor(max_workers=15) as executor:
            futures =[executor.submit(self.process_asset, aid, total_assets, False) for aid in targets]
            concurrent.futures.wait(futures)

        if self.retry_list:
            print(f"\n{Fore.MAGENTA}=== Retrying {len(self.retry_list)} Failed Assets ==={Style.RESET_ALL}")
            retry_targets = list(self.retry_list)
            self.retry_list =[] 
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
                futures =[executor.submit(self.process_asset, aid, total_assets, True) for aid in retry_targets]
                concurrent.futures.wait(futures)
            
        self.flush_mappings()

        print(f"\n{Fore.YELLOW}Finalizing IDs in file...{Style.RESET_ALL}")
        count_replaced = 0
        for node in root.iter():
            if node.text:
                def replacer(match):
                    found_id = match.group(1)
                    if found_id in self.id_mapping:
                        nonlocal count_replaced
                        count_replaced += 1
                        return f"rbxassetid://{self.id_mapping[found_id]}"
                    return match.group(0)

                node.text = ASSET_URI_PATTERN.sub(replacer, node.text)

        tree.write(self.output_file, encoding="utf-8", xml_declaration=True)
        print(f"{Fore.CYAN}ALL TASKS COMPLETE! Output: {self.output_file}{Style.RESET_ALL}")
        self.send_webhook(self.processed_count)