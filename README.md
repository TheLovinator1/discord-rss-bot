# discord-rss-bot

A RSS bot for Discord built with [reader](https://github.com/lemon24/reader). It is designed to be executed by
a [cron job](https://wiki.archlinux.org/title/Cron) or [systemd timer](https://wiki.archlinux.org/title/Systemd/Timers).

    Usage: discord_rss_bot.py [OPTIONS] COMMAND [ARGS]...

    Options:
    --install-completion  Install completion for the current shell.
    --show-completion     Show completion for the current shell, to copy it or customize the installation.
    --help                Show this message and exit.

    Commands:
    add          Add a feed to the database
    backup       Backup the database
    check        Check new entries for every feed
    delete       Delete a feed from the database
    stats        Print the number of feeds and entries in the database
    webhook-add  Add a webhook to the database
    webhook-get  Get the webhook url
