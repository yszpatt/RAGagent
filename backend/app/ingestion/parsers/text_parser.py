from pathlib import Path
from app.ingestion.parsers.base import Page


def parse_text(path: str) -> list[Page]:
    text = Path(path).read_text(encoding="utf-8")
    return [Page(page_number=1, text=text)]
