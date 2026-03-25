import requests
import json
import time
from colorama import init, Fore, Style

init()

def get_root_from_universe(universe_id):
    """Converts a Universe ID to a usable Root Place ID"""
    try:
        res = requests.get(f"https://games.roblox.com/v1/games?universeIds={universe_id}")
        data = res.json().get("data", [])
        if data:
            return str(data[0].get("rootPlaceId")), data[0].get("name")
    except: pass
    return None, None

def investigate_id(target_id):
    target_id = target_id.strip()
    if not target_id.isdigit(): return None

    print(f"{Fore.CYAN}Investigating ID: {target_id}{Style.RESET_ALL}")
    found_keys = set()
    
    if len(target_id) >= 13:
        print(f"  {Fore.GREEN}[PLACE]{Style.RESET_ALL} Modern 64-bit ID detected.")
        found_keys.add(target_id)

    try:
        res_g = requests.get(f"https://groups.roblox.com/v1/groups/{target_id}")
        if res_g.status_code == 200:
            g_name = res_g.json().get('name')
            print(f"  {Fore.MAGENTA}[GROUP]{Style.RESET_ALL} Name: {g_name}")
            res_games = requests.get(f"https://games.roblox.com/v1/groups/{target_id}/universes?limit=10")
            if res_games.status_code == 200:
                for g in res_games.json().get("data", []):
                    if g.get("rootPlaceId"):
                        found_keys.add(str(g["rootPlaceId"]))
                        print(f"    {Fore.GREEN}-> Found Group Game: {g['name']} ({g['rootPlaceId']}){Style.RESET_ALL}")
    except: pass

    try:
        res_u = requests.get(f"https://users.roblox.com/v1/users/{target_id}")
        if res_u.status_code == 200:
            u_name = res_u.json().get('name')
            print(f"  {Fore.MAGENTA}[USER] {Style.RESET_ALL} Name: {u_name}")
            res_ugames = requests.get(f"https://games.roblox.com/v1/users/{target_id}/universes?limit=10")
            if res_ugames.status_code == 200:
                for g in res_ugames.json().get("data", []):
                    if g.get("rootPlaceId"):
                        found_keys.add(str(g["rootPlaceId"]))
                        print(f"    {Fore.GREEN}-> Found User Game: {g['name']} ({g['rootPlaceId']}){Style.RESET_ALL}")
    except: pass

    try:
        res_a = requests.get(f"https://economy.roblox.com/v2/assets/{target_id}/details")
        if res_a.status_code == 200:
            a_data = res_a.json()
            print(f"  {Fore.BLUE}[ASSET]{Style.RESET_ALL} Name: {a_data.get('Name')}")
            u_id = a_data.get("UniverseId")
            if u_id:
                pid, name = get_root_from_universe(u_id)
                if pid:
                    print(f"    {Fore.GREEN}-> Leaked Origin Game: {name} ({pid}){Style.RESET_ALL}")
                    found_keys.add(pid)
    except: pass

    pid, name = get_root_from_universe(target_id)
    if pid:
        print(f"  {Fore.GREEN}[UNIVERSE]{Style.RESET_ALL} ID is a Universe. Root: {pid}")
        found_keys.add(pid)

    return found_keys

def main():
    print(f"{Fore.YELLOW}======================================")
    print("      Lemon Key Finder 🍋")
    print("     (find universe id's for reuploading)")
    print(f"======================================{Style.RESET_ALL}")
    print("Paste IDs. Type 'exit' to quit.\n")

    while True:
        user_input = input(f"{Fore.WHITE}Enter ID(s): {Style.RESET_ALL}").strip().lower()
        if user_input == 'exit': break
        if not user_input: continue
        
        raw_list = user_input.replace(",", " ").split()
        all_results = set()

        for item in raw_list:
            res = investigate_id(item)
            if res: all_results.update(res)

        if all_results:
            all_results.add("0")
            print(f"\n{Fore.YELLOW}=== RESULTS FOR CONFIG ==={Style.RESET_ALL}")
            formatted = ", ".join([f'"{k}"' for k in sorted(all_results)])
            print(f"\"source_place_ids\": [{formatted}]")
        else:
            print(f"\n{Fore.RED}No public keys found.{Style.RESET_ALL}")
        print("\n" + "-"*40 + "\n")

if __name__ == "__main__":
    main()