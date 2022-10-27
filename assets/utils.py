import json
import logging
import os
import shutil
from configparser import ConfigParser
from pathlib import Path
from time import sleep

import aiohttp
import psutil
import pyautogui
import pywinauto.findwindows
import pywintypes
import win32api
import win32con
import win32gui
from pywinauto.application import Application
from rcon.source import rcon

log = logging.getLogger("arkhandler")


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
        "accept2": (0.568, 0.6905)
    }
    # Ark paths
    save_path = fr"{os.environ['LOCALAPPDATA']}\Packages\StudioWildcard.4558480580BB9_1w2mm55455e38\LocalState\Saved"
    boot = r"explorer.exe shell:appsFolder\StudioWildcard.4558480580BB9_1w2mm55455e38!AppARKSurvivalEvolved"
    config = fr"{save_path}\UWPConfig\UWP"

    logo = r"""
                _    _    _                 _ _           
     /\        | |  | |  | |               | | |          
    /  \   _ __| | _| |__| | __ _ _ __   __| | | ___ _ __ 
   / /\ \ | '__| |/ /  __  |/ _` | '_ \ / _` | |/ _ \ '__|
  / ____ \| |  |   <| |  | | (_| | | | | (_| | |  __/ |   
 /_/    \_\_|  |_|\_\_|  |_|\__,_|_| |_|\__,_|_|\___|_|                                                                                                                     
  ___       __   __       _               
 | _ )_  _  \ \ / /__ _ _| |_ _  _ __ ___ 
 | _ \ || |  \ V / -_) '_|  _| || / _/ _ \
 |___/\_, |   \_/\___|_|  \__|\_, \__\___/
      |__/                    |__/        
"""

    default_config = """
    # OPTIONS
    # NetDownKill: How long(in minutes) internet is down before killing the servers and pausing ArkHandler
    #  - set to 0 to disable
    # WebhookURL: Discord webhook url goes here, you can google how to generate it
    # GameiniPaht: The path to your backup Game.ini file if you have one
    # GameUserSettingsiniPath: The path you your backup GameUserSettings.ini file
    # AutoWipe: Toggle auto wipe on or off
    # AlsoWipeClusterData: Self explanatory, when a server wipes, toggle to include cluster data
    # WipeTimes: List of times separated by commas in the format "mm/dd HH:MM"
    # Example: 04/10 12:30,08/20 17:00, 01/19 7:45
    # Debug field, if True, shows extra data in the console(for debug purposes)
    
    
    [Settings]
    NetDownKill = 3
    WebhookURL = ""
    GameiniPath = ""
    GameUserSettingsiniPath = ""
    AutoWipe = False
    AlsoWipeClusterData = False
    WipeTimes =
    Debug = False
    """


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


def on_screen(path: str, confidence: float = 0.8):
    return pyautogui.locateOnScreen(path, confidence=confidence)


def click_button(button: str, images: dict):
    """Click an ark button"""
    if button in images:
        while True:
            loc = on_screen(images[button])
            if loc is not None:
                break
    sleep(1)
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
    em = {
        "title": title,
        "description": message,
        "color": color
    }
    if footer:
        em["footer"] = {"text": footer}
    data = {
        "username": "ArkHandler",
        "avatar_url": "https://i.imgur.com/Wv5SsBo.png",
        "embeds": [em]
    }
    headers = {"Content-Type": "application/json"}
    try:
        async with aiohttp.ClientSession() as session:
            timeout = aiohttp.ClientTimeout(total=20)
            async with session.post(
                    url=url,
                    data=json.dumps(data),
                    headers=headers,
                    timeout=timeout
            ) as res:
                if res.status != 204:
                    log.warning(f"Failed to send {title} webhook. status {res.status}")
                else:
                    log.debug(f"{title} webhook sent successfully")
    except Exception as e:
        log.warning(f"Failed to send {title} webhook: {e}")


def kill(process: str = "ShooterGame.exe"):
    """Kill a process"""
    [p.kill() for p in psutil.process_iter() if p.name() == process]


def is_running(process: str = "ShooterGame.exe"):
    """Check if a process is running"""
    running = [p.name() for p in psutil.process_iter()]
    return process in running


def update_ready(prog: Application, name: str):
    """Check if an app has an update (MS Store must be open)"""
    window = prog.top_window()
    for i in window.descendants(control_type="Button"):
        if name.lower() in str(i).lower() and "update available" in str(i).lower():
            return True
    else:
        return False


def is_updating(prog: Application, name: str):
    """Check if an app is updating (MS Store must be open)"""
    window = prog.top_window()
    for i in window.descendants(control_type="Button"):
        conditions = [
            name.lower() in str(i).lower(),
            "download" in str(i).lower(),
            "installing" in str(i).lower(),
            "pending" in str(i).lower()
        ]
        if any(conditions):
            return True
    else:
        return False


def check_updates():
    """Check MS store for updates"""
    if not is_running("WinStore.App.exe"):
        os.system("explorer.exe shell:appsFolder\Microsoft.WindowsStore_8wekyb3d8bbwe!App")
    app = Application(backend="uia")
    while True:
        try:
            app = app.connect(title="Microsoft Store")
            break
        except pywinauto.findwindows.ElementNotFoundError:
            continue

    windows = get_windows("Microsoft Store")
    if len(windows) > 1 and windows[0][2][1] == 1:
        for i in windows:
            win32gui.ShowWindow(i[0], win32con.SW_RESTORE)

    dlg = app.top_window()
    # Library button
    try:
        library_button = dlg.window(title="Library")

        library_button.wait("ready", timeout=120, retry_interval=1)
        library_button.click_input()
    except pywinauto.findwindows.ElementAmbiguousError:
        pass
    # Update button
    update_button = dlg.window(auto_id="CheckForUpdatesButton")
    update_button.wait("ready")
    update_button.click()
    dlg.window(control_type="Button", auto_id="Minimize").click()
    return app


def sync_inis(game: str, gameuser: str):
    """Update ark UWP config files"""
    if not Path(Const.config).exists():
        return
    # Game.ini
    source = Path(game)  # File to sync
    if source.exists() and game:
        target = Path(fr"{Const.config}\Game.ini")
        if target.exists():
            try:
                os.remove(target)
            except (OSError, WindowsError):
                pass
        shutil.copyfile(source, target)
        log.info("Game.ini synced")
    # GameUserSettings.ini
    source = Path(gameuser)
    if source.exists() and gameuser:
        target = Path(fr"{Const.config}\GameUserSettings.ini")
        if target.exists():
            try:
                os.remove(target)
            except (OSError, WindowsError):
                pass
        shutil.copyfile(source, target)
        log.info("GameUserSettings.ini synced")


def close_teamviewer():
    windows = get_windows("sponsored session")
    if not windows:
        return
    for i in windows:
        win32gui.SetForegroundWindow(i[0])
        win32gui.PostMessage(i[0], win32con.WM_CLOSE, 0, 0)


def launch_ark():
    tries = 0
    while True:
        tries += 1
        os.system(Const.boot)
        sleep(5)
        if is_running():
            break
        if tries >= 10:
            raise WindowsError("Ark failed to boot and may be corrupt")


def start_ark(images: dict):
    """Click through menu buttons to start server"""
    close_teamviewer()
    set_resolution()
    if not is_running():
        launch_ark()
    windows = get_windows("ark: survival evolved")
    if not windows:
        raise WindowsError("Ark failed to boot and may be corrupt")
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
    kill()
    if include_cluster:
        log.info("Also wiping cluster data")
        cpath = Path(fr"{Const.save_path}\clusters\solecluster")
        data = [i for i in cpath.iterdir()]
        for arkdata in data:
            os.remove(os.path.join(cpath, str(arkdata)))
    servers = Path(fr"{Const.save_path}\Maps")
    paths_to_delete = []
    for folder in servers.iterdir():
        if "painting" in folder.name.lower():
            continue
        if "sync" in folder.name.lower():
            continue
        for item in folder.iterdir():
            if item.is_dir():
                for file in item.iterdir():
                    if file.is_dir():
                        continue
                    paths_to_delete.append(file)
            else:
                paths_to_delete.append(item)

    to_del = [i for i in paths_to_delete if "ban" not in i.name.lower() and "paint" not in i.name.lower()]
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
    res = await rcon(
        command=command,
        host="localhost",
        port=int(port),
        passwd=passwd
    )
    return res
