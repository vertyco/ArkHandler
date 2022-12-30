import asyncio
import functools
import logging
import os
import sys
import traceback
from concurrent.futures import ThreadPoolExecutor
from configparser import ConfigParser, NoOptionError, NoSectionError
from datetime import datetime
from logging import handlers
from pathlib import Path
from subprocess import DEVNULL, call

import win32evtlog
from aiohttp import ClientConnectionError, ClientSession, ClientTimeout
from colorama import Fore, Style

from utils import (
    Const,
    PrettyFormatter,
    StandardFormatter,
    check_updates,
    get_rcon_info,
    is_running,
    is_updating,
    kill,
    on_screen,
    run_rcon,
    send_webhook,
    set_resolution,
    start_ark,
    sync_inis,
    update_ready,
    wipe_server,
)

# Config setup
parser = ConfigParser()
# Log setup
log = logging.getLogger("arkhandler")
log.setLevel(logging.DEBUG)
# Console logs
console = logging.StreamHandler()
console.setFormatter(PrettyFormatter())
# File logs
logfile = handlers.RotatingFileHandler(
    "logs.log", mode="a", maxBytes=5 * 1024 * 1024, backupCount=3
)
logfile.setFormatter(StandardFormatter())
# Add handlers
log.addHandler(console)
log.addHandler(logfile)


class ArkHandler:
    """Compile with 'pyinstaller.exe --clean main.spec'"""

    __version__ = "3.2.15"

    def __init__(self):
        # Handlers
        self.loop = None
        self.threadpool = ThreadPoolExecutor(
            max_workers=5, thread_name_prefix="arkhandler"
        )

        # Config
        self.configmtime = None
        self.debug = None
        self.hook = None
        self.game = None
        self.gameuser = None
        self.autowipe = None
        self.clustewipe = None
        self.wipetimes = None

        # Pulled cache
        self.port = 0
        self.passwd = None

        # Data dir
        self.root = os.path.abspath(os.path.dirname(__file__))  # arkhandler folder

        # ArkViewer
        self.viewer = os.path.join(self.root, "viewer")

        # Images
        self.assets = os.path.join(self.root, "assets")
        self.images = {
            "start": rf"{self.assets}\start.PNG",
            "host": rf"{self.assets}\host.PNG",
            "run": rf"{self.assets}\run.PNG",
            "loaded": rf"{self.assets}\loaded.PNG",
        }

        # States
        self.running = False  # Ark is running
        self.checking_updates = False  # Checking for updates
        self.updating = False  # Is updating
        self.installing = False  # Is installing
        self.booting = False  # Is booting up
        self.last_update = None  # Time of last event update
        self.no_internet = False  # Whether script can ping google
        self.netdownkill = (
            0  # Time in minutes for internet to be down before killing server
        )
        self.last_online = datetime.now()  # Timestamp of when server was last online

    async def initialize(self):
        print(Fore.CYAN + Style.BRIGHT + Const.logo)
        self.loop = asyncio.get_event_loop()
        try:
            self.pull_config()
        except (NoOptionError, NoSectionError) as e:
            log.critical(
                f"Config Error: {e.message}\nPress ENTER to confirm and close ArkHandler"
            )
            input()
            return
        log.debug(f"Python version {sys.version}")
        if self.debug:
            info = (
                f"Debug: {self.debug}\n"
                f"Webhook: {self.hook}\n"
                f"Game.ini: {self.game}\n"
                f"GameUserSettings.ini: {self.gameuser}\n"
                f"Autowipe: {self.autowipe}\n"
                f"Clusterwipe: {self.clustewipe}\n"
                f"WipeTimes: {self.wipetimes}"
            )
            print(Fore.CYAN + info)
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            log.debug(f"Running as EXE - {self.root}")
        tasks = [
            self.running_loop(),
            self.watchdog_loop(),
            self.event_loop(),
            self.update_loop(),
            self.wipe_loop(),
            self.internet_loop(),
        ]
        log.info("Starting task loops")
        await asyncio.gather(*tasks)

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
        settings = parser["UserSettings"]
        prev = self.debug
        self.debug = settings.getboolean("Debug", fallback=False)
        if prev is not None:
            if self.debug and not prev:
                log.info("Debug has been changed to True")
            elif prev and not self.debug:
                log.info("Debug has been changed to False")

        if self.debug:
            console.setLevel(logging.DEBUG)
            logfile.setLevel(logging.DEBUG)
        else:
            console.setLevel(logging.INFO)
            logfile.setLevel(logging.INFO)

        self.netdownkill = settings.getint("NetDownKill", fallback=0)
        self.hook = settings.get("WebhookURL", fallback="").replace('"', "")
        self.game = settings.get("GameiniPath", fallback="").replace('"', "")
        self.gameuser = settings.get("GameUserSettingsiniPath", fallback="").replace(
            '"', ""
        )
        self.autowipe = settings.getboolean("AutoWipe", fallback=False)
        self.clustewipe = settings.getboolean("AlsoWipeClusterData", fallback=False)

        wipetimes = settings.get("WipeTimes", fallback="").strip(r'"').split(",")
        rawtimes = [i.strip() for i in wipetimes if i.strip()]
        try:
            self.wipetimes = [datetime.strptime(i, "%m/%d %H:%M") for i in rawtimes]
        except ValueError as e:
            log.error(f"Failed to set wipe times: {e}")

        log.debug("Config parsed")
        self.configmtime = conf.stat().st_mtime

        port, passwd = get_rcon_info()
        self.port = port
        self.passwd = passwd

    async def running_loop(self):
        # Keep the window title animated, so we know it isn't frozen
        bar = [
            "▱▱▱▱▱▱▱",
            "▰▱▱▱▱▱▱",
            "▰▰▱▱▱▱▱",
            "▰▰▰▱▱▱▱",
            "▰▰▰▰▱▱▱",
            "▰▰▰▰▰▱▱",
            "▰▰▰▰▰▰▱",
            "▰▰▰▰▰▰▰",
            "▱▰▰▰▰▰▰",
            "▱▱▰▰▰▰▰",
            "▱▱▱▰▰▰▰",
            "▱▱▱▱▰▰▰",
            "▱▱▱▱▱▰▰",
            "▱▱▱▱▱▱▰",
        ]
        index = 0
        while True:
            cmd = f"title ArkHandler {self.__version__} {bar[index]}"
            os.system(cmd)
            index += 1
            index %= len(bar)
            await asyncio.sleep(0.1)

    async def watchdog_loop(self):
        """Check every 30 seconds if Ark is running and start it if not"""
        while True:
            await asyncio.sleep(10)
            log.debug("Checking if Ark is running")
            try:
                await self.watchdog()
            except Exception:
                log.warning(f"Watchdog loop failed!\n{traceback.format_exc()}")
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
        if any([self.updating, self.checking_updates, self.booting, self.no_internet]):
            return
        log.info("Syncing ini files")
        await self.execute(functools.partial(sync_inis, self.game, self.gameuser))
        await send_webhook(
            self.hook, "Server Down", "Beginning reboot sequence...", 16739584
        )
        self.booting = True
        log.info("Beginning reboot sequence")
        try:
            await self.execute(functools.partial(start_ark, self.images))
            await send_webhook(self.hook, "Booting", "Loading server files...", 19357)
            await asyncio.sleep(10)
            call(
                "net stop LicenseManager", stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL
            )
            while True:
                if not is_running():
                    self.booting = False
                    await send_webhook(
                        self.hook, "Boot Failed", "Trying again...", 19357
                    )
                    return
                loc = await self.execute(
                    functools.partial(on_screen, self.images["loaded"])
                )
                if loc is None:
                    continue
                elif loc is False:
                    log.error("Loaded image seems to be missing!")
                    await asyncio.sleep(60)
                    break
                else:
                    break
            log.info("Reboot complete")
            await send_webhook(
                self.hook, "Reboot Complete", "Server should be back online.", 65314
            )
        except Exception as e:
            log.critical(f"Critical error in ArkHandler!\n{traceback.format_exc()}")
            await send_webhook(
                self.hook,
                "CRITICAL ERROR",
                f"```\n{e}\n```Sleeping for 30 minutes before trying again",
                16711680,
            )
            await asyncio.sleep(1800)
            return
        finally:
            self.booting = False

    async def event_loop(self):
        while True:
            await asyncio.sleep(15)
            if self.no_internet:
                continue
            log.debug("Checking event log")
            try:
                await self.events()
            except Exception:
                log.warning(f"Event loop failed!\n{traceback.format_exc()}")

    async def events(self):
        server = "localhost"
        logtype = "System"
        now = datetime.now()
        handle = win32evtlog.OpenEventLog(server, logtype)
        flags = (
            win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
        )
        events = win32evtlog.ReadEventLog(handle, flags, 0)
        if not events:
            log.info("No events to pull")
            return

        for event in events:
            event_data = event.StringInserts
            if not event_data:
                continue
            if "-StudioWildcard" in str(event_data[0]):
                text = str(event_data[0])
                break
        else:
            return

        created = event.TimeGenerated
        if self.last_update == created:
            return
        eid = event.EventID
        td = (now - created).total_seconds()
        if td > 3600:
            log.info("Found update but it happened more than an hour ago")
            self.last_update = created
            return

        if eid == 44 and not self.updating:
            log.warning(f"Download detected: {text}")
            await send_webhook(
                self.hook,
                "Download Detected!",
                Const.download,
                14177041,
                footer=f"File: {text}",
            )
            self.updating = True
        elif eid == 43 and not self.installing:
            log.warning(f"Install detected: {text}")
            await send_webhook(
                self.hook, "Installing", Const.install, 1127128, footer=f"File: {text}"
            )
            self.installing = True
        elif eid == 19 and any([self.updating, self.installing]):
            log.warning(f"Update success: {text}")
            await send_webhook(
                self.hook,
                "Update Complete",
                Const.complete,
                65314,
                footer=f"File: {text}",
            )
            await asyncio.sleep(60)
            kill()
            self.updating = False
            self.installing = False
        else:
            log.warning(f"No event for '{text}' with ID {eid}")

        self.last_update = created

    async def update_loop(self):
        while True:
            await asyncio.sleep(600)
            skip_conditions = [
                self.checking_updates,
                self.no_internet,
                self.booting,
                self.updating,
            ]
            if any(skip_conditions):
                continue
            log.debug("Checking for updates")
            self.checking_updates = True
            try:
                await self.updates()
            except Exception:
                log.warning(f"Update loop failed!\n{traceback.format_exc()}")
            finally:
                self.checking_updates = False

    async def updates(self):
        kill("WinStore.App.exe")
        await asyncio.sleep(5)
        app = await self.execute(functools.partial(check_updates))
        if not app:
            return
        ready = await self.execute(functools.partial(update_ready, app, "ark"))
        await asyncio.sleep(30)
        updating = await self.execute(functools.partial(is_updating, app, "ark"))
        if not any([ready, updating]):
            kill("WinStore.App.exe")

    async def wipe_loop(self):
        while True:
            await asyncio.sleep(10)
            log.debug("Checking for wipes")
            try:
                await self.wipe()
            except Exception:
                log.warning(f"WIpe loop failed!\n{traceback.format_exc()}")

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
                time.minute == now.minute,
            ]
            if all(conditions):
                wipe = True
                break

        if not wipe:
            return
        self.booting = True
        try:
            await send_webhook(
                self.hook, "WIPING SERVER", "Shutting down to wipe...", 16776960
            )
            kill()
            await asyncio.sleep(10)
            await self.execute(functools.partial(wipe_server, self.clustewipe))
            await asyncio.sleep(65)
        finally:
            self.booting = False

    async def internet_loop(self):
        while True:
            await asyncio.sleep(30)
            if self.netdownkill == 0:
                continue
            log.debug("Checking internet connection")
            try:
                await self.internet()
            except Exception:
                log.warning(f"internet loop failed!\n{traceback.format_exc()}")

    async def internet(self):
        now = datetime.now()
        failed = False
        try:
            async with ClientSession(timeout=ClientTimeout(total=30)) as session:
                async with session.get("https://www.google.com") as res:
                    if res.status < 200 or res.status > 204:
                        failed = True
        except (ClientConnectionError, TimeoutError):
            failed = True

        if failed:
            if not self.no_internet:
                log.critical("Internet is down!")
            self.no_internet = True
            td = (now - self.last_online).total_seconds()
            if (td / 60) > self.netdownkill and is_running():
                if all([self.port, self.passwd, not self.booting, not self.updating]):
                    try:
                        res = await run_rcon("saveworld", self.port, self.passwd)
                        log.warning(f"Server map saved before killing: {res}")
                    except Exception as e:
                        if "semaphor" not in str(e):
                            log.warning(f"Server failed to save before killing: {e}")
                kill()
        else:
            if self.no_internet:
                log.warning("Internet is back up!")
            self.last_online = now
            self.no_internet = False


if __name__ == "__main__":
    try:
        asyncio.run(ArkHandler().initialize())
    except KeyboardInterrupt:
        pass
    except Exception:
        log.critical(f"Arkhandler failed to start!!!\n{traceback.format_exc()}")
    finally:
        log.info("Arkhandler shutting down...")
        set_resolution(default=True)
        log.info("You may now close this window")
