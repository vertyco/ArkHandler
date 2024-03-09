import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from subprocess import DEVNULL, call
from time import sleep

import win32evtlog
from colorama import Fore, Style

from common import const, helpers, version
from common.config import Conf
from common.scheduler import scheduler

log = logging.getLogger("arkhandler.tasks")


class ArkHandler:
    """
    Task Loops:
    - Watchdog: Check for server crashes and restart
    - Update: Check for server updates and install
    - Events: Checks windows events for server updates taking place
    - Internet: Check for internet connection
    """

    __version__ = version.VERSION

    def __init__(self) -> None:
        self.conf: Conf = Conf.load(str(const.CONF_PATH))

        # Main states
        self.current_action = ""  # Used for window title
        self.running = False  # Server is running
        self.checking_server = False  # Checking if server is running
        self.booting = False  # Server is booting up
        self.checking_updates = False  # Checking for updates

        # Update states
        self.last_event: None | tuple[int, datetime] = None  # Last event pulled from event log
        self.downloading = False  # Downloading update
        self.installing = False  # Installing update

        # Internet states
        self.last_connected = datetime.now()  # Last time internet was connected
        self.connected = True  # Whether the computer is connected to the internet

    async def initialize(self):
        log.info("Initializing...")
        # Print banner and info
        print(Fore.CYAN + Style.BRIGHT + const.BANNER_TEXT + Style.RESET_ALL)
        info = (
            f"Python version: {sys.version}\n"
            f"ArkHandler version: {self.__version__}\n"
            f"Root: {const.ROOT_PATH}\n"
            f"Meta: {const.META_PATH}\n"
            f"Config: {const.CONF_PATH}\n"
            f"Debug: {self.conf.debug}\n"
            f"Auto Update: {self.conf.auto_update}\n"
        )
        if self.conf.webhook_url:
            info += f"Webhook: {self.conf.webhook_url}\n"
        if self.conf.game_ini:
            info += f"Game.ini: {self.conf.game_ini}\n"
        if self.conf.gameusersettings_ini:
            info += f"GameUserSettings.ini: {self.conf.gameusersettings_ini}\n"
        if self.conf.debug:
            log.setLevel(logging.DEBUG)
            info += "Debug mode enabled.\n"
            speeds = helpers.get_ethernet_link_speed()
            for adapter, speed in speeds:
                info += f"{adapter}: {speed} Mbps\n"
        print(Fore.CYAN + info.strip())

        # Initialize Sentry
        helpers.init_sentry(self.conf.sentry_dsn, self.__version__)

        # Check resolution
        helpers.check_resolution()

        # Window bar animation
        if const.IS_EXE:
            asyncio.create_task(self.window_title())

        scheduler.add_job(
            func=self.watchdog,
            trigger="interval",
            seconds=30,
            id="watchdog",
            name="Watchdog",
            replace_existing=True,
            max_instances=1,
            next_run_time=datetime.now() + timedelta(seconds=5),
        )
        scheduler.add_job(
            func=self.check_internet,
            trigger="interval",
            seconds=10,
            id="internet_checker",
            name="Internet Checker",
            replace_existing=True,
            max_instances=1,
            next_run_time=datetime.now() + timedelta(seconds=10),
        )
        if self.conf.auto_update:
            scheduler.add_job(
                func=self.check_events,
                trigger="interval",
                seconds=15,
                id="event_watcher",
                name="Event Watcher",
                replace_existing=True,
                max_instances=1,
                next_run_time=datetime.now() + timedelta(seconds=800),
            )
            scheduler.add_job(
                func=self.check_updates,
                trigger="interval",
                seconds=300,
                id="update_checker",
                name="Update Checker",
                replace_existing=True,
                max_instances=1,
                next_run_time=datetime.now() + timedelta(seconds=600),
            )

    async def window_title(self):
        def _run():
            index = 0
            while True:
                cmd = f"title ArkHandler {self.__version__} {const.BAR[index]}"
                if self.current_action:
                    cmd += f" {self.current_action}"
                os.system(cmd)
                index = (index + 1) % len(const.BAR)
                sleep(0.15)

        await asyncio.to_thread(_run)

    async def watchdog(self):
        skip = [
            self.checking_server,
            self.booting,
            self.checking_updates,
            self.installing,
        ]
        if any(skip):
            log.debug(f"Skipping watchdog: {skip}")
            return
        try:
            self.checking_server = True
            await self._check_server()
        except Exception as e:
            log.error("Watchdog failed", exc_info=e)
        finally:
            self.booting = False
            self.checking_server = False

    async def _check_server(self):
        """Check for server crashes and restart"""
        running = await asyncio.to_thread(helpers.is_running)
        loaded = await asyncio.to_thread(helpers.check_for_state, "loaded")
        if running and loaded:
            # Server is running and loaded
            if not self.running:
                log.info("Server is up and running.")
                self.running = True
            return

        # Server is either not running or running but not loaded
        if self.running:
            log.warning("Game is running but server isnt loaded, rebooting in 5 seconds...")
        else:
            log.warning("Server is not running, rebooting in 5 seconds...")
        await asyncio.sleep(5)

        # If we're here, the server needs to be rebooted
        self.running = False
        self.booting = True
        self.current_action = "booting"
        if self.conf.game_ini or self.conf.gameusersettings_ini:
            self.current_action += " [syncing inis]"

        await helpers.send_webhook(
            url=self.conf.webhook_url,
            title="Server Down",
            message="Beginning reboot sequence...",
            color=16739584,
        )
        if self.conf.game_ini:
            log.info(f"Syncing {self.conf.game_ini}...")
            helpers.sync_file(self.conf.game_ini_path)
        if self.conf.gameusersettings_ini:
            log.info(f"Syncing {self.conf.gameusersettings_ini}...")
            helpers.sync_file(self.conf.gameusersettings_ini_path)

        self.current_action = "booting [starting server]"
        try:
            running = await asyncio.to_thread(helpers.start_server)
        except Exception as e:
            log.error("Failed to start server, trying again in 1 minute", exc_info=e)
            running = False

        if not running:
            await helpers.send_webhook(
                url=self.conf.webhook_url,
                title="Boot Failed",
                message="Failed to start server, trying again in 1 minute",
                color=19357,
            )
            self.current_action = "boot failed [sleeping before retry]"
            await asyncio.sleep(60)
            self.booting = False
            return

        await helpers.send_webhook(
            url=self.conf.webhook_url,
            title="Booting",
            message="Loading server files...",
            color=19357,
        )
        await asyncio.sleep(10)
        self.current_action = "booting [stopping license manager]"
        call("net stop LicenseManager", stdin=DEVNULL, stdout=DEVNULL, stderr=DEVNULL)

        # Wait up to 15 minutes for loading to finish
        log.info("Waiting for server to finish loading")
        loaded = await asyncio.to_thread(helpers.wait_for_state, "loaded", 900)
        if not loaded:
            log.error("Server never finished loading, waiting 5 minutes before trying again")
            await helpers.send_webhook(
                url=self.conf.webhook_url,
                title="Boot Failed",
                message="Server never finished loading, waiting 5 minutes before trying again",
                color=19357,
            )
            self.current_action = "boot failed [sleeping before retry]"
            await asyncio.sleep(300)
            self.booting = False
            return

        log.info("Boot sequence complete.")
        await helpers.send_webhook(
            url=self.conf.webhook_url,
            title="Reboot Complete",
            message="Server should be back online.",
            color=65314,
        )
        self.current_action = ""
        self.booting = False

    async def check_internet(self):
        connected = await helpers.internet_connected()
        if not connected:
            if self.connected:
                log.warning("Internet disconnected!")
                self.connected = False
            # Internet is down, nothing to do
            return

        # Internet is up, see if it's been down for a while
        if not self.connected:
            td = (datetime.now() - self.last_connected).total_seconds()
            if td > 180:
                log.warning("Internet was down for over 3 minutes, rebooting...")
                outage = f"<t:{int(self.last_connected.timestamp())}:R> to <t:{int(datetime.now().timestamp())}:R>"
                txt = f"Server experienced an internet outage from {outage}. Rebooting..."
                await helpers.send_webhook(
                    url=self.conf.webhook_url,
                    title="Internet Reboot",
                    message=txt,
                    color=16711753,
                )
                # Kill the server to trigger the watchdog
                helpers.kill()
            else:
                log.warning(f"Internet was down for {round(td)} seconds but is back up!")

        self.connected = True
        self.last_connected = datetime.now()

    async def check_events(self):
        """Check events and update states accordingly"""

        def _check():
            server = "localhost"
            logtype = "System"
            handle = win32evtlog.OpenEventLog(server, logtype)
            flags = win32evtlog.EVENTLOG_SEQUENTIAL_READ | win32evtlog.EVENTLOG_BACKWARDS_READ
            events = win32evtlog.ReadEventLog(handle, flags, 0)
            return events

        events = await asyncio.to_thread(_check)
        if not events:
            log.info("No events to pull")
            return

        now = datetime.now()

        if not self.current_action:
            self.current_action = "checking events"

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
        eid = event.EventID
        if self.last_event is None:
            self.last_event = (eid, created)
            return

        if eid == self.last_event[0]:
            return

        td = (now - created).total_seconds()
        if td > 3600:
            log.info(f"Found event {eid} but it's too old ({td} seconds)")
            self.last_event = (eid, created)
            return

        # A new event has been found
        self.last_event = (eid, created)
        if eid == 44:
            log.warning(f"Download started: {text}")
            self.downloading = True
            self.installing = False
            self.current_action = "downloading update"
            await helpers.send_webhook(
                url=self.conf.webhook_url,
                title="Download Detected!",
                message=const.DOWNLOAD,
                color=14177041,
                footer=f"File: {text}",
            )
        elif eid == 43:
            log.warning(f"Install started: {text}")
            self.downloading = False
            self.installing = True
            self.current_action = "installing update"
            await helpers.send_webhook(
                url=self.conf.webhook_url,
                title="Installing!",
                message=const.INSTALL,
                color=1127128,
                footer=f"File: {text}",
            )
        elif eid == 19:
            log.warning(f"Install finished: {text}")
            self.downloading = False
            self.installing = False
            self.current_action = "update complete!"
            await helpers.send_webhook(
                url=self.conf.webhook_url,
                title="Update Complete!",
                message=const.INSTALL,
                color=65314,
                footer=f"File: {text}",
            )
        else:
            log.error(f"Unknown event {eid}: {text}")
            if self.current_action == "checking events":
                self.current_action = ""
            return

    async def check_updates(self):
        skip = [
            self.booting,
            self.checking_updates,
            self.downloading,
            self.installing,
            not self.conf.auto_update,
        ]
        if any(skip):
            return
        self.checking_updates = True
        if not self.current_action:
            self.current_action = "checking for updates"

        try:
            await asyncio.to_thread(helpers.check_ms_store)
        except Exception as e:
            log.error("Failed to check MS Store for updates", exc_info=e)
            helpers.kill("WinStore.App.exe")
            return
        finally:
            self.checking_updates = False
            if self.current_action == "checking for updates":
                self.current_action = ""
