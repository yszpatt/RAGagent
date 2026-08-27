from pathlib import Path
from app.ingestion.parsers.base import Page

SUPPORTED = {".txt", ".md", ".pdf", ".docx"}


def parse(path: str) -> list[Page]:
    ext = Path(path).suffix.lower()
    if ext not in SUPPORTED:
        raise ValueError(f"unsupported extension: {ext}")
    if ext in {".txt", ".md"}:
        from app.ingestion.parsers.text_parser import parse_text
        return parse_text(path)
    if ext == ".pdf":
        from app.ingestion.parsers.pdf_parser import parse_pdf
        return parse_pdf(path)
    if ext == ".docx":
        from app.ingestion.parsers.docx_parser import parse_docx
        return parse_docx(path)
    raise ValueError(f"unsupported extension: {ext}")
