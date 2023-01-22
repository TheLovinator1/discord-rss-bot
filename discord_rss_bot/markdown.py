from functools import lru_cache

from bs4 import BeautifulSoup


@lru_cache(maxsize=2048)
def convert_html_to_md(html: str) -> str:
    """Convert HTML to Markdown.

    Discord supports:
    - Bold with **text**
    - Italic with *text*
    - Blockquote with >>> text
    - Code with `text`
        - Fence code with ```text```
    - Links with [text](url)
    - Syntax highlighting with ```language
    - Strikethrough with ~~text~~
    """
    soup: BeautifulSoup = BeautifulSoup(html, features="lxml")

    # Bold
    for bold in soup.find_all("b") + soup.find_all("strong"):
        bold.replace_with(f"**{bold.text}**")

    # Italic
    for italic in soup.find_all("i") + soup.find_all("em"):
        italic.replace_with(f"*{italic.text}*")

    # Blockquote
    for blockquote in soup.find_all("blockquote") + soup.find_all("q"):
        blockquote.replace_with(f">>> {blockquote.text}")

    # Code
    for code in soup.find_all("code") + soup.find_all("pre"):
        code.replace_with(f"`{code.text}`")

    # Links
    for link in soup.find_all("a") + soup.find_all("link"):
        link_text = link.text or link.get("href") or "Link"
        link.replace_with(f"[{link_text}]({link.get('href')})")

    # Strikethrough
    for strikethrough in soup.find_all("s") + soup.find_all("del") + soup.find_all("strike"):
        strikethrough.replace_with(f"~~{strikethrough.text}~~")

    # <br> tags
    for br in soup.find_all("br"):
        br.replace_with("\n")

    # Remove all other tags
    for tag in soup.find_all(True):
        tag.replace_with(tag.text)

    # Remove all leading and trailing whitespace
    soup_text = soup.text
    return soup_text.strip()


# Test the function
if __name__ == "__main__":
    html: str = """
    <p><b>bold</b> <i>italic</i> <a href="https://example.com">link</a> <code>code</code> <s>strikethrough</s></p>
    <blockquote>blockquote</blockquote>
    <pre><code>pre code</code></pre>
    <strong>strong</strong>
    """
    print(convert_html_to_md(html))
