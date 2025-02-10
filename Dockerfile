FROM python:3.13-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN useradd --create-home botuser && \
    mkdir -p /home/botuser/discord-rss-bot/ /home/botuser/.local/share/discord_rss_bot/ && \
    chown -R botuser:botuser /home/botuser/
USER botuser
WORKDIR /home/botuser/discord-rss-bot
COPY --chown=botuser:botuser requirements.txt /home/botuser/discord-rss-bot/
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --no-install-project
EXPOSE 5000
VOLUME /home/botuser/.local/share/discord_rss_bot/
CMD ["uv", "run", "uvicorn", "discord_rss_bot.main:app", "--host=0.0.0.0", "--port=5000", "--proxy-headers", "--forwarded-allow-ips='*'", "--log-level", "debug"]
