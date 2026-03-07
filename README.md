# discord-rss-bot

Subscribe to RSS feeds and get updates to a Discord webhook.

Email: [tlovinator@gmail.com](mailto:tlovinator@gmail.com)

Discord: TheLovinator#9276

## Features

- Subscribe to RSS feeds and get updates to a Discord webhook.
- Web interface to manage subscriptions.
- Customizable message format for each feed.
- Choose between Discord embed or plain text.
- Regex filters for RSS feeds.
- Blacklist/whitelist words in the title/description/author/etc.
- Gets extra information from APIs if available, currently for:
  - [https://feeds.c3kay.de/](https://feeds.c3kay.de/)
    - Genshin Impact News
    - Honkai Impact 3rd News
    - Honkai Starrail News
    - Zenless Zone Zero News

## Installation

You have two choices, using [Docker](#docker)
or [install directly on your computer](#install-directly-on-your-computer).

### Docker

- Open a terminal in the repository folder.
  - <kbd>Shift</kbd> + <kbd>right-click</kbd> in the folder and `Open PowerShell window here`
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

- Install the latest of [uv](https://docs.astral.sh/uv/#installation):
  - `powershell -ExecutionPolicy ByPass -c "irm <https://astral.sh/uv/install.ps1> | iex"`
- Download the project from GitHub with Git or download
  the [ZIP](https://github.com/TheLovinator1/discord-rss-bot/archive/refs/heads/master.zip).
  - If you want to update the bot, you can run `git pull` in the project folder or download the ZIP again.
- Open a terminal in the repository folder.
  - <kbd>Shift</kbd> + <kbd>right-click</kbd> in the folder and `Open PowerShell window here`
- Start the bot:
  - Type `uv run discord_rss_bot/main.py` into the PowerShell window.
    - You can stop the bot with <kbd>Ctrl</kbd> + <kbd>c</kbd>.
- Bot is now running on port 3000.
- You should run this bot behind a reverse proxy like [Caddy](https://caddyserver.com/)
  or [Nginx](https://www.nginx.com/) if you want to access it from the internet. Remember to add authentication.
- You can access the web interface at `http://localhost:3000/`.

- To run automatically on boot:
  - Use [Windows Task Scheduler](https://en.wikipedia.org/wiki/Windows_Task_Scheduler).
  - Or add a shortcut to `%userprofile%\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\Startup`.

## Git Backup (State Version Control)

The bot can commit every configuration change (adding/removing feeds, webhook
changes, blacklist/whitelist updates) to a separate private Git repository so
you get a full, auditable history of state changes — similar to `etckeeper`.

### Configuration

Set the following environment variables (e.g. in `docker-compose.yml` or a
`.env` file):

| Variable            | Required | Description                                                                                                                         |
| ------------------- | -------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| `GIT_BACKUP_PATH`   | Yes      | Local path where the backup git repository is stored. The bot will initialise it automatically if it does not yet exist.            |
| `GIT_BACKUP_REMOTE` | No       | Remote URL to push to after each commit (e.g. `git@github.com:you/private-config.git`). Leave unset to keep the history local only. |

### What is backed up

After every relevant change a `state.json` file is written and committed.
The file contains:

- All feed URLs together with their webhook URL, custom message, embed
  settings, and any blacklist/whitelist filters.
- The global list of Discord webhooks.

### Docker example

```yaml
services:
  discord-rss-bot:
    image: ghcr.io/thelovinator1/discord-rss-bot:latest
    volumes:
      - ./data:/data
    environment:
      - GIT_BACKUP_PATH=/data/backup
      - GIT_BACKUP_REMOTE=git@github.com:you/private-config.git
```

For SSH-based remotes mount your SSH key into the container and make sure the
host key is trusted, e.g.:

```yaml
    volumes:
      - ./data:/data
      - ~/.ssh:/root/.ssh:ro
```
