import customtkinter as ctk
import threading
import sys
import os
import json
import re
from tkinter import filedialog
from colorama import Fore, Style

from roblox_session import RobloxSession
from migrator import AssetMigrator
from manual_downloader import ManualDownloader

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("green")

class TextRedirector(object):
    """Safely redirects print() statements to the GUI Console from multiple threads"""
    def __init__(self, text_widget):
        self.text_widget = text_widget
        self.ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

    def write(self, string):
        clean_text = self.ansi_escape.sub('', string)
        if not clean_text:
            return
            
        self.text_widget.after(0, self._append_text, clean_text)

    def _append_text(self, text):
        self.text_widget.configure(state="normal")
        self.text_widget.insert("end", text)
        self.text_widget.see("end") 
        self.text_widget.configure(state="disabled")

    def flush(self):
        pass

class LemonGUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Lemon Spoofer v1 🍋")
        self.geometry("900x650")
        self.resizable(False, False)

        self.config_data = self.load_config()

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=200, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        
        self.logo_label = ctk.CTkLabel(self.sidebar, text="LEMON 🍋", font=ctk.CTkFont(size=25, weight="bold"))
        self.logo_label.grid(row=0, column=0, padx=20, pady=(20, 10))

        self.sidebar_btn_1 = ctk.CTkButton(self.sidebar, text="Migration", command=self.show_migration)
        self.sidebar_btn_1.grid(row=1, column=0, padx=20, pady=10)
        
        self.sidebar_btn_2 = ctk.CTkButton(self.sidebar, text="Manual Spoofer", command=self.show_manual)
        self.sidebar_btn_2.grid(row=2, column=0, padx=20, pady=10)
        
        self.sidebar_btn_3 = ctk.CTkButton(self.sidebar, text="Settings", command=self.show_settings)
        self.sidebar_btn_3.grid(row=3, column=0, padx=20, pady=10)

        self.frame_migration = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.frame_manual = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.frame_settings = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")

        self.setup_migration_ui()
        self.setup_manual_ui()
        self.setup_settings_ui()

        self.show_migration()

    def load_config(self):
        if os.path.exists("config.json"):
            with open("config.json", "r") as f:
                return json.load(f)
        return {"authentication": {}, "migration": {}}

    def save_config(self):
        self.config_data["authentication"]["roblosecurity"] = self.entry_cookie.get()
        self.config_data["migration"]["webhook_url"] = self.entry_webhook.get()
        self.config_data["migration"]["proxy"] = self.entry_proxy.get()
        self.config_data["migration"]["target_group_id"] = self.entry_group.get()
        
        raw_pids = self.textbox_pids.get("1.0", "end").strip()
        self.config_data["migration"]["source_place_ids"] =[x.strip() for x in raw_pids.split("\n") if x.strip()]

        self.config_data["migration"]["enabled_types"] = {
            "animations": bool(self.switch_anim.get()),
            "audio": bool(self.switch_audio.get()),
            "images": bool(self.switch_images.get())
        }
        
        with open("config.json", "w") as f:
            json.dump(self.config_data, f, indent=4)
        
        print("Configuration Saved!")

    def setup_migration_ui(self):
        self.console = ctk.CTkTextbox(self.frame_migration, width=650, height=350, state="disabled", font=("Consolas", 12))
        self.console.pack(pady=20, padx=20)
        
        sys.stdout = TextRedirector(self.console)

        btn_frame = ctk.CTkFrame(self.frame_migration, fg_color="transparent")
        btn_frame.pack(pady=10)

        self.btn_input = ctk.CTkButton(btn_frame, text="Select Input (.rbxmx)", command=self.select_input_file)
        self.btn_input.grid(row=0, column=0, padx=10)

        self.lbl_input = ctk.CTkLabel(btn_frame, text="No file selected")
        self.lbl_input.grid(row=0, column=1, padx=10)

        self.btn_start = ctk.CTkButton(self.frame_migration, text="START MIGRATION", fg_color="green", font=("Arial", 14, "bold"), height=40, command=self.start_migration_thread)
        self.btn_start.pack(pady=20, fill="x", padx=100)

    def setup_manual_ui(self):
        ctk.CTkLabel(self.frame_manual, text="Manual Asset Downloader", font=("Arial", 20, "bold")).pack(pady=20)
        
        self.entry_asset_id = ctk.CTkEntry(self.frame_manual, placeholder_text="Enter Asset ID(s) - Comma separated", width=400)
        self.entry_asset_id.pack(pady=10)
        
        self.btn_download = ctk.CTkButton(self.frame_manual, text="Download Assets", command=self.start_manual_thread)
        self.btn_download.pack(pady=20)
        
        self.manual_console = ctk.CTkTextbox(self.frame_manual, width=600, height=300, state="disabled", font=("Consolas", 12))
        self.manual_console.pack(pady=10)

    def setup_settings_ui(self):
        scroll = ctk.CTkScrollableFrame(self.frame_settings, width=650, height=600)
        scroll.pack(pady=20, padx=20, fill="both")
        
        ctk.CTkLabel(scroll, text="Authentication", font=("Arial", 16, "bold")).pack(pady=5, anchor="w")
        self.entry_cookie = ctk.CTkEntry(scroll, placeholder_text=".ROBLOSECURITY Cookie", width=600)
        self.entry_cookie.pack(pady=5)
        self.entry_cookie.insert(0, self.config_data["authentication"].get("roblosecurity", ""))
        
        ctk.CTkLabel(scroll, text="Target Config", font=("Arial", 16, "bold")).pack(pady=(20, 5), anchor="w")
        self.entry_group = ctk.CTkEntry(scroll, placeholder_text="Target Group ID (Leave 0 for User)", width=600)
        self.entry_group.pack(pady=5)
        self.entry_group.insert(0, str(self.config_data["migration"].get("target_group_id", "")))
        
        ctk.CTkLabel(scroll, text="Networking", font=("Arial", 16, "bold")).pack(pady=(20, 5), anchor="w")
        self.entry_webhook = ctk.CTkEntry(scroll, placeholder_text="Discord Webhook URL", width=600)
        self.entry_webhook.pack(pady=5)
        self.entry_webhook.insert(0, self.config_data["migration"].get("webhook_url", ""))
        
        self.entry_proxy = ctk.CTkEntry(scroll, placeholder_text="Proxy (http://user:pass@ip:port)", width=600)
        self.entry_proxy.pack(pady=5)
        self.entry_proxy.insert(0, self.config_data["migration"].get("proxy", ""))
        
        ctk.CTkLabel(scroll, text="Source Place IDs (Spoofing Keys)", font=("Arial", 16, "bold")).pack(pady=(20, 5), anchor="w")
        self.textbox_pids = ctk.CTkTextbox(scroll, height=100, width=600)
        self.textbox_pids.pack(pady=5)
        
        source_pids = self.config_data["migration"].get("source_place_ids",[])
        pids_text = "\n".join([str(pid) for pid in source_pids])
        self.textbox_pids.insert("0.0", pids_text)
        
        ctk.CTkLabel(scroll, text="Asset Types", font=("Arial", 16, "bold")).pack(pady=(20, 5), anchor="w")
        
        self.switch_anim = ctk.CTkSwitch(scroll, text="Animations", onvalue=True, offvalue=False)
        self.switch_anim.pack(anchor="w", pady=2)
        if self.config_data["migration"].get("enabled_types", {}).get("animations", True): self.switch_anim.select()
        else: self.switch_anim.deselect()
        
        self.switch_audio = ctk.CTkSwitch(scroll, text="Audio", onvalue=True, offvalue=False)
        self.switch_audio.pack(anchor="w", pady=2)
        if self.config_data["migration"].get("enabled_types", {}).get("audio", False): self.switch_audio.select()
        else: self.switch_audio.deselect()
        
        self.switch_images = ctk.CTkSwitch(scroll, text="Images/Decals", onvalue=True, offvalue=False)
        self.switch_images.pack(anchor="w", pady=2)
        if self.config_data["migration"].get("enabled_types", {}).get("images", False): self.switch_images.select()
        else: self.switch_images.deselect()

        ctk.CTkButton(scroll, text="Save Settings", fg_color="green", command=self.save_config).pack(pady=30, fill="x")

    def show_migration(self):
        self.frame_manual.grid_forget()
        self.frame_settings.grid_forget()
        self.frame_migration.grid(row=0, column=1, sticky="nsew")
        sys.stdout = TextRedirector(self.console)

    def show_manual(self):
        self.frame_migration.grid_forget()
        self.frame_settings.grid_forget()
        self.frame_manual.grid(row=0, column=1, sticky="nsew")
        sys.stdout = TextRedirector(self.manual_console)

    def show_settings(self):
        self.frame_migration.grid_forget()
        self.frame_manual.grid_forget()
        self.frame_settings.grid(row=0, column=1, sticky="nsew")

    def select_input_file(self):
        filename = filedialog.askopenfilename(filetypes=[("Roblox XML", "*.rbxmx *.rbxlx")])
        if filename:
            self.config_data["migration"]["input_file"] = filename
            out = filename.replace(".rbxmx", "_Reuploaded.rbxmx").replace(".rbxlx", "_Reuploaded.rbxlx")
            self.config_data["migration"]["output_file"] = out
            self.lbl_input.configure(text=os.path.basename(filename))
            self.save_config()

    def start_migration_thread(self):
        self.save_config()
        self.btn_start.configure(state="disabled")
        t = threading.Thread(target=self.run_migration)
        t.start()

    def run_migration(self):
        print("Initializing Session...")
        try:
            with open("config.json", "r") as f:
                cfg = json.load(f)
            
            proxy = cfg["migration"].get("proxy")
            session = RobloxSession(cfg["authentication"]["roblosecurity"], proxy)
            
            migrator = AssetMigrator(session, cfg)
            migrator.run()
        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
        finally:
            self.btn_start.after(0, lambda: self.btn_start.configure(state="normal"))

    def start_manual_thread(self):
        ids = self.entry_asset_id.get()
        if not ids:
            print("Please enter ID(s).")
            return
            
        self.btn_download.configure(state="disabled")
        t = threading.Thread(target=self.run_manual, args=(ids,))
        t.start()

    def run_manual(self, raw_ids):
        try:
            downloader = ManualDownloader()
            id_list =[x.strip() for x in re.split(r'[ ,]+', raw_ids) if x.strip().isdigit()]
            print(f"Starting download for {len(id_list)} assets...")
            
            for asset_id in id_list:
                downloader.process_single_asset(asset_id, ask_name=False)
                
        except Exception as e:
            print(f"Error: {e}")
        finally:
            self.btn_download.after(0, lambda: self.btn_download.configure(state="normal"))
            print("Done.")

if __name__ == "__main__":
    app = LemonGUI()
    app.mainloop()