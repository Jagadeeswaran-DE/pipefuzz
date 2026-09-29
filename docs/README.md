# Documentation website

The public site explains PipeFuzz v0.1.0. The package repository remains private;
the separate `Jagadeeswaran-DE/pipefuzz-docs` repository contains only rendered
documentation, CSS, JavaScript, a favicon, and the license.

## Build and preview

No documentation framework, Node package, Spark process, or network call is needed
to build the site. Use Python 3.10 or later:

```text
python docs/build.py
python -m http.server 8765 --bind 127.0.0.1 --directory _site
```

Open `http://127.0.0.1:8765`. Generated output goes to ignored `_site/`.
The builder checks all local links and fragments and rejects unresolved examples.

Edit the article fragments in `docs/content/`, the shared layout in `docs/build.py`,
and styling/behavior in `docs/assets/`. Example placeholders embed the real join
source and YAML, so they do not silently diverge from the package examples.

```text
python -m pytest tests/unit/test_documentation.py
```

The complete reference YAML is validated with the actual PipeFuzz configuration
parser. Tests do not start Spark. A build alone does not validate browser layout.

## Publishing boundary

GitHub Pages serves the `main` branch root of the public documentation repository.
Pushing new rendered output there triggers its Pages deployment automatically.
The source package remains in the private `pipefuzz` repository. This separation
avoids requiring paid Pages support for the private repository.

For an update, rebuild and validate `_site`, then copy only its rendered files and
the Apache `LICENSE` into an existing checkout of `pipefuzz-docs`. Review its diff,
commit, and push `main`. Do not mirror the private repository, copy its `.git`
directory, or include runtimes, tests, build reports, or audit logs. The site
intentionally shows short illustrative examples, not the package implementation.

The public site's top-level GitHub and page-source links point to the docs-only
repository. Package-source and audit links can require access; the quickstart
states that the package checkout is private. No analytics or third-party assets
are loaded. Site publication does not publish a PyPI package or mark an alpha
release as production-ready.
