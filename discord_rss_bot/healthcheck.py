"""This is used as a healthcheck in the Dockerfile.
The normal way would probably be to use CURL, but then we would have to install it."""

import sys

import requests


def healthcheck():
    """Check if the website is up."""
    try:
        r = requests.get("http://localhost:5000")
        if r.ok:
            sys.exit(0)
    except requests.exceptions.RequestException:
        sys.exit(1)


if __name__ == "__main__":
    healthcheck()
