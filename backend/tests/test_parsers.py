from pathlib import Path
import pytest
from app.ingestion.parsers.registry import parse


def test_parse_txt_returns_paragraphs(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("第一段内容。\n\n第二段内容。", encoding="utf-8")
    pages = parse(str(f))
    assert len(pages) == 1
    assert "第一段内容" in pages[0].text
    assert pages[0].page_number == 1


def test_parse_md_supported(tmp_path):
    f = tmp_path / "doc.md"
    f.write_text("# 标题\n正文内容", encoding="utf-8")
    pages = parse(str(f))
    assert len(pages) == 1
    assert "标题" in pages[0].text


def test_parse_unsupported_extension_raises(tmp_path):
    f = tmp_path / "test.xyz"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError):
        parse(str(f))


def test_parse_pdf_multipage(tmp_path):
    import io
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    # 默认 Helvetica 是标准 14 字体，不含 CJK 字形映射，pypdf 提取中文会得到占位符，
    # 故使用 CID 字体（STSong-Light）生成可提取中文的多页 PDF。
    pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer)
    c.setFont("STSong-Light", 16)
    c.drawString(100, 750, "第一页内容")
    c.showPage()
    c.setFont("STSong-Light", 16)
    c.drawString(100, 750, "第二页内容")
    c.save()
    buffer.seek(0)

    f = tmp_path / "test.pdf"
    f.write_bytes(buffer.getvalue())
    pages = parse(str(f))
    assert len(pages) == 2
    assert "第一页内容" in pages[0].text
    assert pages[0].page_number == 1
    assert pages[1].page_number == 2
