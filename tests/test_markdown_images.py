"""Markdown image reference parsing (inline, full/collapsed/shortcut reference) and article body checks."""

from __future__ import annotations

import pytest

from conftest import valid_article


def targets(vsum, text):
    return vsum.extract_local_image_targets(text)


def test_inline_images(vsum):
    text = "a\n\n![shot](images/a.png)\n\nb\n\n![titled](images/b.png \"the title\")\n"
    assert targets(vsum, text) == ["images/a.png", "images/b.png"]


def test_angle_bracket_path_with_spaces(vsum):
    assert targets(vsum, "![s](<images/my shot (1).png>)") == ["images/my shot (1).png"]


def test_quoted_path_with_spaces(vsum):
    assert targets(vsum, '![s]("images/my shot.png" title)') == ["images/my shot.png"]


def test_full_reference_image(vsum):
    text = "![流程图][figure]\n\n[figure]: images/flow.png\n"
    assert targets(vsum, text) == ["images/flow.png"]


def test_collapsed_reference_image(vsum):
    text = "![figure][]\n\n[figure]: images/flow.png\n"
    assert targets(vsum, text) == ["images/flow.png"]


def test_shortcut_reference_image(vsum):
    text = "![figure]\n\n[figure]: images/flow.png\n"
    assert targets(vsum, text) == ["images/flow.png"]


def test_unresolvable_reference_raises(vsum):
    """Regression: the exact shape from the review sample must fail loudly."""
    text = "![流程图][figure]\n"
    with pytest.raises(vsum.BriefError, match="figure"):
        targets(vsum, text)


def test_unresolvable_shortcut_raises(vsum):
    with pytest.raises(vsum.BriefError, match="definition"):
        targets(vsum, "![ghost]\n")


def test_unparseable_inline_raises(vsum):
    with pytest.raises(vsum.BriefError, match="cannot be resolved"):
        targets(vsum, "![s](images/unterminated.png")


def test_url_encoded_path_decoded(vsum):
    assert targets(vsum, "![s](images/my%20shot.png)") == ["images/my shot.png"]


def test_code_blocks_ignored(vsum):
    text = (
        "正文\n\n"
        "```markdown\n![示例](images/example.png)\n[示例]: images/from-code.png\n```\n\n"
        "行内代码 `![inline](images/code.png)` 之后继续。\n"
    )
    assert targets(vsum, text) == []


def test_remote_and_anchor_images_skipped(vsum):
    text = "![r](https://example.com/x.png) ![d](data:image/png;base64,AAAA) ![a](#anchor)\n"
    assert targets(vsum, text) == []


def test_mixed_inline_and_reference(vsum):
    text = "![a](images/a.png)\n\n![b][ref-b]\n\n[ref-b]: images/b.png\n"
    assert targets(vsum, text) == ["images/a.png", "images/b.png"]


# ---------------------------------------------------------------- body acceptance


def body_ok(vsum, text, packet_source=None):
    packet = {"source": packet_source if packet_source is not None else {
        "webpage_url": "https://example.com/watch?v=abc123",
        "uploader": "someone",
        "upload_date": "20260102",
    }}
    vsum.validate_article_against_packet(text, packet)


def test_valid_article_passes(vsum):
    body_ok(vsum, valid_article("这是一段实质正文，包含观点与例子。"))


def test_frontmatter_only_fails(vsum):
    with pytest.raises(vsum.BriefError, match="substantive"):
        body_ok(vsum, valid_article("# Test Video\n"))


def test_image_only_body_fails(vsum):
    with pytest.raises(vsum.BriefError, match="substantive"):
        body_ok(vsum, valid_article("![a](images/a.png)\n\n![b][ref]\n\n[ref]: images/b.png\n"))


def test_missing_frontmatter_fails(vsum):
    with pytest.raises(vsum.BriefError, match="frontmatter"):
        body_ok(vsum, "只有正文，没有 frontmatter。")


def test_missing_clippings_tag_fails(vsum):
    with pytest.raises(vsum.BriefError, match="clippings"):
        body_ok(vsum, valid_article("正文。").replace('  - "clippings"\n', ""))


def test_source_mismatch_fails(vsum):
    with pytest.raises(vsum.BriefError, match="does not match"):
        body_ok(vsum, valid_article("正文。", url="https://example.com/other"))


def test_missing_source_with_known_url_fails(vsum):
    text = valid_article("正文。").replace('source: "https://example.com/watch?v=abc123"', "source:")
    with pytest.raises(vsum.BriefError, match="no source"):
        body_ok(vsum, text)


def test_blank_source_allowed_without_known_url(vsum):
    text = valid_article("正文。").replace('source: "https://example.com/watch?v=abc123"', "source:")
    body_ok(vsum, text, packet_source={"title": "Local Only"})


def test_wrong_published_date_fails(vsum):
    text = valid_article("正文。").replace('published: "2026-01-02"', 'published: "1999-01-01"')
    with pytest.raises(vsum.BriefError, match="upload date"):
        body_ok(vsum, text)


def test_author_mismatch_fails(vsum):
    text = valid_article("正文。").replace('  - "someone"', '  - "someone-else"')
    with pytest.raises(vsum.BriefError, match="uploader"):
        body_ok(vsum, text)


def test_author_list_missing_uploader_allowed_when_absent(vsum):
    text = valid_article("正文。").replace('author:\n  - "someone"\n', "author:\n")
    body_ok(vsum, text, packet_source={"webpage_url": "https://example.com/watch?v=abc123"})
