"""Keep the public reference buildable, linked, and in sync with real examples."""

from html import escape
from html.parser import HTMLParser
from pathlib import Path
import runpy

import pytest

from pipefuzz.config import load_config


ROOT = Path(__file__).resolve().parents[2]
BUILDER = runpy.run_path(str(ROOT / "docs" / "build.py"))


def test_documentation_build_contains_only_public_site_files(tmp_path):
    BUILDER["build"](tmp_path)
    expected = {f"{page[0]}.html" for page in BUILDER["PAGES"]}
    assert {item.name for item in tmp_path.iterdir()} == expected | {"assets", ".nojekyll"}
    assert {path.name for path in (tmp_path / "assets").iterdir()} == {
        "favicon.svg", "site.js", "style.css"
    }
    for filename in expected:
        content = (tmp_path / filename).read_text(encoding="utf-8")
        assert content.count("<h1>") == 1
        assert 'lang="en"' in content
        assert 'aria-current="page"' in content


def test_documentation_embeds_actual_example_sources(tmp_path):
    BUILDER["build"](tmp_path)
    content = (tmp_path / "examples.html").read_text(encoding="utf-8")
    for filename in (
        "examples/broken_join/pipeline.py",
        "examples/safe_join/pipeline.py",
        "examples/broken_join/pipefuzz.yaml",
    ):
        assert escape((ROOT / filename).read_text(encoding="utf-8").strip()) in content


class ConfigurationCode(HTMLParser):
    def __init__(self):
        super().__init__()
        self.active = False
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "code" and dict(attrs).get("id") == "complete-configuration":
            self.active = True

    def handle_endtag(self, tag):
        if tag == "code":
            self.active = False

    def handle_data(self, data):
        if self.active:
            self.parts.append(data)


def test_documented_complete_configuration_is_valid(tmp_path):
    parser = ConfigurationCode()
    parser.feed((ROOT / "docs/content/configuration.html").read_text(encoding="utf-8"))
    config_path = tmp_path / "pipefuzz.yaml"
    config_path.write_text("".join(parser.parts), encoding="utf-8")
    config = load_config(config_path)
    assert len(config.scenarios) == 5
    assert len(config.invariants) == 4


def test_documentation_validator_rejects_broken_links(tmp_path):
    (tmp_path / "index.html").write_text('<a href="missing.html">Missing</a>', encoding="utf-8")
    with pytest.raises(ValueError, match="Broken local link"):
        BUILDER["validate_site"](tmp_path)


def test_documentation_validator_rejects_missing_fragments(tmp_path):
    (tmp_path / "index.html").write_text('<a href="#missing">Missing</a>', encoding="utf-8")
    with pytest.raises(ValueError, match="Broken anchor"):
        BUILDER["validate_site"](tmp_path)
