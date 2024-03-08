![Platform](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Python 3.11](https://img.shields.io/badge/python-v3.11-blue?style=for-the-badge)

![Repo-Size](https://img.shields.io/github/repo-size/vertyco/vrt-cogs)

# ArkHandler

Crossplay Server Management Script

This is a little script I wrote to handle my ark servers

- Auto-reboots on crash via screen mapping
- Syncs ini files from a backup or main location before it boots
- Checks for updates automatically and installs them
- Sends webhook notifications to discord if the server crashes or has an update

I am not currently providing direct support for this script.

### Default Config

`config.ini`

```ini
[UserSettings]
# WebhookURL (Optional): Discord webhook url goes here, you can google how to generate it
WebhookURL =

# GameiniPath (Optional): The path to your backup Game.ini file if you have one
GameiniPath =

# GameUserSettingsiniPath (Optional): The path you your backup GameUserSettings.ini file
GameUserSettingsiniPath =

# Debug field, if True, shows extra data in the console(for debug purposes)
Debug = False

# Automatically download/install new releases
AutoUpdate = True

# Sentry DSN key (Optional)
SentryDSN =
```
