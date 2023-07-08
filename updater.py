import asyncio
import ctypes
import logging
import os
import subprocess
import sys

import aiohttp
import psutil

from common import VERSION

APP_NAME = "ArkHandler"
APP_VERSION = VERSION

url = "https://api.github.com/repos/vertyco/ArkHandler/releases/latest"
log = logging.getLogger("ArkHandler.updater")


def is_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except Exception:
        return False


def print_status_info(info):
    total = info.get("total")
    downloaded = info.get("downloaded")
    status = info.get("status")
    print(downloaded, total, status)


async def check_arkhandler_updates():
    log.debug("Checking for updates!")
    return await check_for_updates(VERSION)


async def check_for_updates(current_version: str) -> str | None:
    if not is_admin():
        log.debug("Is not admin")
        return
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            data = await response.json()
    if "tag_name" not in data:
        log.debug(f"No releases found: {data}")
        return
    latest_version = data["tag_name"]
    log.debug(f"Latest: {latest_version}, Current: {current_version}")
    if str(latest_version) <= str(current_version):
        log.debug("ArkHandler is up to date!")
        return
    for asset in data["assets"]:
        print("ASSET", asset)
        if asset["name"].endswith(".exe"):
            return asset["browser_download_url"]


async def download(url: str, filename: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as response:
            content = await response.read()

    with open(filename, "wb") as f:
        f.write(content)


async def execute_update():
    print("Update starting in 10 seconds")
    await asyncio.sleep(10)
    print("Killing process if still running")
    for p in psutil.process_iter():
        if p.name() == "ArkHandler.exe":
            p.kill()
            break

    download_url = sys.argv[1]
    root = sys.argv[2]

    print("DOWNLOAD URL:", download_url)
    print("PATH:", root)

    exe_path = f"{root}/ArkHandler.exe"
    temp_file = f"{root}/ArkHandler_new.exe"

    # First lets download the new version
    await download(download_url, temp_file)
    # Replace the old .exe file with the new one
    if os.path.exists(exe_path):
        os.remove(exe_path)
    os.rename(temp_file, exe_path)
    # Start the new ArkHandler.exe
    subprocess.Popen([exe_path], start_new_session=True, shell=True)


if __name__ == "__main__":
    asyncio.run(execute_update())
