import asyncio
import contextlib
import json
import logging
import os
import sys
from contextlib import suppress
from datetime import datetime
from pathlib import Path
from time import sleep

import aiohttp
import cv2
import numpy as np
import psutil
import pyautogui
import pyscreeze
import pywinauto
import pywintypes
import sentry_sdk
import win32api
import win32con
import win32gui
import wmi
from comtypes import COMError
from pywinauto import Application, ElementAmbiguousError, ElementNotFoundError
from pywinauto.timings import TimeoutError
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

try:
    from common import const
except ModuleNotFoundError:
    import const

log = logging.getLogger("arkhandler.utils")


pyscreeze.USE_IMAGE_NOT_FOUND_EXCEPTION = False


def init_sentry(dsn: str, version: str) -> None:
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            AioHttpIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        release=version,
        environment=sys.platform,
        ignore_errors=[KeyboardInterrupt],
    )


def sync_file(source: Path) -> bool:
    dest = const.INI_PATH / source.name
    if not source.exists():
        log.error(f"ini file not found: {source}")
        return False
    try:
        dest.write_text(source.read_text())
        log.info(f"Synced {source.name} to UWPConfig")
        return True
    except Exception as e:
        log.error(f"Failed to sync {source.name} to UWPConfig", exc_info=e)
        return False


async def send_webhook(url: str, title: str, message: str, color: int, footer: str | None = None):
    if not url:
        return
    log.debug(f"Sending webhook: {title}")
    em = {"title": title, "description": message, "color": color}
    if footer:
        em["footer"] = {"text": footer}
    data = {
        "username": "ArkHandler",
        "avatar_url": "https://i.imgur.com/Wv5SsBo.png",
        "embeds": [em],
    }
    headers = {"Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=20)
            async with session.post(url=url, data=json.dumps(data), headers=headers, timeout=timeout) as res:
                if res.status != 204:
                    log.warning(f"Failed to send {title} webhook. status {res.status}")
                else:
                    log.debug(f"{title} webhook sent successfully")
    except Exception as e:
        log.error(f"Failed to send {title} webhook", exc_info=e)


async def internet_connected() -> bool:
    async def _check(session: aiohttp.ClientSession, url: str) -> bool:
        try:
            async with session.get(url, timeout=5) as response:
                return response.status == 200
        except Exception:
            return False

    urls = ["http://1.1.1.1", "http://8.8.8.8"]
    async with aiohttp.ClientSession() as session:
        tasks = [asyncio.ensure_future(_check(session, url)) for url in urls]
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)

        for task in done:
            return task.result()
        return False


def get_ethernet_link_speed() -> list[tuple[str, float]]:
    connection = wmi.WMI()
    speeds = []
    for adapter in connection.Win32_NetworkAdapter():
        if not adapter.NetConnectionID:
            continue
        if "Ethernet" not in adapter.NetConnectionID:
            continue
        speed = adapter.Speed
        if not speed:
            continue
        speed_mbps = round(int(speed) / (1024**2), 1)
        speeds.append([adapter.NetConnectionID, speed_mbps])
        log.debug(f"{adapter.NetConnectionID}'s speed: {speed_mbps} Mbps")
    return speeds


def get_images() -> dict[str, np.ndarray]:
    size = pyautogui.size()
    res_path = const.IMAGE_PATH / f"{size[0]}x{size[1]}"
    if not res_path.exists():
        raise FileNotFoundError(f"Resolution folder not found: {res_path}")
    images = {
        "start": cv2.imread(str(res_path / "start.PNG")),
        "host": cv2.imread(str(res_path / "host.PNG")),
        "run": cv2.imread(str(res_path / "run.PNG")),
        "accept1": cv2.imread(str(res_path / "accept1.PNG")),
        "accept2": cv2.imread(str(res_path / "accept2.PNG")),
        "loaded": cv2.imread(str(res_path / "loaded.PNG")),
    }
    return images


def get_game_state(confidence: float = 0.85, minSearchTime: float = 0.0) -> str | None:
    """
    Return the current state of the game
    - start: the game is at the pre-menu screen
    - host: the game is at the main menu
    - run: ready to click the run button
    - accept1: ready to click the first accept button
    - accept2: ready to click the second accept button
    - loaded: the game is running
    - None: unknown state, or the game is not running
    """
    maximize_window()
    images = get_images()
    for state, image in images.items():
        with suppress(pyscreeze.ImageNotFoundException, pyautogui.ImageNotFoundException):
            loc = pyautogui.locateOnScreen(image, confidence=confidence, minSearchTime=minSearchTime, grayscale=True)
            if loc:
                return state
    return None


def check_for_state(state: str, confidence: float = 0.85, minSearchTime: float = 0.0) -> bool:
    maximize_window()
    images = get_images()
    image = images[state]
    loc = pyautogui.locateOnScreen(image, confidence=confidence, minSearchTime=minSearchTime, grayscale=True)
    return True if loc else False


def wait_for_state(state: str, timeout: int) -> bool:
    start = datetime.now()
    while (datetime.now() - start).total_seconds() < timeout:
        if not is_running():
            log.warning("Cant wait for state if the server is not running")
            return False
        close_teamviewer()
        maximize_window()
        if check_for_state(state):
            return True
        sleep(1)
    return False


def close_teamviewer():
    try:
        handle = win32gui.FindWindow(None, "Sponsored session")
        if not handle:
            return
        log.info("Closing TeamViewer...")
        win32gui.PostMessage(handle, win32con.WM_CLOSE, 0, 0)
    except Exception as e:
        log.error("Failed to close TeamViewer window", exc_info=e)


def kill(process: str = "ShooterGame.exe") -> bool:
    with suppress(Exception):
        for proc in psutil.process_iter():
            if proc.name() == process:
                proc.kill()
                return True
    return False


def is_running(process: str = "ShooterGame.exe") -> bool:
    for _ in range(3):
        try:
            for proc in psutil.process_iter():
                if proc.name() == process:
                    return True
        except psutil.NoSuchProcess:
            pass
        sleep(0.1)
    return False


def get_positions() -> dict[str, tuple[float, float, float, float]]:
    return json.loads(const.POSITIONS_PATH.read_text())


def maximize_window(app_name: str = "ARK: Survival Evolved") -> None:
    """Maximize the window of the given app name and bring it to the front."""
    log.debug(f"Maximizing {app_name} window...")
    handle = win32gui.FindWindow(None, app_name)
    if not handle:
        return
    win32gui.ShowWindow(handle, win32con.SW_MAXIMIZE)
    bring_to_front()


def bring_to_front(app_name: str = "ARK: Survival Evolved") -> None:
    window = pywinauto.findwindows.find_window(title=app_name)
    if window:
        log.debug(f"Setting focus to {app_name} window: {window}")
        app = Application().connect(handle=window)
        app.top_window().set_focus()


def set_resolution(width: int = 1280, height: int = 720, default: bool = False):
    """Set the screen resolution"""
    if default:
        log.info("Setting resolution back to default")
        win32api.ChangeDisplaySettings(None, 0)
        return
    can_skip = [
        abs(pyautogui.size().width - width) < 10,
        abs(pyautogui.size().height - height) < 10,
    ]
    if all(can_skip):
        log.info("Resolution okay, no need to adjust")
        return
    log.warning(f"Adjusting resolution to {width} by {height}")
    dev = pywintypes.DEVMODEType()
    dev.PelsWidth = width
    dev.PelsHeight = height
    dev.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
    win32api.ChangeDisplaySettings(dev, 0)


def check_resolution():
    # Ensure current resolution is supported
    current = (pyautogui.size().width, pyautogui.size().height)
    if current not in const.SUPPORTED_RESOLUTIONS:
        # Resolution isnt supported so change to the closest one
        closest = min(const.SUPPORTED_RESOLUTIONS, key=lambda x: abs(x[0] - current[0]) + abs(x[1] - current[1]))
        log.warning(f"Current resolution {current} not supported, changing to closest supported resolution {closest}")
        set_resolution(*closest)
    else:
        log.info(f"Current resolution {current} is supported")


def check_ms_store() -> Application | None:
    """Check MS store for updates"""
    # First kill the app if it's running
    kill("WinStore.App.exe")
    sleep(5)
    # Launch the MS store
    os.system(const.MS_BOOT_COMMAND)
    sleep(8)
    if not is_running("WinStore.App.exe"):
        return
    maximize_window("Microsoft Store")
    try:
        app = Application(backend="uia").connect(title="Microsoft Store")
    except (ElementNotFoundError, COMError):
        kill("WinStore.App.exe")
        return

    dlg = app.top_window()

    with contextlib.suppress(ElementAmbiguousError, ElementNotFoundError):
        library_button = dlg.window(auto_id="MyLibraryButton")
        with contextlib.suppress(TimeoutError):
            library_button.wait("ready", timeout=30)
        library_button.click_input()

    try:
        update_button = dlg.window(auto_id="CheckForUpdatesButton")
        with contextlib.suppress(TimeoutError):
            update_button.wait("ready", timeout=30)
        update_button.click()
    except (ElementAmbiguousError, ElementNotFoundError):
        kill("WinStore.App.exe")
        return

    return app


def start_server() -> bool:
    log.info("Starting the server...")
    # If the app is already running we want to kill it
    if kill():
        sleep(5)
    # Launch Ark
    os.system(const.BOOT_COMMAND)
    sleep(5)
    if not is_running():
        log.error("Failed to launch the Ark: Survival Evolved!")
        return False
    images = get_images()
    buttons = {
        "start": 300,
        "host": 300,
        "run": 120,
        "accept1": 15,
        "accept2": 15,
    }
    for button_name, min_search_time in buttons.items():
        if not is_running():
            log.error(f"Server may have crashed while waiting for {button_name} button")
            return False
        image = images[button_name]
        log.info(f"Waiting for {button_name} button to appear...")
        # Close teamviewer popup if it's open
        close_teamviewer()
        # Ensure the window is maximized
        maximize_window()
        found = wait_for_state(button_name, min_search_time)
        if not found:
            log.warning(f"Could not find {button_name} button")
            return False
        loc = pyautogui.locateOnScreen(image, confidence=0.85, minSearchTime=1, grayscale=True)
        if not loc:
            log.error(f"Failed to locate {button_name} button")
            return False
        coords = pyautogui.center(loc)
        log.info(f"Clicking {button_name} button...")
        if button_name == "start":
            pyautogui.doubleClick(coords[0], coords[1])
        else:
            pyautogui.click(coords[0], coords[1])
    return is_running()


if __name__ == "__main__":
    start_server()
