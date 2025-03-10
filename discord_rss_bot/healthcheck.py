from __future__ import annotations

import sys

import requests


def healthcheck() -> None:
    """Check if the website is up.

    sys.exit(0): success - the container is healthy and ready for use.
    sys.exit(1): unhealthy - the container is not working correctly.
    """
    # TODO(TheLovinator): We should check more than just that the website is up.
    try:
        r: requests.Response = requests.get(url="http://localhost:5000", timeout=5)
        if r.ok:
            sys.exit(0)
    except requests.exceptions.RequestException as e:
        print(f"Healthcheck failed: {e}", file=sys.stderr)  # noqa: T201
        sys.exit(1)


if __name__ == "__main__":
    healthcheck()
