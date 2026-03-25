import requests
import json
import os
import re
import time
import concurrent.futures
from colorama import init, Fore, Style
from roblox_session import RobloxSession

init()

class ManualDownloader:
    def __init__(self):
        self.config = self.load_config()
        self.cookie = self.config["authentication"]["roblosecurity"]
        
        proxy_url = self.config.get("migration", {}).get("proxy")
        self.session = RobloxSession(self.cookie, proxy=proxy_url)
        

        self.config_keys = [str(x).strip() for x in self.config.get("migration", {}).get("source_place_ids", [])]
        if "0" in self.config_keys: self.config_keys.remove("0")
        

        self.universal_keys = [
            "95206881",  
            "1818",      
            "6065519443"
        ]
        
        if not os.path.exists("downloads"):
            os.makedirs("downloads")

    def load_config(self):
        if not os.path.exists("config.json"):
            print(f"{Fore.RED}Config not found!{Style.RESET_ALL}")
            exit()
        with open("config.json", "r") as f:
            return json.load(f)

    def get_asset_details(self, asset_id):
        try:
            url = f"https://economy.roblox.com/v2/assets/{asset_id}/details"
            res = self.session.request("GET", url)
            if res.status_code == 200:
                return res.json()
        except: pass
        return {}

    def get_creator_games(self, creator_id, creator_type):
        """
        ENHANCED LOGIC:
        - Checks Newest Games (Desc)
        - Checks Oldest Games (Asc) - Vital for old groups
        - Checks User Starter Places
        """
        keys = set()
        endpoints = []

        if creator_type == "User":

            endpoints.append(f"https://games.roblox.com/v2/users/{creator_id}/games?accessFilter=Public&sortOrder=Desc&limit=50")

            endpoints.append(f"https://games.roblox.com/v2/users/{creator_id}/games?accessFilter=Public&sortOrder=Asc&limit=50")
            
        elif creator_type == "Group":

            endpoints.append(f"https://games.roblox.com/v2/groups/{creator_id}/games?accessFilter=Public&sortOrder=Desc&limit=50")

            endpoints.append(f"https://games.roblox.com/v2/groups/{creator_id}/games?accessFilter=Public&sortOrder=Asc&limit=50")


        for url in endpoints:
            try:
                res = self.session.request("GET", url)
                if res.status_code == 200:
                    data = res.json().get("data", [])
                    for game in data:
                        keys.add(str(game["rootPlaceId"]))
            except: pass
            
        return list(keys)

    def resolve_root_place(self, universe_id):
        if not universe_id: return None
        try:
            res = self.session.request("GET", f"https://games.roblox.com/v1/games?universeIds={universe_id}")
            data = res.json().get("data", [])
            if data: return str(data[0].get("rootPlaceId"))
        except: pass
        return None

    def _try_download_key(self, asset_id, place_id):
        """Worker function for threading"""
        headers = {
            "User-Agent": "RobloxStudio/WinInet",
            "Accept": "application/json",
        }
        key_label = "Public"
        if place_id:
            headers["Roblox-Place-Id"] = str(place_id)
            key_label = str(place_id)
            
        payload = [{"assetId": int(asset_id), "requestId": "1", "clientInsert": True, "scriptInsert": True}]
        
        try:
            url = "https://assetdelivery.roblox.com/v2/assets/batch"
            res = self.session.request("POST", url, json=payload, headers=headers, timeout=5)
            
            if res.status_code == 200:
                data = res.json()
                if data and "locations" in data[0] and data[0]["locations"]:
                    cdn_url = data[0]["locations"][0]["location"]
                    

                    file_res = requests.get(cdn_url, timeout=10)
                    if file_res.status_code == 200:

                        if b"<Error" in file_res.content[:100] or b"AccessDenied" in file_res.content[:100]:
                            return None
                        return (file_res.content, key_label)
        except: pass
        return None

    def determine_extension(self, content):
        if content.startswith(b"\x89PNG"): return ".png"
        if content.startswith(b"\xFF\xD8\xFF"): return ".jpg"
        if content.startswith(b"OggS"): return ".ogg"
        if content.startswith(b"ID3") or content.startswith(b"\xFF\xFB"): return ".mp3"
        if content.startswith(b"RIFF"): return ".wav"
        if content.startswith(b"<roblox") or b"<roblox" in content[:100]: return ".rbxm" 
        if b"version" in content[:50]: return ".rbxm" 
        return ".bin" 

    def clean_filename(self, name):
        return re.sub(r'[\\/*?:"<>|]', "", name).strip()

    def process_single_asset(self, asset_id, ask_name=True):
        print(f"\n{Fore.CYAN}--- Processing ID: {asset_id} ---{Style.RESET_ALL}")
        

        details = self.get_asset_details(asset_id)
        real_name = details.get("Name", "Untitled")
        creator = details.get("Creator", {})
        c_name = creator.get("Name", "Unknown")
        c_id = creator.get("CreatorTargetId")
        c_type = creator.get("CreatorType")
        
        print(f"Name: {Fore.YELLOW}{real_name}{Style.RESET_ALL} | Owner: {Fore.MAGENTA}{c_name}{Style.RESET_ALL}")


        keys_to_try = []


        if c_id:
            print(f"{Fore.BLUE}[INFO] Deep Scanning games by {c_name}...{Style.RESET_ALL}", end=" ")
            creator_keys = self.get_creator_games(c_id, c_type)
            print(f"Found {len(creator_keys)} keys.")
            keys_to_try.extend(creator_keys)


        u_id = details.get("UniverseId")
        if u_id:
            pid = self.resolve_root_place(u_id)
            if pid: keys_to_try.append(pid)

        keys_to_try.extend(self.config_keys)
        keys_to_try.extend(self.universal_keys)
        keys_to_try.append(None) 
        
        unique_keys = []
        [unique_keys.append(x) for x in keys_to_try if x not in unique_keys]
        
        print(f"{Fore.BLUE}[INFO] Cracking permissions with {len(unique_keys)} keys...{Style.RESET_ALL}")

        final_content = None
        used_key = None

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            future_to_key = {executor.submit(self._try_download_key, asset_id, key): key for key in unique_keys}
            
            for future in concurrent.futures.as_completed(future_to_key):
                result = future.result()
                if result:
                    final_content, used_key = result
                    executor.shutdown(wait=False, cancel_futures=True)
                    break
        
        if final_content:
            print(f"{Fore.GREEN}SUCCESS! Unlocked via: {used_key}{Style.RESET_ALL}")
            
            final_filename = self.clean_filename(real_name)
            
            if ask_name:
                user_input = input(f"Save as (Press Enter for '{final_filename}'): ").strip()
                if user_input: final_filename = self.clean_filename(user_input)
            
            ext = self.determine_extension(final_content)
            
            save_name = f"{final_filename}{ext}"
            counter = 1
            while os.path.exists(os.path.join("downloads", save_name)):
                save_name = f"{final_filename}_{counter}{ext}"
                counter += 1
            
            path = os.path.join("downloads", save_name)
            with open(path, "wb") as f:
                f.write(final_content)
            
            print(f"{Fore.CYAN}Saved to: {path}{Style.RESET_ALL}")
        else:
            print(f"{Fore.RED}FAILED.{Style.RESET_ALL}")
            if c_type == "Group":
                 print(f"{Fore.WHITE}Tip: {c_name} might not have ANY public games. You must find a Place ID owned by this group manually.{Style.RESET_ALL}")
            else:
                 print(f"{Fore.WHITE}Tip: Ensure your cookie is valid and config.json is correct.{Style.RESET_ALL}")

    def run(self):
        print(f"{Fore.CYAN}========================================")
        print("   Lemon Manual Downloader 🍋")
        print(f"========================================{Style.RESET_ALL}\n")

        while True:
            raw_input = input(f"\n{Fore.WHITE}Enter Asset ID(s) (or 'exit'): {Style.RESET_ALL}").strip()
            if raw_input.lower() == "exit": break
            
            ids = [x.strip() for x in re.split(r'[ ,]+', raw_input) if x.strip().isdigit()]
            
            if not ids: continue
            
            ask_for_name = (len(ids) == 1)
            
            for asset_id in ids:
                self.process_single_asset(asset_id, ask_name=ask_for_name)

if __name__ == "__main__":
    ManualDownloader().run()