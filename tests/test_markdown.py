from discord_rss_bot.markdown import convert_html_to_md


def test_convert_to_md() -> None:
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
            '<b>bold</b> <i>italic</i> <a href="https://example.com">link</a> <code>code</code> <s>strikethrough</s>',
        )
        == "**bold** *italic* [link](https://example.com) `code` ~~strikethrough~~"
    )

    # Test removing all other tags
    assert convert_html_to_md("<p>paragraph</p>") == "paragraph"
    assert convert_html_to_md("<p>paragraph</p><p>paragraph</p>") == "paragraph\nparagraph"

    # Test <br> tags
    assert convert_html_to_md("<p>paragraph<br>paragraph</p>") == "paragraph\nparagraph"

    # Test removing trailing newline
    assert convert_html_to_md("paragraph ") == "paragraph"

    # Test removing leading and trailing whitespace
    assert convert_html_to_md(" paragraph ") == "paragraph"

    # Test removing leading and trailing whitespace and trailing newline
    assert convert_html_to_md(" paragraph\n \n") == "paragraph"

    # Test real entry
    nvidia_entry: str = (
        '<p><a href="https://www.nvidia.com/en-us/geforce/news/jan-2023-nvidia-broadcast-update/">'
        "NVIDIA Broadcast 1.4 Adds Eye Contact and Vignette Effects With Virtual Background Enhancements</a></p>"
        '<div class="field field-name-field-short-description field-type-text-long field-label-hidden">'
        '<div class="field-items"><div class="field-item even">Plus new options to mirror your camera and take a selfie.</div>'  # noqa: E501
        '</div></div><div class="field field-name-field-thumbnail-image field-type-image field-label-hidden">'
        '<div class="field-items"><div class="field-item even"><a href="https://www.nvidia.com/en-us/geforce/news/jan-2023-nvidia-broadcast-update/">'
        '<img width="210" src="https://www.nvidia.com/content/dam/en-zz/Solutions/geforce/news/jan-2023-nvidia-broadcast-update/broadcast-owned-asset-625x330-newsfeed.png"'
        ' title="NVIDIA Broadcast 1.4 Adds Eye Contact and Vignette Effects With Virtual Background Enhancements" '
        'alt="NVIDIA Broadcast 1.4 Adds Eye Contact and Vignette Effects With Virtual Background Enhancements"></a></div></div></div>'  # noqa: E501
    )
    assert (
        convert_html_to_md(nvidia_entry)
        == "[NVIDIA Broadcast 1.4 Adds Eye Contact and Vignette Effects With Virtual Background Enhancements](https://www.nvidia.com/en-us/geforce/news/jan-2023-nvidia-broadcast-update/)\n"
        "Plus new options to mirror your camera and take a selfie."
    )
