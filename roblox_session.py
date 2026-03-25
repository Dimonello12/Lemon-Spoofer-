import requests
from colorama import Fore, Style

class RobloxSession:
    def __init__(self, cookie, proxy=None):
        self.cookie = cookie.strip()
        self.session = requests.Session()
        self.session.cookies['.ROBLOSECURITY'] = self.cookie
        
        if proxy:
            self.session.proxies = {"http": proxy, "https": proxy}
            print(f"{Fore.MAGENTA}Proxy enabled.{Style.RESET_ALL}")

        self.token = None
        self.refresh_token()

    def refresh_token(self):
        """Standard method to fetch x-csrf-token"""
        try:
            response = self.session.post("https://auth.roblox.com/v2/logout")
            if "x-csrf-token" in response.headers:
                self.token = response.headers["x-csrf-token"]
                self.session.headers.update({"x-csrf-token": self.token})
        except Exception as e:
            print(f"{Fore.RED}Failed to refresh CSRF: {e}{Style.RESET_ALL}")

    def request(self, method, url, **kwargs):
        if "ide/publish" in url:
            self.session.headers.update({
                "User-Agent": "RobloxStudio/WinInet",
                "Accept": "application/json"
            })
            
        res = self.session.request(method, url, **kwargs)
        
        if res.status_code == 403 and "x-csrf-token" in res.headers:
            self.token = res.headers["x-csrf-token"]
            self.session.headers.update({"x-csrf-token": self.token})
            return self.session.request(method, url, **kwargs)
            
        return res