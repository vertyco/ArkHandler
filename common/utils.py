import contextlib
import ctypes
import json
import logging
import os
from configparser import ConfigParser
from pathlib import Path
from time import sleep

import aiohttp
import psutil
import pyautogui
import pyscreeze
import pywintypes
import sentry_sdk
import win32api
import win32con
import win32gui
import wmi
from pywinauto.application import Application
from pywinauto.findwindows import ElementAmbiguousError, ElementNotFoundError
from pywinauto.timings import TimeoutError
from rcon.source import rcon
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.logging import LoggingIntegration

log = logging.getLogger("ArkHandler.utils")

ctypes.windll.user32.BringWindowToTop.argtypes = [ctypes.wintypes.HWND]
ctypes.windll.user32.BringWindowToTop.restype = ctypes.wintypes.BOOL
ctypes.windll.user32.ShowWindow.argtypes = [ctypes.wintypes.HWND, ctypes.c_int]
ctypes.windll.user32.ShowWindow.restype = ctypes.wintypes.BOOL
pyscreeze.USE_IMAGE_NOT_FOUND_EXCEPTION = False


class Const:
    download = "**The server has started downloading an update, and will go down once it starts installing.**"
    install = "**The server has started installing the update. Stand by...**"
    complete = "**The server has finished installing the update.**"
    # Coords
    positions = {
        "start": (0.5, 0.875),
        "host": (0.12, 0.545),
        "run": (0.494, 0.7675),
        "accept1": (0.418, 0.551),
        "accept2": (0.568, 0.6905),
    }
    # Ark paths
    app = "StudioWildcard.4558480580BB9_1w2mm55455e38"
    save_path = rf"{os.environ['LOCALAPPDATA']}\Packages\{app}\LocalState\Saved"
    cluster_path = rf"{save_path}\clusters\solecluster"
    boot = rf"explorer.exe shell:appsFolder\{app}!AppARKSurvivalEvolved"
    config = rf"{save_path}\UWPConfig\UWP"


class ExitApplication(Exception):
    pass


def init_sentry(dsn: str, version: str) -> None:
    """Initializes Sentry SDK.

    Parameters
    ----------
    dsn: str
        The Sentry DSN to use.
    version: str
        The version of the application.
    """
    sentry_sdk.init(
        dsn=dsn,
        integrations=[
            AioHttpIntegration(),
            LoggingIntegration(
                level=logging.INFO,
                event_level=logging.ERROR,
            ),
        ],
        release=version,
        environment="windows",
        ignore_errors=[KeyboardInterrupt],
    )


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


def get_windows(name: str, exclude: bool = False):
    """Get all windows associated with the provided string

    If exclude is True, it will return all windows that do not match the string
    """

    def callback(hwnd, opened):
        # Handle, Title, Placement, Position(left, top, right bottom)
        opened.append(
            (
                hwnd,
                win32gui.GetWindowText(hwnd),
                win32gui.GetWindowPlacement(hwnd),
                win32gui.GetWindowRect(hwnd),
            )
        )

    windows = []
    win32gui.EnumWindows(callback, windows)
    if exclude:
        windows = [i for i in windows if name.lower() not in i[1].lower()]
    else:
        windows = [i for i in windows if name.lower() in i[1].lower()]
    return windows


def on_screen(image, confidence: float = 0.85, search_time: int = 5):
    try:
        return pyautogui.locateOnScreen(image, confidence=confidence, minSearchTime=search_time)
    except OSError:
        return False
    except Exception as e:
        log.info(f"Failed to locate {image}", exc_info=e)
        return False


def click_button(button: str, images: dict) -> bool:
    """Click an ark button, returns True if successful"""
    # Bring ark to the front
    maximize_window()
    if not is_running():
        log.warning(f"Ark crashed, cancelling {button} button click")
        return False

    log.info(f"Clicking {button} button")
    if button in images:
        # We will wait up to 5 minutes for the image to appear
        loc = on_screen(images[button], search_time=300)
        if not loc:
            log.warning(f"Failed to locate {button} button")
            return False

    sleep(1.5)

    if not is_running():
        log.warning(f"Ark crashed, cancelling {button} button click")
        return False

    # Ark will always be 16:9 aspect ratio
    xr, yr = Const.positions[button]
    ark_windows = get_windows("ark: survival evolved")
    if not ark_windows:
        raise Exception("Ark is not running!")

    left, top, right, bottom = ark_windows[0][3]

    # Make sure aspect ratio is okay
    w, h = right - left, bottom - top
    wr, hr = (w / 16), (h / 9)
    y_offset = 15
    if wr > hr and (wr - hr) > 1:  # Too wide
        diff = (w - ((h / 9) * 16)) / 2
        left = left + diff
        right = right - diff
        y_offset += int(diff * 0.01)
    elif wr < hr and (hr - wr) > 1:  # Too tall
        diff = (h - ((w / 16) * 9)) / 2
        top = top + diff
        bottom = bottom - diff
        y_offset += int(diff * 0.01)
    # Get x and y for click
    x, y = int((right - left) * xr + left), int((bottom - top) * yr + top + y_offset)
    maximize_window()
    if button == "start":
        click(x, y, True)
    else:
        click(x, y)
    return True


def click(x: int, y: int, double: bool = False):
    """Click a position on the screen"""
    # pyautogui.moveTo(x, y, 1, pyautogui.easeOutQuad)
    if double:
        pyautogui.doubleClick(x, y)
    else:
        pyautogui.click(x, y)


def set_resolution(width: int = 1280, height: int = 720, default: bool = False):
    """Set the screen resolution"""
    if default:
        log.debug("Setting resolution back to default")
        win32api.ChangeDisplaySettings(None, 0)
        return
    can_skip = [
        abs(pyautogui.size().width - width) < 10,
        abs(pyautogui.size().height - height) < 10,
    ]
    if all(can_skip):
        log.debug("Resolution okay, no need to adjust")
        return
    log.warning(f"Adjusting resolution to {width} by {height}")
    dev = pywintypes.DEVMODEType()
    dev.PelsWidth = width
    dev.PelsHeight = height
    dev.Fields = win32con.DM_PELSWIDTH | win32con.DM_PELSHEIGHT
    win32api.ChangeDisplaySettings(dev, 0)


async def send_webhook(url: str, title: str, message: str, color: int, footer: str = None):
    """Send a discord webhook"""
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


def kill(process: str = "ShooterGame.exe") -> bool:
    """Kill a process"""
    try:
        for p in psutil.process_iter():
            if p.name() != process:
                continue
            try:
                p.kill()
                return True
            except Exception as e:
                log.error(f"Exception while killing {process}", exc_info=e)
        return False
    except psutil.NoSuchProcess:
        return False


def is_running(process: str = "ShooterGame.exe", tries: int = 1, delay: int = 0):
    """Check if a process is running"""
    # Must be true all 3 times
    running = []
    for __ in range(tries):
        try:
            processes = [p.name() for p in psutil.process_iter()]
            running.append(process in processes)
        except psutil.NoSuchProcess:
            running.append(False)
        if delay:
            sleep(delay)
    return any(running)


def update_ready(prog: Application, name: str):
    """Check if an app has an update (MS Store must be open)"""
    try:
        window = prog.top_window()
    except RuntimeError:
        return False
    for i in window.descendants(control_type="Button"):
        if name.lower() in str(i).lower() and "update available" in str(i).lower():
            return True
    else:
        return False


def is_updating(prog: Application, name: str):
    """Check if an app is updating (MS Store must be open)"""
    try:
        window = prog.top_window()
    except RuntimeError:
        return False
    for i in window.descendants(control_type="Button"):
        conditions = [
            name.lower() in str(i).lower(),
            "download" in str(i).lower(),
            "installing" in str(i).lower(),
            "pending" in str(i).lower(),
        ]
        if any(conditions):
            return True
    else:
        return False


def check_updates():
    """Check MS store for updates"""
    try:
        if not is_running("WinStore.App.exe"):
            os.system(r"explorer.exe shell:appsFolder\Microsoft.WindowsStore_8wekyb3d8bbwe!App")
        app = Application(backend="uia")
        tries = 0
        while True:
            tries += 1
            if tries >= 10:
                log.error("Cannot find Microsoft Store app")
                return None
            try:
                app = app.connect(title="Microsoft Store")
                break
            except ElementNotFoundError:
                sleep(1)
                continue
            except Exception as e:
                log.error("Failed to get Microsoft Store app", exc_info=e)
                sleep(1)
                continue

        windows = get_windows("Microsoft Store")
        if len(windows) > 1 and windows[0][2][1] == 1:
            for i in windows:
                try:
                    win32gui.ShowWindow(i[0], win32con.SW_RESTORE)
                except Exception as e:
                    log.error("Failed to restore microsoft store window", exc_info=e)

        dlg = app.top_window()
        # Library button
        with contextlib.suppress(ElementAmbiguousError, ElementNotFoundError):
            library_button = dlg.window(auto_id="MyLibraryButton")
            with contextlib.suppress(TimeoutError):
                library_button.wait("ready", timeout=30)
            library_button.click_input()

        # Update button
        error = False
        try:
            update_button = dlg.window(auto_id="CheckForUpdatesButton")
            with contextlib.suppress(TimeoutError):
                update_button.wait("ready", timeout=60)
            update_button.click()
        except (ElementAmbiguousError, ElementNotFoundError):
            error = True

        # Minimize or close the window
        if error:
            kill("WinStore.App.exe")
            return
        for i in windows:
            win32gui.ShowWindow(i[0], win32con.SW_MINIMIZE)
        return app
    except Exception as e:
        log.error("Failed to check for updates!", exc_info=e)


def sync_file(origin: str, filename: str):
    source = Path(origin)
    if not source.exists():
        log.warning(f"{filename} source doesn't exist: {source}")
        return

    if source.is_dir():
        source = Path(os.path.join(source, filename))
    if not source.exists():
        log.warning(f"{filename} source file not found: {source}")
        return
    target = os.path.join(Const.config, filename)
    try:
        with open(rf"{source}", "rb") as src:
            with open(rf"{target}", "wb") as tgt:
                tgt.write(src.read())
        log.info(f"{source.name} synced from {source}")
    except Exception as e:
        log.error(f"Failed to sync {filename} file", exc_info=e)


def sync_inis(game: str, gameuser: str):
    """Update ark UWP config files"""
    log.info("Syncing ini files")
    if not Path(Const.config).exists():
        log.warning("Cannot find UWP path, config not synced!")
        return

    # Sync Game.ini
    if game:
        sync_file(game, "Game.ini")
    # Sync GameUserSettings.ini
    if gameuser:
        sync_file(gameuser, "GameUserSettings.ini")


def close_teamviewer():
    windows = get_windows("sponsored session")
    if not windows:
        return
    log.info("Closing teamviewer window")
    for i in windows:
        win32gui.SetForegroundWindow(i[0])
        win32gui.PostMessage(i[0], win32con.WM_CLOSE, 0, 0)


def launch_program() -> None:
    tries = 0
    while True:
        tries += 1
        if not is_running():
            os.system(Const.boot)

        sleep(15)

        if is_running():
            break

        if tries >= 10:
            raise WindowsError("Ark failed to launch 10 times and may be corrupt")

    log.info(f"Ark launched in {tries} tries")


def maximize_window():
    """Mazimize ark and minimize other windows"""
    # First check if any windows that arent ark are in the foreground
    # If there are any windows that are on top of ark, minimize them
    windows = get_windows("ark: survival evolved", exclude=True)
    if windows:
        for window in windows:
            hwnd = window[0]
            # If this window is in the foreground or on top of ark, minimize it
            if win32gui.GetForegroundWindow() == hwnd or win32gui.GetWindow(hwnd, win32con.GW_HWNDPREV) == hwnd:
                log.debug(f"Minimizing window: {window[1]}")
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)

    # Then maximize ark
    log.debug("Maximizng window")
    windows = get_windows("ark: survival evolved")
    if not windows:
        raise WindowsError("Failed to fetch windows for Ark")

    # Iterate through all the ARK application windows
    for window in windows:
        hwnd = window[0]  # Get handle to window
        win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)


def start_ark(images: dict) -> bool:
    """Click through menu buttons to start server"""
    close_teamviewer()
    kill("WinStore.App.exe")
    set_resolution()
    if not is_running(tries=2, delay=1):
        log.debug("Ark not running, launching...")
        launch_program()
    log.debug("Maximizing ark window")
    maximize_window()
    buttons = ["start", "host", "run", "accept1", "accept2"]
    for b in buttons:
        res = click_button(b, images)
        if not res:
            return False

    log.info("Boot macro finished, server is loading")
    return is_running(tries=2, delay=1)


def wipe_server(include_cluster: bool = False):
    log.warning("WIPING SERVER")
    paths_to_delete = []

    if include_cluster:
        log.info("Also wiping cluster data")
        cpath = Path(rf"{Const.save_path}\clusters\solecluster")
        for i in cpath.iterdir():
            paths_to_delete.append(i)

    servers = Path(rf"{Const.save_path}\Maps")
    for mapfolder in servers.iterdir():
        for submapfolder_or_mapfile in mapfolder.iterdir():
            if submapfolder_or_mapfile.is_dir():
                for file in submapfolder_or_mapfile.iterdir():
                    paths_to_delete.append(file)
            else:
                paths_to_delete.append(submapfolder_or_mapfile)

    def filecheck(path: Path):
        conditions = [
            "sync" not in path.name.lower(),
            "ban" not in path.name.lower(),
            "paint" not in path.name.lower(),
        ]
        return all(conditions)

    to_del = [i for i in paths_to_delete if filecheck(i)]
    for i in to_del:
        os.remove(i)
    log.info(f"Deleted {len(to_del)} files")


def get_rcon_info():
    path = os.path.join(Const.config, "GameUserSettings.ini")
    parser = ConfigParser(strict=False)
    parser.read(path)
    port = parser.get("ServerSettings", "RCONPort", fallback=0)
    passwd = parser.get("ServerSettings", "ServerAdminPassword", fallback=None)
    return port, passwd


async def run_rcon(command: str, port: int, passwd: str):
    res = await rcon(command=command, host="127.0.0.1", port=int(port), passwd=passwd)
    return res
