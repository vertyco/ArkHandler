import asyncio
import configparser
import datetime
import json
import logging
import os
import shutil

import aiohttp
import colorama
import psutil
import pywinauto.mouse
import win32con
import win32evtlog
import win32gui
from colorama import Fore
from pywinauto.application import Application

"""
Calculating aspect ratios
x = measured x coordinate / total pixel width (ex: 500/1280)
y = measured y coordinate / total pixel height (ex: 300/720)
"""

TEAMVIEWER = (0.59562272, 0.537674419)
START = (0.49975574, 0.863596872)
HOST = (0.143624817, 0.534317984)
RUN = (0.497313141, 0.748913988)
ACCEPT1 = (0.424035173, 0.544743701)
ACCEPT2 = (0.564240352, 0.67593397)

INVITE = (0.8390625, 0.281944444)
EXIT = (0.66171875, 0.041666667)

os.system('title ArkHandler')
logging.basicConfig(filename='logs.log',
                    filemode='a',
                    format='%(asctime)s - %(levelname)s - %(message)s',
                    datefmt='%d-%b-%y %H:%M:%S')
log = logging.getLogger()
log.setLevel(logging.DEBUG)

user = os.environ['USERPROFILE']
appdata = "\\AppData\\Local\\Packages\\StudioWildcard.4558480580BB9_1w2mm55455e38\\LocalState\\Saved\\UWPConfig\\UWP"
TARGET = f"{user}{appdata}"
ARK_BOOT = "explorer.exe shell:appsFolder\StudioWildcard.4558480580BB9_1w2mm55455e38!AppARKSurvivalEvolved"
XAPP = "explorer.exe shell:appsFolder\Microsoft.XboxApp_8wekyb3d8bbwe!Microsoft.XboxApp"
LOGO = """
                _    _    _                 _ _           
     /\        | |  | |  | |               | | |          
    /  \   _ __| | _| |__| | __ _ _ __   __| | | ___ _ __ 
   / /\ \ | '__| |/ /  __  |/ _` | '_ \ / _` | |/ _ \ '__|
  / ____ \| |  |   <| |  | | (_| | | | | (_| | |  __/ |   
 /_/    \_\_|  |_|\_\_|  |_|\__,_|_| |_|\__,_|_|\___|_|   
                                                          
                                                          
  ___       __   __       _               
 | _ )_  _  \ \ / /__ _ _| |_ _  _ __ ___ 
 | _ \ || |  \ V / -_) '_|  _| || / _/ _ \\
 |___/\_, |   \_/\___|_|  \__|\_, \__\___/
      |__/                    |__/        
"""
colorama.init()
print(Fore.GREEN + LOGO)


def window_enumeration_handler(hwnd, windows):
    windows.append((hwnd, win32gui.GetWindowText(hwnd)))


class ArkHandler:
    def __init__(self):
        self.running = False
        self.checking_updates = False
        self.downloading = False
        self.updating = False
        self.installing = False
        self.booting = False
        self.last_update = None

        self.timestamp = ""

        self.top_windows = []

    @staticmethod
    async def import_config():
        if GAME_SOURCE != "":
            if os.path.exists(GAME_SOURCE) and os.path.exists(TARGET):
                s_file = os.path.join(GAME_SOURCE, "Game.ini")
                t_file = os.path.join(TARGET, "Game.ini")
                if os.path.exists(t_file):
                    try:
                        os.remove(t_file)
                    except Exception as ex:
                        print(Fore.RED + f"Failed to sync Game.ini\nError: {ex}")
                        log.warning(f"Failed to sync Game.ini\nError: {ex}")
                        return
                if not os.path.exists(s_file):
                    print(Fore.RED + f"Cannot find source Game.ini file!")
                    log.warning(f"Cannot find source Game.ini file!")
                    return
                shutil.copyfile(s_file, t_file)
                print(Fore.CYAN + "Game.ini synced.")

        # sync GameUserSettings.ini file
        if GAMEUSERSETTINGS_SOURCE != "":
            if os.path.exists(GAMEUSERSETTINGS_SOURCE) and os.path.exists(TARGET):
                s_file = os.path.join(GAMEUSERSETTINGS_SOURCE, "GameUserSettings.ini")
                t_file = os.path.join(TARGET, "GameUserSettings.ini")
                if os.path.exists(t_file):
                    try:
                        os.remove(t_file)
                    except Exception as ex:
                        print(Fore.RED + f"Failed to sync GameUserSettings.ini\nError: {ex}")
                        log.warning(f"Failed to sync GameUserSettings.ini\nError: {ex}")
                        return
                if not os.path.exists(s_file):
                    print(Fore.RED + f"Cannot find source GameUserSettings.ini file!")
                    log.warning(f"Cannot find source GameUserSettings.ini file!")
                    return
                shutil.copyfile(s_file, t_file)
                print(Fore.CYAN + "GameUserSettings.ini synced.")

    @staticmethod
    async def calc_position_click(clicktype, action=None):
        # get clicktype ratios
        x = clicktype[0]
        y = clicktype[1]

        # grab ark window
        window_handle = win32gui.FindWindow(None, "ARK: Survival Evolved")
        window_rect = win32gui.GetWindowRect(window_handle)
        # check if window is maximized and maximize it if not
        tup = win32gui.GetWindowPlacement(window_handle)
        if tup[1] != win32con.SW_SHOWMAXIMIZED:
            window = win32gui.GetForegroundWindow()
            win32gui.ShowWindow(window, win32con.SW_MAXIMIZE)
            window_handle = win32gui.FindWindow(None, "ARK: Survival Evolved")
            window_rect = win32gui.GetWindowRect(window_handle)

        # sort window borders
        right = window_rect[2]
        bottom = window_rect[3] + 20

        # get click positions
        x_click = right * x
        y_click = bottom * y

        # click dat shit
        if action == "double":
            pywinauto.mouse.double_click(button='left', coords=(int(x_click), int(y_click)))
        else:
            pywinauto.mouse.click(button='left', coords=(int(x_click), int(y_click)))

    @staticmethod
    async def send_hook(title, message, color, msg=None):
        if not WEBHOOK_URL:
            return
        if msg:
            data = {"username": "ArkHandler", "avatar_url": "https://i.imgur.com/Wv5SsBo.png", "embeds": [
                {
                    "description": message,
                    "title": title,
                    "color": color,
                    "footer": {"text": msg}
                }
            ]}
        else:
            data = {"username": "ArkHandler", "avatar_url": "https://i.imgur.com/Wv5SsBo.png", "embeds": [
                {
                    "description": message,
                    "title": title,
                    "color": color
                }
            ]}
        headers = {
            "Content-Type": "application/json"
        }
        print(Fore.WHITE + "Attempting to send webhook")
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=20)
                async with session.post(
                        url=WEBHOOK_URL,
                        data=json.dumps(data),
                        headers=headers,
                        timeout=timeout) as res:
                    if res.status == 204:
                        print(Fore.GREEN + f"Sent {title} Webhook - Status: {res.status}")
                    else:
                        print(Fore.RED + f"{title} Webhook may have failed - Status: {res.status}")
                        log.warning(f"{title} Webhook may have failed - Status: {res.status}")
        except Exception as e:
            log.warning(f"SendHook: {e}")

    @staticmethod
    async def ark():
        if "ShooterGame.exe" in (p.name() for p in psutil.process_iter()):
            return True

    @staticmethod
    async def kill_ark():
        for p in psutil.process_iter():
            if p.name() == "ShooterGame.exe":
                p.kill()

    @staticmethod
    async def store():
        if "WinStore.App.exe" in (p.name() for p in psutil.process_iter()):
            return True

    async def kill_store(self):
        # check if teamviewer sponsored session window is open
        if not self.updating:
            for p in psutil.process_iter():
                if p.name() == "WinStore.App.exe":
                    try:
                        p.kill()
                    except Exception as ex:
                        log.warning(f"WinStore App failed to terminate!\nError: {ex}")

    async def close_tv(self):
        self.top_windows = []
        win32gui.EnumWindows(window_enumeration_handler, self.top_windows)
        for window in self.top_windows:
            if "sponsored session" in window[1].lower():
                print("Closing teamviewer sponsored session window")
                handle = win32gui.FindWindow(None, window[1])
                win32gui.SetForegroundWindow(handle)
                win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
                await asyncio.sleep(1)
                break

    async def watchdog(self):
        """Check every 30 seconds if Ark is running, and start the server if it is not."""
        while True:
            if await self.ark():
                if not self.running:
                    print(Fore.CYAN + "Ark is Running.")
                    self.running = True
            else:
                if not self.updating and not self.checking_updates and not self.booting:
                    print(Fore.RED + "Ark is not Running! Beginning reboot sequence...")
                    try:
                        await self.import_config()
                        await self.send_hook("Server Down", "Beginning reboot sequence...", 16739584)
                        await self.boot_ark()
                    except Exception as e:
                        log.warning(f"Watchdog: {e}")
            await asyncio.sleep(30)

    async def boot_ark(self):
        self.running = False
        self.booting = True
        if await self.ark():
            await self.kill_ark()
            await asyncio.sleep(20)
        await asyncio.sleep(5)
        await self.close_tv()
        # start ark
        print(Fore.MAGENTA + "Attempting to launch Ark")
        os.system(ARK_BOOT)
        await asyncio.sleep(15)
        # make sure ark is actually fucking running and didnt crash
        if not await self.ark():
            print(Fore.RED + "Ark crashed, trying again... (Thanks Wildcard)")
            os.system(ARK_BOOT)
            await asyncio.sleep(12)

        await self.calc_position_click(START, "double")
        await asyncio.sleep(8)
        await self.calc_position_click(HOST)
        await asyncio.sleep(4)
        await self.calc_position_click(RUN)
        await asyncio.sleep(2)
        await self.calc_position_click(ACCEPT1)
        await asyncio.sleep(2)
        await self.calc_position_click(ACCEPT2)

        print(Fore.GREEN + "Boot macro finished, loading server files.")
        await self.send_hook("Booting", "Loading server files...", 19357)
        await asyncio.sleep(10)
        print(Fore.YELLOW + "Stopping LicenseManager")
        os.system("net stop LicenseManager")
        await asyncio.sleep(60)
        await self.send_hook("Reboot Complete", "Server should be back online.", 65314)
        self.booting = False

    async def event_puller(self):
        """Gets most recent update event for ark and determines how recent it was"""
        while True:
            await asyncio.sleep(5)
            try:
                await self.pull_events()
            except Exception as e:
                log.warning(f"EventPuller: {e}")

    async def pull_events(self):
        server = 'localhost'
        logtype = 'System'
        now = datetime.datetime.now()
        hand = win32evtlog.OpenEventLog(server, logtype)
        flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        for event in events:
            data = event.StringInserts
            if "-StudioWildcard" in str(data[0]):
                if self.last_update == event.TimeGenerated:
                    return

                eid = event.EventID
                string = data[0]

                td = now - event.TimeGenerated
                if td.total_seconds() < 3600:
                    recent = True
                else:
                    recent = False

                if eid == 44 and recent and not self.updating:
                    print(Fore.RED + f"DOWNLOAD DETECTED: {string}")
                    await self.send_hook(
                        "Download Detected!",
                        DOWNLOAD_MESSAGE,
                        14177041,
                        f"File: {string}"
                    )
                    self.updating = True

                elif eid == 43 and recent and not self.installing:
                    print(Fore.MAGENTA + f"INSTALL DETECTED: {string}")
                    await self.send_hook(
                        "Installing",
                        INSTALL_MESSAGE,
                        1127128,
                        f"File: {string}"
                    )
                    self.installing = True

                elif eid == 19 and recent:
                    if self.updating or self.installing:
                        print(Fore.GREEN + f"UPDATE SUCCESS: {string}")
                        await self.send_hook(
                            "Update Complete",
                            COMPLETED_MESSAGE,
                            65314,
                            f"File: {string}"
                        )
                        await asyncio.sleep(20)
                        self.updating = False
                        self.installing = False
                        await self.boot_ark()
                self.last_update = event.TimeGenerated
                return

    async def update_checker(self):
        while True:
            try:
                await asyncio.sleep(600)
                await self.check_updates()
                await asyncio.sleep(100)
                await self.kill_store()
            except Exception as e:
                log.warning(f"UpdateChecker: {e}")

    async def check_updates(self):
        if not self.booting and self.running:
            self.checking_updates = True
            if not await self.store():
                os.system("explorer.exe shell:appsFolder\Microsoft.WindowsStore_8wekyb3d8bbwe!App")
                await asyncio.sleep(3)
            else:
                program = "microsoft store"
                self.top_windows = []
                win32gui.EnumWindows(window_enumeration_handler, self.top_windows)
                for window in self.top_windows:
                    if program in window[1].lower():
                        win32gui.ShowWindow(window[0], win32con.SW_MAXIMIZE)

            app = Application(backend="uia").connect(title="Microsoft Store")
            await asyncio.sleep(3)
            for button in app.windows()[0].descendants():
                if "Library" in str(button):
                    button.click_input()
                    await asyncio.sleep(2)
                    for button2 in app.windows()[0].descendants(control_type="Button"):
                        if "Get updates" in str(button2):
                            button2.click()
                            window = win32gui.GetForegroundWindow()
                            win32gui.ShowWindow(window, win32con.SW_MINIMIZE)
                            await asyncio.sleep(5)
            self.checking_updates = False


try:
    Config = configparser.ConfigParser()
    Config.read("config.ini")
    WEBHOOK_URL = Config.get("UserSettings", "webhookurl").strip('\"')
    DOWNLOAD_MESSAGE = Config.get("UserSettings", "downloadmessage").strip('\"')
    INSTALL_MESSAGE = Config.get("UserSettings", "installmessage").strip('\"')
    COMPLETED_MESSAGE = Config.get("UserSettings", "completedmessage").strip('\"')
    GAME_SOURCE = Config.get("UserSettings", "gameinipath").strip('\"')
    GAMEUSERSETTINGS_SOURCE = Config.get("UserSettings", "gameusersettingsinipath").strip('\"')
    print(Fore.WHITE + f"Config importing:\n{GAME_SOURCE}\n{GAMEUSERSETTINGS_SOURCE}")
except Exception as e:
    print(Fore.RED + f"Config failed to import!\nError: {e}")
    log.warning(f"Config failed to import!\nError: {e}")

loop = asyncio.get_event_loop()
at = ArkHandler()
try:
    asyncio.ensure_future(at.event_puller())
    asyncio.ensure_future(at.watchdog())
    asyncio.ensure_future(at.update_checker())
    loop.run_forever()
finally:
    loop.close()
