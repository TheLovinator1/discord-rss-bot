# discord-rss-bot

Subscribe to RSS feeds and get updates to a Discord webhook.

## Conf

```
# Generate Django secret key
echo "DJANGO_SECRET_KEY=$(python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())")" > .env
```

## Run

```
# Development

uv run python manage.py migrate
uv run python manage.py createsuperuser --username TheLovinator --email tlovinator@gmail.com
uv run python manage.py makemigrations
uv run python manage.py check
uv run python manage.py runserver 0.0.0.0:8000
```

## Contact

Email: [tlovinator@gmail.com](mailto:tlovinator@gmail.com)

Discord: TheLovinator#9276
