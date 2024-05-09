import os
import sys
from pathlib import Path

SUPPORTED_RESOLUTIONS = [
    (1280, 720),
    (2560, 1440),
]

IS_EXE = True if (getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS")) else False
if IS_EXE:
    ROOT_PATH = Path(os.path.dirname(os.path.abspath(sys.executable)))
else:
    ROOT_PATH = Path(os.path.dirname(os.path.abspath(__file__))).parent

META_PATH = Path(os.path.abspath(os.path.dirname(__file__))).parent

ASSET_PATH = META_PATH / "assets"
IMAGE_PATH = META_PATH / "resolutions"
CONF_PATH = ROOT_PATH / "config.ini"
DEFAULT_CONF_TEXT = (ASSET_PATH / "default_config.ini").read_text()
BANNER_TEXT = (ASSET_PATH / "banner.txt").read_text()
POSITIONS_PATH = IMAGE_PATH / "positions.json"

DOWNLOAD = "**The server has started downloading an update, and will go down once it starts installing.**"
INSTALL = "**The server has started installing the update. Stand by...**"
COMPLETE = "**The server has finished installing the update.**"

APP = "StudioWildcard.4558480580BB9_1w2mm55455e38"
SAVE_PATH = Path(os.environ["LOCALAPPDATA"]) / "Packages" / APP / "LocalState" / "Saved"
CLUSTER_PATH = SAVE_PATH / "clusters" / "solecluster"
INI_PATH = SAVE_PATH / "UWPConfig" / "UWP"

BOOT_COMMAND = rf"explorer.exe shell:appsFolder\{APP}!AppARKSurvivalEvolved"
MS_BOOT_COMMAND = r"explorer.exe shell:appsFolder\Microsoft.WindowsStore_8wekyb3d8bbwe!App"
DSN_FALLBACK = "https://49f9dec01c25b19eda9eaf449a017bf9@sentry.vertyco.net/5"

BAR = [
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
