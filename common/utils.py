import contextlib
import ctypes
import json
import logging
import os
import subprocess
import sys
import tempfile
from configparser import ConfigParser
from pathlib import Path
from time import sleep

import aiohttp
import psutil
import pyautogui
import pywintypes
import sentry_sdk
import win32api
import win32con
import win32gui
from pywinauto.application import Application
from pywinauto.findwindows import ElementAmbiguousError, ElementNotFoundError
from pywinauto.timings import TimeoutError
from rcon.source import rcon
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

log = logging.getLogger("ArkHandler.utils")


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


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


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
        integrations=[AioHttpIntegration()],
        release=version,
        environment="windows",
    )


async def check_for_updates(current_version: str):
    log.debug("Checking for updates")
    if not is_admin():
        log.debug("Not running as admin, skipping update check")
        return
    url = "https://api.github.com/repos/vertyco/ArkHandler/releases/latest"
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
    if "tag_name" not in data:
        log.debug("No releases found")
        return
    latest_version = data["tag_name"]
    log.debug(f"Current: {current_version}, Latest: {latest_version}")

    if str(latest_version) > str(current_version):
        log.warning(f"UPDATE DETECTED (Current: {current_version}, Latest: {latest_version})")
        for asset in data["assets"]:
            if asset["name"].endswith(".exe"):
                download_url = asset["browser_download_url"]
                await download_new_version(download_url)
                break
    else:
        log.debug("ArkHandler is on the latest version!")


async def download_new_version(url):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.read()

    temp_dir = tempfile.gettempdir()
    temp_file = os.path.join(temp_dir, "ArkHandler_new.exe")

    with open(temp_file, "wb") as f:
        f.write(content)

    replace_and_restart(temp_file)


def replace_and_restart(new_exe: str):
    log.warning("Installing...")
    current_exe = sys.executable
    os.remove(current_exe)
    os.rename(new_exe, current_exe)

    subprocess.Popen([current_exe])
    sys.exit()


def get_windows(name: str):
    """Get all windows associated with the provided string"""

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
    windows = [i for i in windows if name.lower() in i[1].lower()]
    return windows


def on_screen(path: str, confidence: float = 0.85):
    try:
        return pyautogui.locateOnScreen(path, confidence=confidence)
    except OSError:
        return False


def click_button(button: str, images: dict):
    """Click an ark button"""
    if button in images:
        while True:
            loc = on_screen(images[button])
            if loc is None:
                continue
            elif loc is False:
                sleep(30)
                break
            else:
                log.debug(f"{button} button located")
                break
    sleep(1.5)
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
    if button == "start":
        click(x, y, True)
    else:
        click(x, y)


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
        win32api.ChangeDisplaySettings(None, 0)
        return
    if abs(pyautogui.size().width - width) < 10:
        return
    if abs(pyautogui.size().height - height) < 10:
        return
    log.warning(f"Setting resolution to {width} by {height}")
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
            async with session.post(
                url=url, data=json.dumps(data), headers=headers, timeout=timeout
            ) as res:
                if res.status != 204:
                    log.warning(f"Failed to send {title} webhook. status {res.status}")
                else:
                    log.debug(f"{title} webhook sent successfully")
    except Exception as e:
        log.error(f"Failed to send {title} webhook", exc_info=e)


def kill(process: str = "ShooterGame.exe"):
    """Kill a process"""
    try:
        [p.kill() for p in psutil.process_iter() if p.name() == process]
    except Exception as e:
        log.error(f"Exceeption while killing {process}", exc_info=e)


def is_running(process: str = "ShooterGame.exe"):
    """Check if a process is running"""
    try:
        running = [p.name() for p in psutil.process_iter()]
    except psutil.NoSuchProcess:
        return False
    return process in running


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


def sync_file(source: str, filename: str):
    source = Path(source)
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
        log.info(f"Game.ini synced from {source}")
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
    for i in windows:
        win32gui.SetForegroundWindow(i[0])
        win32gui.PostMessage(i[0], win32con.WM_CLOSE, 0, 0)


def launch_ark() -> None:
    tries = 0
    while True:
        tries += 1
        os.system(Const.boot)
        sleep(15)
        if is_running():
            return
        kill()
        if tries >= 10:
            raise WindowsError("Ark failed to launch and may be corrupt")


def start_ark(images: dict):
    """Click through menu buttons to start server"""
    close_teamviewer()
    kill("WinStore.App.exe")
    set_resolution()
    if not is_running():
        launch_ark()
    windows = get_windows("ark: survival evolved")
    if not windows:
        raise WindowsError("Failed to fetch windows for Ark")
    for i in windows:
        win32gui.ShowWindow(i[0], win32con.SW_MAXIMIZE)
    click_button("start", images)
    click_button("host", images)
    click_button("run", images)
    click_button("accept1", images)
    click_button("accept2", images)
    log.info("Boot macro finished, server is loading")


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
