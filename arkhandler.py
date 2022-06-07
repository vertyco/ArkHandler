import asyncio
import configparser
import json
import logging
import os
import shutil
from datetime import datetime
from time import sleep

import aiohttp
import colorama
import psutil
import pywinauto.mouse
import win32con
import win32evtlog
import win32gui
from colorama import Fore
from pywinauto.application import Application
from customlogger import CustomFormatter, StandardFormatter

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

# Define logging
# logging.basicConfig(
#     level=logging.INFO,
#     format='%(asctime)s - %(levelname)s - %(message)s',
#     handlers=[logging.FileHandler('logs.log'), logging.StreamHandler()],
#     datefmt='%m/%d %I:%M:%S %p',
# )
log = logging.getLogger(__name__)
log.setLevel(logging.DEBUG)

console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
console.setFormatter(CustomFormatter())

logfile = logging.FileHandler('logs.log')
logfile.setLevel(logging.DEBUG)
logfile.setFormatter(StandardFormatter())

log.addHandler(console)
log.addHandler(logfile)

# log.debug("debug message")
# log.info("info message")
# log.warning("warning message")
# log.error("error message")
# log.critical("critical message")

DOWNLOAD_MESSAGE = "**The server has started downloading an update, and will go down once it starts installing.**"
INSTALL_MESSAGE = "**The server has started installing the update. Stand by...**"
COMPLETED_MESSAGE = "**The server has finished installing the update.**"

user = os.environ['USERPROFILE']
MAIN = f"{os.environ['LOCALAPPDATA']}/Packages/StudioWildcard.4558480580BB9_1w2mm55455e38/LocalState/Saved"
TARGET = f"{MAIN}/UWPConfig/UWP"
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
version = "Version: 2.0.3"
print(f"{Fore.LIGHTCYAN_EX}{LOGO}\n{version}{Fore.RESET}")

DEFAULT = """
# Create a webhook URL for the discord channel this rig hosts and paste it in the quotes to have the bot send update alerts.
# The webhook messages can also be configured below.

# The Path settings is the folder path to your backup ini files if you have them (gameusersettings.ini and game.ini). 
# When ArkHandler reboots the server,
# it will pull the newest ini files from those paths and inject them into your appdata settings.

# Wipe times should always be "mm/dd HH:MM" separated by a comma with NO spaces, like 04/10 12:30,08/20 17:00
# Debug field, if True, shows extra data in the console(for debug purposes)

[UserSettings]
WebhookURL = ""
GameiniPath = ""
GameUserSettingsiniPath = ""
AutoWipe = False
AlsoWipeClusterData = False
WipeTimes = 
Debug = False
"""


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

        self.cf = configparser.ConfigParser()
        self.config = {
            "webhook": "",
            "game": "",
            "gameuser": "",
            "autowipe": False,
            "clusterwipe": False,
            "wipetimes": [],
            "debug": False,
            "pulled": True
        }

    def pull_config(self):
        while True:
            try:
                self.cf.read("config.ini")
                debug = self.cf.get("UserSettings", "debug").strip('\"')
                if debug and "t" in debug.lower():
                    console.setLevel(logging.DEBUG)
                    debug = True
                else:
                    console.setLevel(logging.INFO)
                    debug = False

                if debug:
                    log.debug("Pulling config")

                self.config = {
                    "webhook": self.cf.get("UserSettings", "webhookurl").strip('\"'),
                    "game": self.cf.get("UserSettings", "gameinipath").strip('\"'),
                    "gameuser": self.cf.get("UserSettings", "gameusersettingsinipath").strip('\"'),
                    "autowipe": self.cf.get("UserSettings", "autowipe").strip('\"'),
                    "clusterwipe": self.cf.get("UserSettings", "alsowipeclusterdata").strip('\"'),
                    "wipetimes": self.cf.get("UserSettings", "wipetimes"),
                    "debug": debug,
                    "pulled": True
                }
                if "t" in self.config["autowipe"].lower():
                    self.config["autowipe"] = True
                else:
                    self.config["autowipe"] = False
                if "t" in self.config["clusterwipe"].lower():
                    self.config["clusterwipe"] = True
                else:
                    self.config["clusterwipe"] = False
                self.config["wipetimes"] = self.config["wipetimes"].split(",")
                break
            except (configparser.NoOptionError, configparser.NoSectionError):
                log.warning(f"Config failed to read! Creating a new one!")
                try:
                    with open("config.ini", "w") as f:
                        f.write(DEFAULT)
                except Exception as e:
                    log.warning(f"Cant write default config!!: {e}")
                    break
                continue
            except Exception as e:
                log.warning(f"Failed to pull config: {e}")
                break

    async def sync_config(self):
        if self.config["game"]:
            if os.path.exists(self.config["game"]) and os.path.exists(TARGET):
                s_file = os.path.join(self.config["game"], "Game.ini")
                t_file = os.path.join(TARGET, "Game.ini")
                if os.path.exists(t_file):
                    try:
                        os.remove(t_file)
                    except Exception as ex:
                        log.warning(f"Failed to sync Game.ini\nError: {ex}")
                        return
                if not os.path.exists(s_file):
                    log.warning(f"Cannot find source Game.ini file!")
                    return
                shutil.copyfile(s_file, t_file)
                log.info("Game.ini synced.")

        # sync GameUserSettings.ini file
        if self.config["gameuser"]:
            if os.path.exists(self.config["gameuser"]) and os.path.exists(TARGET):
                s_file = os.path.join(self.config["gameuser"], "GameUserSettings.ini")
                t_file = os.path.join(TARGET, "GameUserSettings.ini")
                if os.path.exists(t_file):
                    try:
                        os.remove(t_file)
                    except Exception as ex:
                        log.warning(f"Failed to sync GameUserSettings.ini\nError: {ex}")
                        return
                if not os.path.exists(s_file):
                    log.warning(f"Cannot find source GameUserSettings.ini file!")
                    return
                shutil.copyfile(s_file, t_file)
                log.info("GameUserSettings.ini synced.")

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

    async def send_hook(self, title, message, color, msg=None):
        if not self.config["webhook"]:
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
        log.info("Attempting to send webhook")
        try:
            async with aiohttp.ClientSession() as session:
                timeout = aiohttp.ClientTimeout(total=20)
                async with session.post(
                        url=self.config["webhook"],
                        data=json.dumps(data),
                        headers=headers,
                        timeout=timeout) as res:
                    if res.status == 204:
                        log.info(f"Sent {title} Webhook - Status: {res.status}")
                    else:
                        log.warning(f"{title} Webhook may have failed - Status: {res.status}")
        except Exception as e:
            log.warning(f"SendHook Error: {e}")

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
                log.debug("Closing teamviewer sponsored session window")
                handle = win32gui.FindWindow(None, window[1])
                win32gui.SetForegroundWindow(handle)
                win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
                await asyncio.sleep(1)
                break

    async def watchdog(self):
        """Check every 30 seconds if Ark is running, and start the server if it is not."""
        while True:
            if not self.config["pulled"]:
                continue
            if await self.ark():
                if not self.running:
                    log.info("Ark is Running.")
                    self.running = True
            else:
                if not self.updating and not self.checking_updates and not self.booting:
                    log.info("Ark is not Running! Beginning reboot sequence...")
                    try:
                        await self.sync_config()
                        await self.send_hook("Server Down", "Beginning reboot sequence...", 16739584)
                        await self.boot_ark()
                    except Exception as e:
                        log.critical(f"Watchdog Error: {e}")
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
        log.info("Attempting to launch Ark")
        os.system(ARK_BOOT)
        await asyncio.sleep(15)
        # make sure ark is actually fucking running and didnt crash
        if not await self.ark():
            log.warning("Ark crashed, trying again... (Thanks Wildcard)")
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

        log.info("Boot macro finished, loading server files.")
        await self.send_hook("Booting", "Loading server files...", 19357)
        await asyncio.sleep(10)
        log.debug("Stopping LicenseManager")
        os.system("net stop LicenseManager")
        await asyncio.sleep(60)
        await self.send_hook("Reboot Complete", "Server should be back online.", 65314)
        self.booting = False

    async def event_puller(self):
        """Gets most recent update event for ark and determines how recent it was"""
        while True:
            if not self.config["pulled"]:
                await asyncio.sleep(10)
                continue
            log.debug("Pulling events")
            await asyncio.sleep(5)
            try:
                await self.pull_events()
            except Exception as e:
                log.error(f"EventPuller: {e}")

    async def pull_events(self):
        server = 'localhost'
        logtype = 'System'
        now = datetime.now()
        hand = win32evtlog.OpenEventLog(server, logtype)
        flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
        events = win32evtlog.ReadEventLog(hand, flags, 0)
        for event in events:
            await asyncio.sleep(0.001)
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
                    log.warning(f"DOWNLOAD DETECTED: {string}")
                    await self.send_hook(
                        "Download Detected!",
                        DOWNLOAD_MESSAGE,
                        14177041,
                        f"File: {string}"
                    )
                    self.updating = True

                elif eid == 43 and recent and not self.installing:
                    log.warning(f"INSTALL DETECTED: {string}")
                    await self.send_hook(
                        "Installing",
                        INSTALL_MESSAGE,
                        1127128,
                        f"File: {string}"
                    )
                    self.installing = True

                elif eid == 19 and recent:
                    if self.updating or self.installing:
                        log.warning(f"UPDATE SUCCESS: {string}")
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
            if not self.config["pulled"]:
                continue
            try:
                await asyncio.sleep(600)
                log.debug("Checking for updates")
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

    async def wipe_checker(self):
        while True:
            if not self.config["pulled"]:
                continue
            log.debug("Checking wipe schedule")
            if not self.config["autowipe"] or not self.config["wipetimes"]:
                await asyncio.sleep(15)
                continue
            now = datetime.now()
            for ts in self.config["wipetimes"]:
                time = datetime.strptime(ts, "%m/%d %H:%M")
                if time.month != now.month:
                    continue
                if time.day != now.day:
                    continue
                if time.hour != now.hour:
                    continue
                td = time.minute - now.minute

                if td == 0:
                    log.debug("Wipe time IS NOW")
                    await self.wipe(self.config["clusterwipe"])
                    await asyncio.sleep(60)
                    break
            else:
                await asyncio.sleep(5)

    async def wipe(self, wipe_cluster_data):
        log.warning("WIPING MAP")
        self.booting = True
        await self.kill_ark()
        if wipe_cluster_data:
            log.warning("WIPING CLUSTER DATA")
            cpath = f"{MAIN}/clusters/solecluster/"
            if not os.listdir(cpath):
                pass
            else:
                for cname in os.listdir(cpath):
                    if "sync" in cname:
                        continue
                    os.remove(os.path.join(cpath, cname))
        else:
            log.warning("NOT WIPING CLUSTER DATA")

        maps = f"{MAIN}/Maps"
        for foldername in os.listdir(maps):
            if "ClientPaintingsCache" in foldername:
                continue
            if "sync" in foldername:
                continue
            mapfolder = f"{maps}/{foldername}"

            # Only the island has no subfolder
            subfolder = True
            if foldername == "SavedArks":
                subfolder = False

            if not subfolder:
                mapcontents = os.listdir(mapfolder)
            else:
                mapfolder = f"{mapfolder}/{os.listdir(mapfolder)[0]}"
                mapcontents = os.listdir(mapfolder)

            for item in mapcontents:
                if "ServerPaintingsCache" in item:
                    continue
                if "BanList" in item:
                    continue
                if os.path.isdir(os.path.join(mapfolder, item)):
                    continue
                os.remove(os.path.join(mapfolder, item))
        self.booting = False
        log.warning("WIPE COMPLETE")

    async def config_puller(self):
        while True:
            self.pull_config()
            if self.config["debug"]:
                await asyncio.sleep(10)
            else:
                await asyncio.sleep(300)


def main():
    loop = asyncio.new_event_loop()
    at = ArkHandler()
    try:
        loop.create_task(at.config_puller())
        loop.create_task(at.watchdog())
        loop.create_task(at.event_puller())
        loop.create_task(at.update_checker())
        loop.create_task(at.wipe_checker())
        loop.run_forever()
    finally:
        loop.close()


if __name__ == "__main__":
    main()
