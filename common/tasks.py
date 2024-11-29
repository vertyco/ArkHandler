import asyncio
import logging
import os
import sys
from datetime import datetime, timedelta
from itertools import cycle
from subprocess import DEVNULL, call
from time import sleep

from colorama import Fore, Style

from common import const, helpers, logger, version
from common.config import Conf
from common.scheduler import scheduler

log = logging.getLogger("arkhandler.tasks")


class ArkHandler:
    """
    Task Loops:
    - Watchdog: Check for server crashes and restart
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
        logger.init_sentry(self.conf.sentry_dsn, self.__version__)

        # Check resolution
        helpers.check_resolution()

        # Window bar animation
        if const.IS_EXE:
            asyncio.create_task(self.window_title())

        scheduler.add_job(
            func=self.watchdog,
            trigger="interval",
            seconds=7,
            id="watchdog",
            name="Watchdog",
            replace_existing=True,
            max_instances=1,
            next_run_time=datetime.now() + timedelta(seconds=5),
        )
        scheduler.add_job(
            func=self.check_internet,
            trigger="interval",
            seconds=60,
            id="internet_checker",
            name="Internet Checker",
            replace_existing=True,
            max_instances=1,
            next_run_time=datetime.now() + timedelta(seconds=60),
        )

    async def window_title(self):
        def _run():
            bar_cycle = cycle(const.BAR)
            while True:
                cmd = f"title ArkHandler {self.__version__} {next(bar_cycle)}"
                if self.current_action:
                    cmd += f" {self.current_action}"
                os.system(cmd)
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
        if running:
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

        self.current_action = "killing MS Store"
        helpers.kill("WinStore.App.exe")

        self.current_action = "booting [starting server]"
        os.system(const.BOOT_COMMAND)
        running = await asyncio.to_thread(helpers.wait_till_running)
        if not running:
            log.warning("Failed to start server, trying again in 1 minute")
            await helpers.send_webhook(
                url=self.conf.webhook_url,
                title="Boot Failed",
                message="Failed to start server, trying again in 1 minute",
                color=19357,
            )
            self.current_action = "boot failed [sleeping before retry]"
            await asyncio.sleep(60)
            helpers.kill()
            self.booting = False
            return

        # Set the permissions on the DLL
        perms = await asyncio.to_thread(helpers.apply_permissions_to_dll, const.DLL_PATH)
        log.info("Set permissions on startup dll: %s", perms)

        # Get the PID of ShooterGame.exe
        pid = await asyncio.to_thread(helpers.get_pid)
        log.info("Ark is running with PID %s, injecting startup dll...", pid)

        # Inject the DLL
        injected = await asyncio.to_thread(helpers.inject_dll, pid, const.DLL_PATH)
        log.info("Injected dll: %s", injected)

        # Wait 3 seconds then check if process is still running
        await asyncio.sleep(3)
        running = await asyncio.to_thread(helpers.is_running)
        if not running:
            log.error("Ark is not running after injection, killing and retrying")
            helpers.kill()
            self.current_action = "dll injection failed [sleeping before retry]"
            await asyncio.sleep(5)
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
        await asyncio.sleep(10)
        # Wait up to 15 minutes for loading to finish
        log.info("Waiting for server to finish loading")
        loaded = await asyncio.to_thread(helpers.wait_for_state, "loaded", 900)
        if not loaded:
            log.warning("Server never finished loading, waiting 5 minutes before trying again")
            await helpers.send_webhook(
                url=self.conf.webhook_url,
                title="Boot Failed",
                message="Server never finished loading, waiting 5 minutes before trying again",
                color=19357,
            )
            self.current_action = "boot failed [sleeping before retry]"
            await asyncio.sleep(300)
            self.booting = False
            helpers.kill()
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
