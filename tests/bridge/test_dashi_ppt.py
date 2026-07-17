"""Tests for DashiPPTBridge."""

from __future__ import annotations

from pathlib import Path

import pytest

from anappt.bridge.dashi_ppt import DashiPPTBridge, SlideContent


@pytest.fixture
def bridge(tmp_path: Path) -> DashiPPTBridge:
    """Return a DashiPPTBridge with temp output dir."""
    return DashiPPTBridge(output_dir=tmp_path, theme="default")


@pytest.fixture
def sample_markdown() -> str:
    """Return sample markdown for testing."""
    return """# Executive Summary

This is the executive summary of the analysis.

## Key Findings

- Finding 1: Revenue grew 20%
- Finding 2: Customer retention improved
- Finding 3: Market share increased

## Methodology

We used statistical analysis and machine learning.

## Conclusions

The analysis shows positive trends across all metrics.
"""


class TestListThemes:
    """Tests for list_themes static method."""

    def test_returns_dict(self) -> None:
        themes = DashiPPTBridge.list_themes()
        assert isinstance(themes, dict)
        assert len(themes) > 0

    def test_has_default_theme(self) -> None:
        themes = DashiPPTBridge.list_themes()
        assert "default" in themes

    def test_has_multiple_themes(self) -> None:
        themes = DashiPPTBridge.list_themes()
        assert len(themes) >= 3

    def test_returns_copy(self) -> None:
        themes1 = DashiPPTBridge.list_themes()
        themes2 = DashiPPTBridge.list_themes()
        assert themes1 == themes2
        themes1["new"] = "test"
        assert "new" not in DashiPPTBridge.list_themes()


class TestValidateMarkdown:
    """Tests for validate_markdown static method."""

    def test_valid_with_h1(self) -> None:
        assert DashiPPTBridge.validate_markdown("# Title\n\nContent") is True

    def test_valid_with_h2(self) -> None:
        assert DashiPPTBridge.validate_markdown("## Section\n\nContent") is True

    def test_valid_with_h3(self) -> None:
        assert DashiPPTBridge.validate_markdown("### Subsection\n\nContent") is True

    def test_empty_content(self) -> None:
        assert DashiPPTBridge.validate_markdown("") is False

    def test_whitespace_only(self) -> None:
        assert DashiPPTBridge.validate_markdown("   \n  \n") is False

    def test_no_headings(self) -> None:
        assert DashiPPTBridge.validate_markdown("Just plain text without headings") is False

    def test_valid_complex_markdown(self, sample_markdown: str) -> None:
        assert DashiPPTBridge.validate_markdown(sample_markdown) is True


class TestParseMarkdownToSlides:
    """Tests for parse_markdown_to_slides method."""

    def test_single_slide(self, bridge: DashiPPTBridge) -> None:
        slides = bridge.parse_markdown_to_slides("# Title\n\nContent")
        assert len(slides) == 1
        assert slides[0].title == "Title"

    def test_multiple_slides(self, bridge: DashiPPTBridge, sample_markdown: str) -> None:
        slides = bridge.parse_markdown_to_slides(sample_markdown)
        assert len(slides) == 4
        assert slides[0].title == "Executive Summary"
        assert slides[1].title == "Key Findings"

    def test_bullets_parsed(self, bridge: DashiPPTBridge) -> None:
        md = "# Title\n\n- Bullet 1\n- Bullet 2\n- Bullet 3"
        slides = bridge.parse_markdown_to_slides(md)
        assert len(slides) == 1
        assert len(slides[0].bullets) == 3
        assert slides[0].bullets[0] == "Bullet 1"

    def test_content_parsed(self, bridge: DashiPPTBridge) -> None:
        md = "# Title\n\nThis is some content.\nMore content here."
        slides = bridge.parse_markdown_to_slides(md)
        assert len(slides) == 1
        assert "This is some content" in slides[0].content

    def test_h2_starts_new_slide(self, bridge: DashiPPTBridge) -> None:
        md = "# Slide 1\n\nContent 1\n\n# Slide 2\n\nContent 2"
        slides = bridge.parse_markdown_to_slides(md)
        assert len(slides) == 2
        assert slides[0].title == "Slide 1"
        assert slides[1].title == "Slide 2"

    def test_star_bullets(self, bridge: DashiPPTBridge) -> None:
        md = "# Title\n\n* Item 1\n* Item 2"
        slides = bridge.parse_markdown_to_slides(md)
        assert len(slides[0].bullets) == 2

    def test_empty_markdown(self, bridge: DashiPPTBridge) -> None:
        slides = bridge.parse_markdown_to_slides("")
        assert slides == []

    def test_title_only_slide(self, bridge: DashiPPTBridge) -> None:
        slides = bridge.parse_markdown_to_slides("# Just a title")
        assert len(slides) == 1
        assert slides[0].title == "Just a title"
        assert slides[0].bullets == []
        assert slides[0].content == ""


class TestGenerateHTML:
    """Tests for generate_html method."""

    def test_returns_html_string(self, bridge: DashiPPTBridge) -> None:
        slides = [SlideContent(title="Test", bullets=["A", "B"])]
        html = bridge.generate_html(slides)
        assert isinstance(html, str)
        assert "<!DOCTYPE html>" in html
        assert "</html>" in html

    def test_contains_slide_titles(self, bridge: DashiPPTBridge) -> None:
        slides = [SlideContent(title="My Title")]
        html = bridge.generate_html(slides)
        assert "My Title" in html

    def test_contains_bullets(self, bridge: DashiPPTBridge) -> None:
        slides = [SlideContent(title="Test", bullets=["Bullet One"])]
        html = bridge.generate_html(slides)
        assert "Bullet One" in html

    def test_contains_navigation(self, bridge: DashiPPTBridge) -> None:
        slides = [SlideContent(title="Test")]
        html = bridge.generate_html(slides)
        assert "next()" in html
        assert "prev()" in html

    def test_contains_counter(self, bridge: DashiPPTBridge) -> None:
        slides = [SlideContent(title="A"), SlideContent(title="B")]
        html = bridge.generate_html(slides)
        assert 'id="total"' in html
        assert 'id="current"' in html

    def test_first_slide_active(self, bridge: DashiPPTBridge) -> None:
        slides = [SlideContent(title="A"), SlideContent(title="B")]
        html = bridge.generate_html(slides)
        assert "active" in html

    def test_title_in_html_head(self, bridge: DashiPPTBridge) -> None:
        slides = [SlideContent(title="Test")]
        html = bridge.generate_html(slides, title="My Presentation")
        assert "<title>My Presentation</title>" in html


class TestGeneratePPT:
    """Tests for generate_ppt method."""

    def test_generates_html_file(
        self, bridge: DashiPPTBridge, sample_markdown: str, tmp_path: Path
    ) -> None:
        result = bridge.generate_ppt(sample_markdown, filename="test.html")
        assert result.exists()
        assert result.suffix == ".html"
        content = result.read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content

    def test_invalid_markdown_raises(self, bridge: DashiPPTBridge) -> None:
        with pytest.raises(ValueError, match="invalid"):
            bridge.generate_ppt("No headings here")

    def test_empty_content_raises(self, bridge: DashiPPTBridge) -> None:
        with pytest.raises(ValueError):
            bridge.generate_ppt("")

    def test_creates_output_dir(self, tmp_path: Path, sample_markdown: str) -> None:
        output_dir = tmp_path / "new_dir" / "ppt"
        bridge = DashiPPTBridge(output_dir=output_dir)
        bridge.generate_ppt(sample_markdown, filename="test.html")
        assert output_dir.exists()

    def test_theme_override(self, tmp_path: Path, sample_markdown: str) -> None:
        bridge = DashiPPTBridge(output_dir=tmp_path, theme="default")
        bridge.generate_ppt(sample_markdown, theme="dark", filename="test.html")
        assert bridge.theme == "dark"

    def test_invalid_theme_falls_back(self, tmp_path: Path, sample_markdown: str) -> None:
        bridge = DashiPPTBridge(output_dir=tmp_path)
        bridge.generate_ppt(sample_markdown, theme="nonexistent", filename="test.html")
        assert bridge.theme == "default"


class TestSlideContent:
    """Tests for SlideContent class."""

    def test_defaults(self) -> None:
        sc = SlideContent()
        assert sc.title == ""
        assert sc.bullets == []
        assert sc.content == ""
        assert sc.image_path == ""
        assert sc.layout == "content"

    def test_with_values(self) -> None:
        sc = SlideContent(
            title="Test",
            bullets=["A", "B"],
            content="Body text",
            image_path="/img/a.png",
            layout="image",
        )
        assert sc.title == "Test"
        assert sc.bullets == ["A", "B"]
        assert sc.content == "Body text"
        assert sc.image_path == "/img/a.png"
        assert sc.layout == "image"
