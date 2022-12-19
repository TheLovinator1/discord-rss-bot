FROM python:3.11-slim

# Force the stdout and stderr streams to be unbuffered.
# Will allow log messages to be immediately dumped instead of being buffered.
# This is useful when the bot crashes before writing messages stuck in the buffer.
ENV PYTHONUNBUFFERED 1

# Don't generate byte code (.pyc-files).
# These are only needed if we run the python-files several times.
# Docker doesn't keep the data between runs so this adds nothing.
ENV PYTHONDONTWRITEBYTECODE 1

# Install Poetry
RUN pip install poetry --no-cache-dir --disable-pip-version-check --no-color

# Creata the botuser and create the directory where the code will be stored.
RUN useradd --create-home botuser && \
    install --verbose --directory --mode=0775 --owner=botuser --group=botuser /home/botuser/discord-rss-bot/ && \
    install --verbose --directory --mode=0775 --owner=botuser --group=botuser /home/botuser/.local/share/discord_rss_bot/

# Change to the bot user so we don't run as root.
USER botuser

# Copy files from our repository to the container.
ADD --chown=botuser:botuser pyproject.toml poetry.lock README.md LICENSE /home/botuser/discord-rss-bot/

# This is the directory where the code will be stored.
WORKDIR /home/botuser/discord-rss-bot

# Install the dependencies.
RUN poetry install --no-interaction --no-ansi --only main

ADD --chown=botuser:botuser discord_rss_bot /home/botuser/discord-rss-bot/discord_rss_bot/

EXPOSE 5000
VOLUME /home/botuser/.local/share/discord_rss_bot/

CMD ["poetry", "run", "uvicorn", "discord_rss_bot.main:app", "--host", "0.0.0.0", "--port", "5000", "--proxy-headers"]