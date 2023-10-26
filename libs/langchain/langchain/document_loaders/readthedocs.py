import re
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple, Union

from langchain.docstore.document import Document
from langchain.document_loaders.base import BaseLoader


class ReadTheDocsLoader(BaseLoader):
    """Load `ReadTheDocs` documentation directory."""

    def __init__(
        self,
        path: Union[str, Path],
        encoding: Optional[str] = None,
        errors: Optional[str] = None,
        custom_html_tag: Optional[Tuple[str, dict]] = None,
        patterns: Sequence[str] = ("*.htm", "*.html"),
        exclude_index_pages: bool = False,
        **kwargs: Optional[Any]
    ):
        """
        Initialize ReadTheDocsLoader

        The loader loops over all files under `path` and extracts the actual content of
        the files by retrieving main html tags. Default main html tags include
        `<main id="main-content>`, <`div role="main>`, and `<article role="main">`. You
        can also define your own html tags by passing custom_html_tag, e.g.
        `("div", "class=main")`. The loader iterates html tags with the order of
        custom html tags (if exists) and default html tags. If any of the tags is not
        empty, the loop will break and retrieve the content out of that tag.

        Args:
            path: The location of pulled readthedocs folder.
            encoding: The encoding with which to open the documents.
            errors: Specify how encoding and decoding errors are to be handled—this
                cannot be used in binary mode.
            custom_html_tag: Optional custom html tag to retrieve the content from
                files.
            patterns: The file patterns to load, passed to `glob.rglob`.
            exclude_index_pages: Exclude index pages with high link ratios (>50%).
                This is to reduce the frequency at which index pages make their
                way into retrieved results.
            kwargs: named arguments passed to `bs4.BeautifulSoup`.
        """
        try:
            from bs4 import BeautifulSoup
        except ImportError:
            raise ImportError(
                "Could not import python packages. "
                "Please install it with `pip install beautifulsoup4`. "
            )

        try:
            _ = BeautifulSoup(
                "<html><body>Parser builder library test.</body></html>", **kwargs
            )
        except Exception as e:
            raise ValueError("Parsing kwargs do not appear valid") from e

        self.file_path = Path(path)
        self.encoding = encoding
        self.errors = errors
        self.custom_html_tag = custom_html_tag
        self.patterns = patterns
        self.bs_kwargs = kwargs
        self.exclude_index_pages = exclude_index_pages

    def load(self) -> List[Document]:
        """Load documents."""
        docs = []
        for file_pattern in self.patterns:
            for p in self.file_path.rglob(file_pattern):
                if p.is_dir():
                    continue
                with open(p, encoding=self.encoding, errors=self.errors) as f:
                    text = self._clean_data(f.read())
                metadata = {"source": str(p)}
                docs.append(Document(page_content=text, metadata=metadata))
        return docs

    def _get_link_ratio(self, section):
        links = section.find_all("a")
        total_text = "".join(str(s) for s in section.stripped_strings)
        if len(total_text) == 0:
            return 0

        link_text = "".join(
            str(string.string.strip())
            for link in links
            for string in link.strings
            if string
        )
        return len(link_text) / len(total_text)

    def _get_clean_text(self, element):
        """Recursive text getter that excludes code and binary content and preserves newline data from the html."""
        from bs4 import NavigableString
        from bs4.element import Comment

        elements_to_skip = [
            "script",
            "noscript",
            "canvas",
            "meta",
            "svg",
            "map",
            "area",
            "audio",
            "source",
            "track",
            "video",
            "embed",
            "object",
            "param",
            "picture",
            "iframe",
            "frame",
            "frameset",
            "noframes",
            "applet",
            "form",
            "button",
            "select",
            "base",
            "style",
            "img"
        ]

        newline_elements = [
            "p",
            "div",
            "ul",
            "ol",
            "li",
            "h1",
            "h2",
            "h3",
            "h4",
            "h5",
            "h6",
            "pre",
            "table",
            "tr"
        ]

        def process_element(el):
            """Traverse through HTML tree recursively to preserve newline and skip unwanted (code/binary) elements"""
            tag_name = getattr(el, "name", None)
            if isinstance(el, Comment) or tag_name in elements_to_skip:
                return ""
            elif isinstance(el, NavigableString):
                return el
            elif tag_name == "br":
                return "\n"
            elif tag_name in newline_elements:
                return "".join(process_element(child) for child in el.children) + "\n"
            else:
                return "".join(process_element(child) for child in el.children)

        text = process_element(element)
        return text

    def _clean_data(self, data: str) -> str:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(data, **self.bs_kwargs)

        # default tags
        html_tags = [
            ("div", {"role": "main"}),
            ("main", {"id": "main-content"}),
        ]

        if self.custom_html_tag is not None:
            html_tags.append(self.custom_html_tag)

        text = None

        # reversed order. check the custom one first
        for tag, attrs in html_tags[::-1]:
            text = soup.find(tag, attrs)
            # if found, break
            if text is not None:
                break

        if (
            text is not None
            and not (self.exclude_index_pages and self._get_link_ratio(text) >= 0.5)
        ):
            text = self._get_clean_text(text)
        else:
            text = ""
        # trim empty lines
        return "\n".join([t for t in text.split("\n") if t])
