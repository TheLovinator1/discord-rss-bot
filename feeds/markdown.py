from __future__ import annotations

from typing import Any
from urllib.parse import ParseResult, parse_qs, urlencode, urlparse, urlunparse

from bs4 import BeautifulSoup


def convert_html_to_md(html: str | None) -> str:  # noqa: C901
    """Convert HTML to markdown.

    Args:
        html: The HTML to convert.

    Returns:
        Our markdown.
    """
    if not html:
        return "No content."

    soup: BeautifulSoup = BeautifulSoup(html, features="lxml")

    for bold in soup.find_all("b") + soup.find_all("strong"):
        bold.replace_with(f"**{bold.text}**")

    for italic in soup.find_all("i") + soup.find_all("em"):
        italic.replace_with(f"*{italic.text}*")

    for blockquote in soup.find_all("blockquote") + soup.find_all("q"):
        blockquote.replace_with(f">>> {blockquote.text}")

    for code in soup.find_all("code") + soup.find_all("pre"):
        code.replace_with(f"`{code.text}`")

    for image in soup.find_all("img"):
        image.decompose()

    for link in soup.find_all("a") + soup.find_all("link"):
        handle_links(link)

    for strikethrough in soup.find_all("s") + soup.find_all("del") + soup.find_all("strike"):
        strikethrough.replace_with(f"~~{strikethrough.text}~~")

    for br in soup.find_all("br"):
        br.replace_with("\n")

    clean_soup: BeautifulSoup = BeautifulSoup(str(soup).replace("</p>", "</p>\n"), features="lxml")

    # Remove all other tags
    for tag in clean_soup.find_all(True):  # noqa: FBT003
        tag.replace_with(tag.text)

    return clean_soup.text.strip()


def handle_links(link: Any) -> None:  # noqa: ANN401
    """Handle links in the HTML.

    Args:
        link: The link to handle.
    """
    if not link.get_text().strip():
        link.decompose()
    else:
        url: str = link.get("href", "")
        if url:
            parsed_url: ParseResult = urlparse(url)
            query_params: dict[str, list[str]] = parse_qs(parsed_url.query)

            # Remove UTM parameters
            query_params = {key: value for key, value in query_params.items() if not key.startswith("utm_")}

            # Reconstruct the URL without UTM parameters
            new_query: str = urlencode(query_params, doseq=True)
            clean_url: str = urlunparse(parsed_url._replace(query=new_query))

            link_text: str = str(link.text) or clean_url
            link_text = link_text.replace("https://", "").replace("http://", "").replace("www.", "")
            link.replace_with(f"[{link_text}]({clean_url})")
