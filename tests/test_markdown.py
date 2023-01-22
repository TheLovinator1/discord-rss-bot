from discord_rss_bot.markdown import convert_html_to_md


def test_convert_to_md():
    # Test bold
    assert convert_html_to_md("<b>bold</b>") == "**bold**"

    # Test italic
    assert convert_html_to_md("<i>italic</i>") == "*italic*"

    # Test blockquote
    assert convert_html_to_md("<blockquote>blockquote</blockquote>") == ">>> blockquote"

    # Test code
    assert convert_html_to_md("<code>code</code>") == "`code`"

    # Test strikethrough
    assert convert_html_to_md("<s>strikethrough</s>") == "~~strikethrough~~"

    # Test link
    assert convert_html_to_md('<a href="https://example.com">link</a>') == "[link](https://example.com)"

    # Test pre code
    assert convert_html_to_md("<pre><code>pre code</code></pre>") == "``pre code``"

    # Test strong
    assert convert_html_to_md("<strong>strong</strong>") == "**strong**"

    # Test multiple tags
    assert (
        convert_html_to_md(
            '<b>bold</b> <i>italic</i> <a href="https://example.com">link</a> <code>code</code> <s>strikethrough</s>'
        )
        == "**bold** *italic* [link](https://example.com) `code` ~~strikethrough~~"
    )

    # Test removing all other tags
    assert convert_html_to_md("<p>paragraph</p>") == "paragraph"
    assert convert_html_to_md("<p>paragraph</p><p>paragraph</p>") == "paragraphparagraph"

    # Test <br> tags
    assert (
        convert_html_to_md("<p>paragraph<br>paragraph</p>")
        == """paragraph
paragraph"""
    )

    # Test removing trailing newline
    assert convert_html_to_md("paragraph ") == "paragraph"

    # Test removing leading and trailing whitespace
    assert convert_html_to_md(" paragraph ") == "paragraph"

    # Test removing leading and trailing whitespace and trailing newline
    assert (
        convert_html_to_md(
            """ paragraph
                              
                                """  # noqa: W293
        )
        == "paragraph"
    )
