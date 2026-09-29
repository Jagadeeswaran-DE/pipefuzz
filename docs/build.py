"""Build the documentation with Python's standard library; no Spark required."""

from __future__ import annotations

import argparse
from html import escape
from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
from urllib.parse import unquote, urlsplit


ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
REPOSITORY = "https://github.com/Jagadeeswaran-DE/pipefuzz"
DOCS_REPOSITORY = "https://github.com/Jagadeeswaran-DE/pipefuzz-docs"
PAGES = (
    ("index", "Introduction", "Start here", "Understand PipeFuzz", "Learn how PipeFuzz tests PySpark transformations using generated data and explicit invariants."),
    ("quickstart", "Quick start", "Start here", "Your first PipeFuzz run", "Install PipeFuzz from source and run the broken and safe join examples."),
    ("examples", "Join walkthrough", "Start here", "One join. Two very different results.", "See how duplicate dimension keys amplify measures, and how the safe example prevents it."),
    ("configuration", "Configuration", "Reference", "Describe the data. Define the contract.", "The complete PipeFuzz YAML v1 schema and relationship reference."),
    ("checks", "Scenarios & invariants", "Reference", "Choose what to challenge and what to check", "Understand every adversarial scenario and invariant in PipeFuzz v0.1."),
    ("cli", "CLI & troubleshooting", "Reference", "Run, diagnose, reproduce", "Commands, flags, exit codes, reproducibility, and troubleshooting for PipeFuzz."),
    ("architecture", "Architecture & limits", "Under the hood", "What happens inside a run", "The local Spark execution lifecycle, source map, security boundaries, and v0.1 limitations."),
)


class Document(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = set()
        self.links = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if "id" in attributes:
            if attributes["id"] in self.ids:
                raise ValueError(f"Duplicate HTML id: {attributes['id']}")
            self.ids.add(attributes["id"])
        for attribute in ("href", "src"):
            if attribute in attributes:
                self.links.append(attributes[attribute])


def validate_site(output: Path) -> None:
    """Check every generated local link, fragment, and asset, including subpath use."""
    documents = {}
    for path in output.glob("*.html"):
        document = Document()
        text = path.read_text(encoding="utf-8")
        if "{{" in text or "}}" in text:
            raise ValueError(f"Unresolved content placeholder in {path.name}")
        document.feed(text)
        documents[path.resolve()] = document
    for path, document in documents.items():
        for link in document.links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            if parsed.path.startswith("/"):
                raise ValueError(f"Root-relative link breaks project Pages: {link}")
            target = (path.parent / unquote(parsed.path)).resolve() if parsed.path else path
            if not target.is_relative_to(output.resolve()) or not target.is_file():
                raise ValueError(f"Broken local link in {path.name}: {link}")
            if parsed.fragment and target in documents:
                if unquote(parsed.fragment) not in documents[target].ids:
                    raise ValueError(f"Broken anchor in {path.name}: {link}")


def render(slug: str, title: str, group: str, heading: str, description: str) -> str:
    content = (DOCS / "content" / f"{slug}.html").read_text(encoding="utf-8")
    examples = {
        "broken_pipeline": "examples/broken_join/pipeline.py",
        "safe_pipeline": "examples/safe_join/pipeline.py",
        "example_config": "examples/broken_join/pipefuzz.yaml",
    }
    for key, path in examples.items():
        content = content.replace("{{" + key + "}}", escape((ROOT / path).read_text(encoding="utf-8").strip()))
    navigation = []
    current_group = None
    for page_slug, page_title, page_group, *_ in PAGES:
        if page_group != current_group:
            navigation.append(f'<p class="nav-label">{escape(page_group)}</p>')
            current_group = page_group
        current = ' aria-current="page"' if page_slug == slug else ""
        navigation.append(f'<a href="{page_slug}.html"{current}>{escape(page_title)}</a>')
    toc = "".join(
        f'<a href="#{identifier}">{re.sub("<[^>]+>", "", text)}</a>'
        for identifier, text in re.findall(r'<h2 id="([^"]+)">(.*?)</h2>', content)
    )
    index = [page[0] for page in PAGES].index(slug)
    previous_link = ""
    next_link = ""
    if index:
        previous = PAGES[index - 1]
        previous_link = f'<a href="{previous[0]}.html"><span>Previous</span>{previous[1]}</a>'
    if index < len(PAGES) - 1:
        following = PAGES[index + 1]
        next_link = f'<a class="next" href="{following[0]}.html"><span>Next</span>{following[1]}</a>'
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(description, quote=True)}">
  <meta name="color-scheme" content="light">
  <title>{escape(title)} · PipeFuzz documentation</title>
  <link rel="icon" type="image/svg+xml" href="assets/favicon.svg">
  <link rel="stylesheet" href="assets/style.css">
  <script src="assets/site.js" defer></script>
</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="topbar">
  <a class="brand" href="index.html"><span class="brand-mark" aria-hidden="true">pf</span>PipeFuzz<span class="brand-divider">/</span><span class="brand-docs">Docs</span></a>
  <div class="header-links"><span class="version">v0.1.0 <span>alpha</span></span><a href="{DOCS_REPOSITORY}">GitHub <span aria-hidden="true">↗</span></a><button class="menu-button" aria-expanded="false" aria-controls="sidebar">Menu</button></div>
</header>
<div class="layout">
  <aside class="sidebar" id="sidebar"><nav aria-label="Documentation">{''.join(navigation)}</nav><div class="sidebar-note"><span class="eyebrow">The v0.1 boundary</span><p>Real PySpark.<br>Small generated inputs.<br>Local execution.</p><a href="architecture.html#limitations">Know the limits</a></div></aside>
  <main id="main" tabindex="-1">
    <div class="breadcrumb">Documentation <span>/</span> {escape(group)}</div>
    <article><h1>{escape(heading)}</h1>{content}</article>
    <nav class="page-turn" aria-label="Previous and next pages">{previous_link}{next_link}</nav>
    <footer>PipeFuzz v0.1.0 · Apache-2.0 <span>Local testing. Explicit properties.</span><a href="{DOCS_REPOSITORY}/blob/main/{slug}.html">Page source</a></footer>
  </main>
  <aside class="toc" aria-label="On this page"><p>On this page</p>{toc}<a class="back-top" href="#main">Back to top</a></aside>
</div>
<div class="copy-status" role="status" aria-live="polite"></div>
</body>
</html>
'''


def build(output: Path) -> None:
    output = output.resolve()
    if output == ROOT or output == DOCS or output in ROOT.parents:
        raise ValueError("Choose a dedicated output directory, not the source directory")
    output.mkdir(parents=True, exist_ok=True)
    for page in PAGES:
        (output / f"{page[0]}.html").write_text(render(*page), encoding="utf-8")
    shutil.copytree(DOCS / "assets", output / "assets", dirs_exist_ok=True)
    (output / ".nojekyll").write_text("", encoding="utf-8")
    validate_site(output)
    print(f"Built and validated {len(PAGES)} documentation pages in {output}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "_site")
    args = parser.parse_args()
    build(args.output)
