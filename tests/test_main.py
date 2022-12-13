from fastapi.testclient import TestClient

from discord_rss_bot.main import app, create_list_of_webhooks, encode_url

client = TestClient(app)


def test_read_main():
    response = client.get("/")
    assert response.status_code == 200


def test_add():
    response = client.get("/add")
    assert response.status_code == 200


def test_search():
    response = client.get("/search/?query=a")
    assert response.status_code == 200


def test_encode_url():
    before = "https://www.google.com/"
    after = "https%3A//www.google.com/"
    assert encode_url(url_to_quote=before) == after
