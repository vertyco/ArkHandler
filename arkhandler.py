import asyncio
import functools
import logging
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from configparser import ConfigParser
from datetime import datetime
from pathlib import Path

import win32evtlog
from colorama import Fore

from assets.customlogger import CustomFormatter, StandardFormatter
from assets.utils import (
    Const, set_resolution,
    send_webhook, kill, is_running, update_ready, is_updating,
    check_updates, sync_inis, start_ark, wipe_server, on_screen
)

# Window setup
os.system('title ArkHandler')
# Config setup
parser = ConfigParser()
# Log setup
log = logging.getLogger("arkhandler")
log.setLevel(logging.DEBUG)
# Console logs
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
console.setFormatter(CustomFormatter())
# File logs
logfile = logging.FileHandler('logs.log')
logfile.setLevel(logging.DEBUG)
logfile.setFormatter(StandardFormatter())
log.addHandler(console)
log.addHandler(logfile)


class ArkHandler:
    def __init__(self):
        # Handlers
        self.loop = asyncio.get_event_loop()
        self.threadpool = ThreadPoolExecutor(max_workers=5, thread_name_prefix="arkhandler")

        # Config
        self.configmtime = None
        self.debug = None
        self.hook = None
        self.game = None
        self.gameuser = None
        self.autowipe = None
        self.clustewipe = None
        self.wipetimes = None

        # Images
        self.images = {
            "start": fr"{os.getcwd()}\assets\start.PNG",
            "host": fr"{os.getcwd()}\assets\host.PNG",
            "run": fr"{os.getcwd()}\assets\run.PNG",
            "loaded": fr"{os.getcwd()}\assets\loaded.PNG"
        }

        # States
        self.running = False  # Ark is running
        self.checking_updates = False  # Checking for updates
        self.updating = False  # Is updating
        self.installing = False  # Is installing
        self.booting = False  # Is booting up
        self.last_update = None  # Time of last event update

    def initialize(self):
        print(Fore.LIGHTBLUE_EX + Const.logo + Fore.RESET)
        print(Fore.LIGHTGREEN_EX + "Version " + Const.VERSION + Fore.RESET)
        self.pull_config()
        if self.debug:
            info = f"Debug: {self.debug}\n" \
                   f"Webhook: {self.hook}\n" \
                   f"Game.ini: {self.game}\n" \
                   f"GameUserSettings.ini: {self.gameuser}\n" \
                   f"Autowipe: {self.autowipe}\n" \
                   f"Clusterwipe: {self.clustewipe}\n" \
                   f"WipeTimes: {self.wipetimes}"
            print(Fore.CYAN + info + Fore.RESET)
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            path = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets"))
            log.debug(f"Running as EXE - {path}")
            self.images = {
                "start": fr"{path}\start.PNG",
                "host": fr"{path}\host.PNG",
                "run": fr"{path}\run.PNG",
                "loaded": fr"{path}\loaded.PNG"
            }

    async def execute(self, partial_function: functools.partial):
        result = await self.loop.run_in_executor(self.threadpool, partial_function)
        return result

    def pull_config(self):
        conf = Path("config.ini")
        if not conf.exists():
            log.warning("No config detected! Creating new one")
            conf.write_text(Const.default_config)
        elif conf.stat().st_mtime == self.configmtime:
            return
        parser.read("config.ini")
        self.debug = parser.getboolean("Settings", "Debug")
        if not self.debug:
            console.setLevel(logging.INFO)
            logfile.setLevel(logging.INFO)
        self.hook = parser.get("Settings", "WebhookURL").strip(r'"')
        self.game = parser.get("Settings", "GameiniPath").strip(r'"')
        self.gameuser = parser.get("Settings", "GameUserSettingsiniPath").strip(r'"')
        self.autowipe = parser.getboolean("Settings", "AutoWipe")
        self.clustewipe = parser.getboolean("Settings", "AlsoWipeClusterData")

        try:
            wipetimes_raw = [i.strip() for i in parser.get("Settings", "WipeTimes").strip(r'"').split(",") if i.strip()]
            if wipetimes_raw:
                self.wipetimes = [datetime.strptime(i, "%m/%d %H:%M") for i in wipetimes_raw]
        except Exception as e:
            log.error(f"Failed to set wipe times, invalid format!\n{e}")
        log.debug("Config parsed")
        self.configmtime = conf.stat().st_mtime

    async def watchdog_loop(self):
        """Check every 30 seconds if Ark is running and start it if not"""
        while True:
            await asyncio.sleep(10)
            log.debug("Checking if Ark is running")
            await self.watchdog()
            await asyncio.sleep(20)

    async def watchdog(self):
        if is_running():
            if not self.running:
                log.info("Ark is running")
                self.running = True
            return

        # If ark is not running
        if self.running:
            log.warning("Ark is no longer running")
            self.running = False
        if any([self.updating, self.checking_updates, self.booting]):
            return
        log.info("Beginning reboot sequence")
        sync_inis(self.game, self.gameuser)
        await send_webhook(self.hook, "Server Down", "Beginning reboot sequence...", 16739584)
        self.booting = True
        try:
            await self.execute(functools.partial(start_ark, self.images))
            await send_webhook(self.hook, "Booting", "Loading server files...", 19357)
            await asyncio.sleep(10)
            os.system("net stop LicenseManager")
            while True:
                loc = await self.execute(functools.partial(on_screen, self.images["loaded"]))
                if loc is not None:
                    break
            log.info("Reboot complete")
            await send_webhook(self.hook, "Reboot Complete", "Server should be back online.", 65314)
        except Exception as e:
            log.critical(f"Critical error in ArkHandler!: {traceback.format_exc()}")
            await send_webhook(self.hook, "CRITICAL ERROR", f"```\n{e}\n```", 16711680)
            return
        finally:
            self.booting = False

    async def event_loop(self):
        while True:
            await asyncio.sleep(15)
            log.debug("Checking event log")
            await self.events()

    async def events(self):
        server = "localhost"
        logtype = "System"
        now = datetime.now()
        handle = win32evtlog.OpenEventLog(server, logtype)
        flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
        events = win32evtlog.ReadEventLog(handle, flags, 0)
        if not events:
            log.info("No events to pull")
            return

        for event in events:
            text = str(event.StringInserts[0])
            if "-StudioWildcard" in text:
                break
        else:
            return

        created = event.TimeGenerated
        if self.last_update == created:
            return
        eid = event.EventID
        td = (now - created).total_seconds()
        if td > 3600:
            log.info(f"Found update but it happened more than an hour ago")
            return

        if eid == 44 and not self.updating:
            log.warning(f"Download detected: {text}")
            await send_webhook(
                self.hook,
                "Download Detected!",
                Const.download,
                14177041,
                footer=f"File: {text}"
            )
            self.updating = True
        elif eid == 43 and not self.installing:
            log.warning(f"Install detected: {text}")
            await send_webhook(
                self.hook,
                "Installing",
                Const.install,
                1127128,
                footer=f"File: {text}"
            )
            self.installing = True
        elif eid == 19 and any([self.updating, self.installing]):
            log.warning(f"Update success: {text}")
            await send_webhook(
                self.hook,
                "Update Complete",
                Const.complete,
                65314,
                footer=f"File: {text}"
            )
            self.updating = False
            self.installing = False
        else:
            log.warning(f"No event for '{text}' with ID {eid}")

        self.last_update = created

    async def update_loop(self):
        while True:
            await asyncio.sleep(600)
            if self.checking_updates:
                continue
            log.debug("Checking for updates")
            self.checking_updates = True
            try:
                await self.updates()
            finally:
                self.checking_updates = False

    async def updates(self):
        app = await self.execute(functools.partial(check_updates))
        ready = await self.execute(functools.partial(update_ready, app, "ark"))
        await asyncio.sleep(30)
        updating = await self.execute(functools.partial(is_updating, app, "ark"))
        if not any([ready, updating]):
            kill("WinStore.App.exe")

    async def wipe_loop(self):
        while True:
            await asyncio.sleep(30)
            log.debug("Checking for wipes")
            await self.wipe()

    async def wipe(self):
        self.pull_config()
        if not self.autowipe:
            return
        if not self.wipetimes:
            return
        now = datetime.now()
        wipe = False
        for ts in self.wipetimes:
            time: datetime = ts
            conditions = [
                time.month == now.month,
                time.day == now.day,
                time.hour == now.hour,
                time.minute == now.minute
            ]
            if all(conditions):
                wipe = True
                break
        if not wipe:
            log.debug("No wipes available")
            return
        self.booting = True
        try:
            await self.execute(functools.partial(wipe_server, self.clustewipe))
            await asyncio.sleep(10)
        finally:
            self.booting = False


async def main():
    ark = ArkHandler()
    ark.initialize()
    tasks = [
        ark.watchdog_loop(),
        ark.event_loop(),
        ark.update_loop(),
        ark.wipe_loop()
    ]
    log.info("Starting task loops")
    await asyncio.gather(*tasks)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
    finally:
        set_resolution(default=True)

