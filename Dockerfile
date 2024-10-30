# Stage 1: Build the requirements.txt using Poetry.
FROM python:3.13 AS builder

# Set environment variables for Python.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1
ENV PATH="${PATH}:/root/.local/bin"

# Install system dependencies.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry.
RUN curl -sSL https://install.python-poetry.org | python3 -

# Copy only the poetry.lock/pyproject.toml to leverage Docker cache.
WORKDIR /app
COPY pyproject.toml poetry.lock /app/

# Install dependencies and create requirements.txt.
RUN poetry self add poetry-plugin-export && poetry export --format=requirements.txt --output=requirements.txt --only=main --without-hashes

# Stage 2: Install dependencies and run the application
FROM python:3.13 AS runner

# Set environment variables for Python.
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

# Create a non-root user.
RUN useradd -ms /bin/bash botuser && \
    install --verbose --directory --mode=0775 --owner=botuser --group=botuser /home/botuser/discord-rss-bot/ && \
    install --verbose --directory --mode=0775 --owner=botuser --group=botuser /home/botuser/.local/share/discord_rss_bot/

# Copy the generated requirements.txt from the builder stage.
WORKDIR /home/botuser/discord-rss-bot
COPY --from=builder /app/requirements.txt /home/botuser/discord-rss-bot/

# Create a virtual environment and install dependencies.
RUN python -m venv /home/botuser/.venv && \
    . /home/botuser/.venv/bin/activate && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --upgrade setuptools wheel && \
    pip install --no-cache-dir --requirement requirements.txt

# Copy the rest of the application code.
COPY . /home/botuser/discord-rss-bot/

# Change to the bot user so we don't run as root.
USER botuser

# The uvicorn server will listen on this port.
EXPOSE 5000

# Where our database file will be stored.
VOLUME /home/botuser/.local/share/discord_rss_bot/

# Print the folder structure and wait so we can inspect the container.
# CMD ["tail", "-f", "/dev/null"]

# Run the application.
CMD ["/home/botuser/.venv/bin/python", "-m", "uvicorn", "discord_rss_bot.main:app", "--host=0.0.0.0", "--port=5000", "--proxy-headers", "--forwarded-allow-ips='*'", "--log-level", "debug"]
