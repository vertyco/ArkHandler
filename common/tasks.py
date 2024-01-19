import asyncio
import logging
import os
import sys
from configparser import ConfigParser, NoOptionError, NoSectionError
from datetime import datetime, timedelta
from pathlib import Path
from subprocess import DEVNULL, call

import cv2
import win32evtlog
from aiohttp import ClientSession, ClientTimeout
from colorama import Fore, Style

from common.scheduler import scheduler
from common.utils import (
    Const,
    check_updates,
    get_ethernet_link_speed,
    get_rcon_info,
    init_sentry,
    is_running,
    is_updating,
    kill,
    maximize_window,
    on_screen,
    run_rcon,
    send_webhook,
    start_ark,
    sync_inis,
    update_ready,
    wipe_server,
)
from common.version import VERSION

log = logging.getLogger("ArkHandler.tasks")
parser = ConfigParser()


class ArkHandler:
    __version__ = VERSION

    def __init__(self) -> None:
        # Config
        self.configmtime = None
        self.debug = None
        self.hook = None
        self.game = None
        self.gameuser = None
        self.autowipe = None
        self.clustewipe = None
        self.wipetimes = None
        self.autoupdate = False

        # Pulled cache
        self.port = 0
        self.passwd = None

        # Data dir
        self.is_exe = True if (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")) else False
        if self.is_exe:
            self.mainpath = Path(os.path.dirname(os.path.abspath(sys.executable)))
        else:
            self.mainpath = Path(os.path.dirname(os.path.abspath(sys.executable))).parent.parent

        self.root = Path(os.path.abspath(os.path.dirname(__file__))).parent.resolve()  # arkhandler folder

        # Images
        self.assets = os.path.join(self.root, "assets")
        self.images = {
            "start": cv2.imread(os.path.join(self.assets, "start.PNG"), cv2.IMREAD_COLOR),
            "host": cv2.imread(os.path.join(self.assets, "host.PNG"), cv2.IMREAD_COLOR),
            "run": cv2.imread(os.path.join(self.assets, "run.PNG"), cv2.IMREAD_COLOR),
            "loaded": cv2.imread(os.path.join(self.assets, "loaded.PNG"), cv2.IMREAD_COLOR),
        }
        # Other assets
        self.default_config = Path(os.path.join(self.assets, "example_config.ini")).read_text()
        self.banner = Path(os.path.join(self.assets, "banner.txt")).read_text()

        # States
        self.checking_server = False  # Checking if server is running
        self.running = False  # Ark is running
        self.checking_updates = False  # Checking for updates
        self.updating = False  # Is updating
        self.installing = False  # Is installing
        self.booting = False  # Is booting up
        self.last_update = None  # Time of last event update
        self.checking_internet = False  # Internet check is running
        self.no_internet = False  # Whether script can ping google
        self.netdownkill = 0  # Time in minutes for internet to be down before killing server
        self.last_online = datetime.now()  # Timestamp of when server was last online
        self.current_action = (
            None  # Current action being performed by the app [None, "updating", "installing", "booting", ect...]
        )

    async def initialize(self) -> None:
        call(
            f'CheckNetIsolation LoopbackExempt -a -n="{Const.app}"',
            stdin=DEVNULL,
            stdout=DEVNULL,
            stderr=DEVNULL,
        )
        print(Fore.CYAN + Style.BRIGHT + self.banner)
        try:
            self.pull_config()
        except (NoOptionError, NoSectionError):
            log.warning("Config file invalid! Creating a new one")
            os.rename(self.mainpath / "config.ini", self.mainpath / "INVALID_config.ini")
            Path(self.mainpath / "config.ini").write_text(Const.default_config)

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

        now = datetime.now()
        if self.is_exe:
            log.debug(f"Running as EXE - {self.root}")
            try:
                init_sentry(
                    dsn="https://5d2f87a0ab981ec8d7640a2cc839adf7@sentry.vertyco.net/3",
                    version=self.__version__,
                )
            except Exception as e:
                log.error("Failed to initialize Sentry", exc_info=e)

        speeds = get_ethernet_link_speed()
        linkspeeds = "Link Speeds\n"
        for adapter, speed in speeds:
            linkspeeds += f"{adapter}: {speed} Mbps\n"
        if speeds:
            log.info(linkspeeds.strip())

        # Program bar animation
        asyncio.create_task(self.running_loop())
        asyncio.create_task(self.check_server_loop())
        scheduler.add_job(
            self.check_events,
            trigger="interval",
            seconds=15,
            next_run_time=now + timedelta(seconds=120),
            id="Handler.check_events",
            max_instances=1,
        )
        scheduler.add_job(
            self.check_updates,
            trigger="interval",
            seconds=600,
            next_run_time=now + timedelta(seconds=600),
            id="Handler.check_updates",
            max_instances=1,
        )
        scheduler.add_job(
            self.check_wipe,
            trigger="interval",
            seconds=15,
            next_run_time=now + timedelta(seconds=300),
            id="Handler.check_wipe",
            max_instances=1,
        )
        scheduler.add_job(
            self.check_internet,
            trigger="interval",
            seconds=300,
            next_run_time=now + timedelta(seconds=300),
            id="Handler.check_internet",
            max_instances=1,
        )

    def pull_config(self):
        conf = self.mainpath / "config.ini"
        if not conf.exists():
            log.warning("No config detected! Creating new one")
            conf.write_text(self.default_config)
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

        self.netdownkill = settings.getint("NetDownKill", fallback=0)
        self.hook = settings.get("WebhookURL", fallback="").replace('"', "")
        self.game = settings.get("GameiniPath", fallback="").replace('"', "")
        self.gameuser = settings.get("GameUserSettingsiniPath", fallback="").replace('"', "")
        self.autowipe = settings.getboolean("AutoWipe", fallback=False)
        self.clustewipe = settings.getboolean("AlsoWipeClusterData", fallback=False)
        self.autoupdate = settings.getboolean("AutoUpdate", fallback=True)

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
        await asyncio.sleep(2)
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
            if self.current_action:
                cmd += f" - {self.current_action}"
            os.system(cmd)
            index += 1
            index %= len(bar)
            await asyncio.sleep(0.15)

    async def check_server_loop(self):
        await asyncio.sleep(5)
        while True:
            try:
                await self._check()
            except Exception as e:
                log.error("Check server loop failed", exc_info=e)
            await asyncio.sleep(10)

    async def _check(self):
        if self.booting:
            log.debug("Booting in process, skipping server check...")
            return

        running = await asyncio.to_thread(is_running, tries=3, delay=1)
        if running:
            self.current_action = None
            if not self.running:
                log.info("Ark is running")
                self.running = True
            return

        # Don't act while updating or no internet
        skip_conditions = [self.installing, self.checking_updates, self.no_internet]
        if any(skip_conditions):
            log.debug("Skipping due to install, updates, or internet")
            return

        # If func makes it this far, then Ark is not running...
        if self.running:
            log.warning("Ark is no longer running, beginning reboot sequence in 10 seconds")
        else:
            log.warning("Attempting to boot ark in 10 seconds")

        await asyncio.sleep(9)

        self.running = False
        self.booting = True
        self.current_action = "booting"
        try:
            if not self.debug:
                await send_webhook(self.hook, "Server Down", "Beginning reboot sequence...", 16739584)
            self.current_action = "booting [syncing inis]"
            await asyncio.to_thread(sync_inis, self.game, self.gameuser)
            await asyncio.sleep(1)

            # Startup should not take more than 15 minutes
            self.current_action = "booting [launching ark]"
            success = await asyncio.to_thread(start_ark, self.images)
            if not success:
                log.warning("Ark didn't boot correctly! Killing process and trying again")
                self.booting = False
                if not self.debug:
                    await send_webhook(self.hook, "Boot Failed", "Trying again...", 19357)
                kill()
                await asyncio.sleep(3)
                self.booting = False
                return

            if not self.debug:
                await send_webhook(self.hook, "Booting", "Loading server files...", 19357)

            await asyncio.sleep(10)
            self.current_action = "booting [stopping license manager]"
            call("net stop LicenseManager", stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)

            # Wait up to 20 minutes for loading to finish
            log.info("Waiting for server to finish loading")
            self.current_action = "booting [waiting for server to load]"
            # Ensure ark is maximized and in the foreground
            maximize_window()

            loc = await asyncio.to_thread(on_screen, self.images["loaded"], 0.85, 1200)
            if not loc:
                log.warning("Server never finished loading! Killing process and trying again")
                self.booting = False
                if not self.debug:
                    await send_webhook(self.hook, "Loading Failed", "Trying again...", 19357)
                kill()
                await asyncio.sleep(3)
                self.booting = False
                return

            log.info("Reboot complete")
            if not self.debug:
                await send_webhook(self.hook, "Reboot Complete", "Server should be back online.", 65314)
            self.current_action = None
        except Exception as e:
            log.critical("Critical error in ArkHandler!", exc_info=e)
            if not self.debug:
                await send_webhook(
                    self.hook,
                    "CRITICAL ERROR",
                    f"```\n{e}\n```Sleeping for 10 minutes before trying again",
                    16711680,
                )
            await asyncio.sleep(600)
            self.booting = False
            self.running = False
            kill()
            return
        finally:
            self.booting = False

    async def check_events(self):
        if self.no_internet:
            return
        server = "localhost"
        logtype = "System"
        now = datetime.now()
        handle = win32evtlog.OpenEventLog(server, logtype)
        flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
        events = win32evtlog.ReadEventLog(handle, flags, 0)
        if not events:
            log.info("No events to pull")
            return

        if not self.current_action:
            self.current_action = "checking for updates"

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
            self.current_action = "updating"
        elif eid == 43 and not self.installing:
            log.warning(f"Install detected: {text}")
            await send_webhook(self.hook, "Installing", Const.install, 1127128, footer=f"File: {text}")
            self.installing = True
            self.current_action = "installing"
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
            log.warning("Restarting the loop")
            self.current_action = "update complete!"
        else:
            log.warning(f"No event for '{text}' with ID {eid}")

        self.last_update = created

    async def check_updates(self):
        skip_conditions = [
            self.checking_updates,
            self.no_internet,
            self.booting,
            self.updating,
        ]
        if any(skip_conditions):
            return
        log.debug("Checking for updates")
        self.checking_updates = True
        if not self.current_action:
            self.current_action = "checking for updates"
        try:
            kill("WinStore.App.exe")
            await asyncio.sleep(5)
            app = await asyncio.to_thread(check_updates)
            if not app:
                return
            ready = await asyncio.to_thread(update_ready, app, "ark")
            await asyncio.sleep(30)
            updating = await asyncio.to_thread(is_updating, app, "ark")
            if not any([ready, updating]):
                kill("WinStore.App.exe")
        except Exception as e:
            log.error("Update check failed!", exc_info=e)
        finally:
            self.checking_updates = False
            if self.current_action.endswith("updates"):
                self.current_action = None

    async def check_wipe(self):
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
            await send_webhook(self.hook, "WIPING SERVER", "Shutting down to wipe...", 16776960)
            kill()
            await asyncio.sleep(10)
            await asyncio.to_thread(wipe_server, self.clustewipe)
            await asyncio.sleep(65)
        finally:
            self.booting = False

    async def check_internet(self):
        if self.checking_internet:
            return
        try:
            self.checking_internet = True
            await self._check_internet()
        finally:
            self.checking_internet = False

    async def _check_internet(self):
        if self.netdownkill == 0:
            log.debug("Not checking internet since netdownkill is 0")
            return

        now = datetime.now()
        failed = False
        try:
            async with ClientSession(timeout=ClientTimeout(total=15)) as session:
                async with session.get("https://www.google.com") as res:
                    if res.status < 200 or res.status > 204:
                        failed = True
        except Exception:
            failed = True

        if failed:
            if not self.no_internet:
                log.warning("Internet is down!")
            self.no_internet = True
            td = round((now - self.last_online).total_seconds())
            if (td / 60) > self.netdownkill and is_running():
                log.error(f"Internet has been down for {td}s, shutting down ark!")
                if all([self.port, self.passwd, not self.booting, not self.updating]):
                    try:
                        res = await run_rcon("saveworld", self.port, self.passwd)
                        log.warning(f"Server map saved before killing: {res}")
                    except Exception as e:
                        if "semaphor" not in str(e):
                            log.error("Server failed to save before killing", exc_info=e)
                kill()
        else:
            if self.no_internet:
                log.warning("Internet is back up! Rebooting in 60 seconds")
            self.last_online = now
            await asyncio.sleep(60)
            self.no_internet = False
