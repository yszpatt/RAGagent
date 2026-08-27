from docx import Document as DocxDocument
from app.ingestion.parsers.base import Page


def parse_docx(path: str) -> list[Page]:
    doc = DocxDocument(path)
    text = "\n".join(p.text for p in doc.paragraphs)
    return [Page(page_number=1, text=text)]
