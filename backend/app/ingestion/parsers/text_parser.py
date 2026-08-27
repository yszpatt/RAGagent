from pathlib import Path
from app.ingestion.parsers.base import Page


def parse_text(path: str) -> list[Page]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise ValueError(f"file is not valid UTF-8 text: {path}")
    return [Page(page_number=1, text=text)]
