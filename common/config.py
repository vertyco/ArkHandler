import typing as t
from configparser import ConfigParser
from pathlib import Path

from pydantic import BaseModel

from common import const


class Conf(BaseModel):
    webhook_url: str
    game_ini: str
    gameusersettings_ini: str
    sentry_dsn: str
    debug: bool

    @property
    def game_ini_path(self) -> Path:
        return Path(self.game_ini)

    @property
    def gameusersettings_ini_path(self) -> Path:
        return Path(self.gameusersettings_ini)

    @classmethod
    def load(cls, path: str) -> t.Self:
        parser = ConfigParser()
        parser.read(path)
        settings = parser["UserSettings"]
        config = {
            "webhook_url": settings.get("WebhookURL", fallback="").replace('"', ""),
            "game_ini": settings.get("GameiniPath", fallback="").replace('"', ""),
            "gameusersettings_ini": settings.get("GameUserSettingsiniPath", fallback="").replace('"', ""),
            "sentry_dsn": settings.get("SentryDSN", fallback=const.DSN_FALLBACK).replace('"', ""),
            "debug": settings.getboolean("Debug", fallback=False),
        }
        if config["game_ini"]:
            if Path(config["game_ini"]).is_dir():
                config["game_ini"] = str(Path(config["game_ini"]) / "Game.ini")
            if not Path(config["game_ini"]).exists():
                raise FileNotFoundError(f"game.ini not found: {config['game_ini']}")
        if config["gameusersettings_ini"]:
            if Path(config["gameusersettings_ini"]).is_dir():
                config["gameusersettings_ini"] = str(Path(config["gameusersettings_ini"]) / "GameUserSettings.ini")
            if not Path(config["gameusersettings_ini"]).exists():
                raise FileNotFoundError(f"gameusersettings_ini not found: {config['gameusersettings_ini']}")
        if config["webhook_url"] and not config["webhook_url"].startswith("https://discord.com/api/webhooks/"):
            raise ValueError(f"Invalid webhook_url: {config['webhook_url']}")
        return super().model_validate(config)
