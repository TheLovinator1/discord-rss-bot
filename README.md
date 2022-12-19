# discord-rss-bot

Subscribe to RSS feeds and get updates to a Discord webhook. Built with [reader](https://github.com/lemon24/reader).

## Installation

You have two choices, using [Docker](https://github.com/TheLovinator1/discord-rss-bot)
or [install directly on your computer](#Install-directly-on-your-computer).

### Docker

- Open a terminal in the repository folder.
    - Windows 10: <kbd>Shift</kbd> + <kbd>right-click</kbd> in the folder and select `Open PowerShell window here`
    - Windows 11: <kbd>Shift</kbd> + <kbd>right-click</kbd> in the folder and Show more options
      and `Open PowerShell window here`
- Run the Docker Compose file:
    - `docker-compose up`
        - You can stop the bot with <kbd>Ctrl</kbd> + <kbd>c</kbd>.
        - If you want to run the bot in the background, you can run `docker-compose up -d`.
- You should run this bot behind a reverse proxy like [Caddy](https://caddyserver.com/)
  or [Nginx](https://www.nginx.com/).
    - 5000 is the port the bot listens on.
- You can update the container with `docker-compose pull`
    - You can automate this with [Watchtower](https://github.com/containrrr/watchtower)
      or [Diun](https://github.com/crazy-max/diun)

### Install directly on your computer

This is not recommended if you don't have an init system (e.g., systemd)

- Install the latest version of needed software:
    - [Python](https://www.python.org/)
        - You should use the latest version.
        - You want to add Python to your PATH.
        - Windows: Find `App execution aliases` and disable python.exe and python3.exe
    - [Poetry](https://python-poetry.org/docs/master/#installation)
        - Windows: You have to add `%appdata%\Python\Scripts` to your PATH for Poetry to work.
- Download the project from GitHub with Git or download
  the [ZIP](https://github.com/TheLovinator1/discord-rss-bot/archive/refs/heads/master.zip).
    - If you want to update the bot, you can run `git pull` in the project folder or download the ZIP again.
- Open a terminal in the repository folder.
    - Windows 10: <kbd>Shift</kbd> + <kbd>right-click</kbd> in the folder and select `Open PowerShell window here`
    - Windows 11: <kbd>Shift</kbd> + <kbd>right-click</kbd> in the folder and Show more options
      and `Open PowerShell window here`
- Install requirements:
    - Type `poetry install` into the PowerShell window. Make sure you are
      in the repository folder where the [pyproject.toml](pyproject.toml) file is located.
        - (You may have to restart your terminal if it can't find the `poetry` command. Also double check it is in
          your PATH.)
- Start the bot:
    - Type `poetry run bot` into the PowerShell window.
        - You can stop the bot with <kbd>Ctrl</kbd> + <kbd>c</kbd>.

Note: You will need to run `poetry install` again if [poetry.lock](poetry.lock) has been modified.

## Need help?

- Email: [tlovinator@gmail.com](mailto:tlovinator@gmail.com)
- Discord: TheLovinator#9276
- Send an issue: [discord-rss-bot/issues](https://github.com/TheLovinator1/discord-rss-bot/issues)
