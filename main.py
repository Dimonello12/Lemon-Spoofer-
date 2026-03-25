import json
import os
from colorama import init, Fore, Style
from roblox_session import RobloxSession
from migrator import AssetMigrator

def main():

    init()
    print(f"{Fore.CYAN}--- Roblox Asset Spoofer ---{Style.RESET_ALL}")

    if not os.path.exists("config.json"):
        print(f"{Fore.RED}config.json not found! Please create it.{Style.RESET_ALL}")
        return

    with open("config.json", "r") as f:
        config = json.load(f)

    cookie = config["authentication"]["roblosecurity"]
    if not cookie or "WARNING" not in cookie:
        print(f"{Fore.RED}Please update config.json with your actual .ROBLOSECURITY cookie.{Style.RESET_ALL}")
        return

    input_file = config["migration"]["input_file"]
    if not os.path.exists(input_file):
        print(f"{Fore.RED}Input file '{input_file}' not found.{Style.RESET_ALL}")
        return


    proxy_url = config.get("migration", {}).get("proxy")
    
    print(f"{Fore.YELLOW}Authenticating with Roblox...{Style.RESET_ALL}")
    

    session = RobloxSession(cookie, proxy=proxy_url)
    
    if session.token:
        print(f"{Fore.GREEN}Authentication successful! CSRF Token obtained.{Style.RESET_ALL}")
    else:
        print(f"{Fore.RED}Authentication failed. Check cookie or proxy.{Style.RESET_ALL}")
        return

    migrator = AssetMigrator(session, config)
    migrator.run()

if __name__ == "__main__":
    main()