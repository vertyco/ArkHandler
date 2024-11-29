![Platform](https://img.shields.io/badge/Windows-0078D6?style=for-the-badge&logo=windows&logoColor=white)
![Python 3.11](https://img.shields.io/badge/python-v3.11-blue?style=for-the-badge)

![Repo-Size](https://img.shields.io/github/repo-size/vertyco/vrt-cogs)

# ArkHandler - Player Dedicated Server Automation

This project aims to make self-hosting player dedicated servers using the Microsoft Store version of Ark Survival Evolved a more viable alternative over using Nitrado.

## Features

- Automatic server restarts on crash
- Syncs ini files from a backup or main location before it boots
- Sends webhook notifications to discord if the server crashes

## QuickStart

The following steps are the only support I provide for this project.

1. Head to the **[Releases](https://github.com/vertyco/ArkHandler/releases)** page and download the `ArkHandler.exe` executable.
2. Place the executable in a folder on your desktop or place of your choosing.
3. Run the executable and it will generate a `config.ini` file.
4. Optionally, you can change the `config.ini` settings file to your liking.
5. Run the executable again and it will start and monitor your server.

## Automatic Restarts after PC Reboot

- Open Task Scheduler
- Click `Create Task` button on the right side of the window
- Name it something like "ArkHandler"
- Select `Run with highest privileges`
- Select `Configure for: Windows 10`
- Go to the `Triggers` tab and click `New`
- Select `At log on` from the dropdown menu
- Click `OK`
- Go to the `Actions` tab and click `New`
- Click `Browse` and navigate to the `ArkHandler.exe` executable
- Right click on the file location in the Windows Exporer path bar and click `Copy address as text`
- Click "ArkHandler.exe" and then click "Open"
- In the `Start in (optional)` field, paste the path you copied earlier
- Click `OK`
- Go to the `Settings` tab and uncheck `Stop the task if it runs longer than:`
- Click `OK`

If you have configured your Win10 PC to auto-login, the server will start automatically after a reboot.

- Go [here](https://www.intowindows.com/how-to-automatically-login-in-windows-10/) for setting up Auto-Login and follow method 2.
- Go [Here](https://answers.microsoft.com/en-us/windows/forum/all/turn-off-automatic-reboot-with-updates-lets/851bef8c-157d-4301-8128-9c5d3a4bd547) for help with disabling automatic updates and restarts.

### Default Config

`config.ini`

```ini
[UserSettings]
# WebhookURL (Optional): Discord webhook url goes here, you can google how to generate it
WebhookURL =

# GameiniPath (Optional): The path to your backup Game.ini file if you have one
# When this is set the program will copy the Game.ini file to the game directory before starting the game
GameiniPath =

# GameUserSettingsiniPath (Optional): The path you your backup GameUserSettings.ini file
# When this is set the program will copy the GameUserSettings.ini file to the game directory before starting the game
GameUserSettingsiniPath =

# Debug field, if True, shows extra data in the console(for debug purposes)
Debug = False

# Sentry DSN key (Optional) - If this is not set, it will use the default public DSN key
SentryDSN =
```
