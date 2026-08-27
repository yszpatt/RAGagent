from pypdf import PdfReader
from app.ingestion.parsers.base import Page


def parse_pdf(path: str) -> list[Page]:
    reader = PdfReader(path)
    return [Page(page_number=i + 1, text=p.extract_text() or "") for i, p in enumerate(reader.pages)]
