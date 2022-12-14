from typing import Literal

from fastapi.testclient import TestClient
from httpx import Response

from discord_rss_bot.main import app, encode_url

client: TestClient = TestClient(app)


def test_read_main() -> None:
    """Test the main page."""
    response: Response = client.get("/")
    assert response.status_code == 200


def test_add() -> None:
    """Test the /add page."""
    response: Response = client.get("/add")
    assert response.status_code == 200


def test_search() -> None:
    """Test the /search page."""
    response: Response = client.get("/search/?query=a")
    assert response.status_code == 200


def test_encode_url() -> None:
    """Test the encode_url function."""
    before: Literal["https://www.google.com/"] = "https://www.google.com/"
    after: Literal["https%3A//www.google.com/"] = "https%3A//www.google.com/"
    assert encode_url(url_to_quote=before) == after
