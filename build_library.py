"""Download Gutenberg UTF-8 texts and wrap them as reader pages."""
from __future__ import annotations

import html
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LIB = ROOT / "library"
UA = "Mozilla/5.0 (compatible; beacon-library/1.0; +https://github.com/gazetheeupon/beacon)"

BOOKS = [
    {
        "slug": "constitution",
        "title": "Constitution of the United States",
        "author": "1787",
        "url": "https://www.gutenberg.org/files/5/5-0.txt",
    },
    {
        "slug": "declaration",
        "title": "Declaration of Independence",
        "author": "1776",
        "url": "https://www.gutenberg.org/files/1/1-0.txt",
    },
    {
        "slug": "pride-and-prejudice",
        "title": "Pride and Prejudice",
        "author": "Jane Austen",
        "url": "https://www.gutenberg.org/files/1342/1342-0.txt",
    },
    {
        "slug": "frankenstein",
        "title": "Frankenstein",
        "author": "Mary Shelley",
        "url": "https://www.gutenberg.org/files/84/84-0.txt",
    },
    {
        "slug": "alice",
        "title": "Alice’s Adventures in Wonderland",
        "author": "Lewis Carroll",
        "url": "https://www.gutenberg.org/files/11/11-0.txt",
    },
    {
        "slug": "art-of-war",
        "title": "The Art of War",
        "author": "Sunzi, tr. Lionel Giles",
        "url": "https://www.gutenberg.org/files/132/132-0.txt",
    },
    {
        "slug": "the-raven",
        "title": "The Raven",
        "author": "Edgar Allan Poe",
        "url": "https://www.gutenberg.org/files/1065/1065-0.txt",
    },
]


TEMPLATE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} · BEACON library</title>
  <meta name="description" content="Public-domain text: {title} by {author}.">
  <link rel="stylesheet" href="../styles.css">
</head>
<body class="reader">
  <div class="wrap">
    <header class="top">
      <a class="mark" href="../">BEACON</a>
      <nav>
        <a href="./">Library</a>
        <a href="../pulse/">Pulse</a>
        <a href="../pay/">Pay</a>
      </nav>
    </header>
    <p class="gutenberg-note">Public domain · {author} · if this page is useful, Lightning <code>streamqa@coinos.io</code></p>
    <h1>{title}</h1>
    <div class="paybar">
      Lightning <code>streamqa@coinos.io</code>
      · USDC Base <code>0x1e59553f1C9283CDE70e7d008602E24eac51E627</code>
      · <a href="../pay/">pay page</a>
    </div>
    <article>
      <pre class="raw">{body}</pre>
    </article>
    <footer>Source: Project Gutenberg. Header inside the text is their license, kept intact.</footer>
  </div>
</body>
</html>
"""


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read()
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def main() -> None:
    LIB.mkdir(exist_ok=True)
    for book in BOOKS:
        dest = LIB / f"{book['slug']}.html"
        print("fetch", book["title"], flush=True)
        try:
            text = fetch(book["url"])
        except Exception as e:
            print("  FAIL", e, flush=True)
            if dest.exists():
                continue
            text = f"(download failed: {e})\nSource: {book['url']}\n"
        page = TEMPLATE.format(
            title=html.escape(book["title"]),
            author=html.escape(book["author"]),
            body=html.escape(text),
        )
        dest.write_text(page, encoding="utf-8")
        print("  wrote", dest.name, "chars", len(text), flush=True)


if __name__ == "__main__":
    main()
