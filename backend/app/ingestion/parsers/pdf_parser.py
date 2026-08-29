import logging
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader

from app.core.config import settings
from app.ingestion.parsers.base import Page

logger = logging.getLogger(__name__)

# 单页有效字符低于该值视为「无文本层」（扫描页/空白页），交给 OCR 兜底。
# 正常文本页远高于此；空白分隔页 OCR 也很快，不会拖慢整体。
_EMPTY_PAGE_CHARS = 10

# RapidOCR 单例：模型加载约 1-2s，一本书只应加载一次
_ocr_engine = None


def _get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        # 惰性导入：未安装 rapidocr-onnxruntime 时不影响纯文本 PDF 的解析
        from rapidocr_onnxruntime import RapidOCR

        _ocr_engine = RapidOCR()
    return _ocr_engine


def _ocr_page(pdf_path: str, page_number: int, dpi: int, tmp_dir: str) -> str:
    """栅格化单页并 OCR，返回按阅读顺序拼接的行文本。

    pdftoppm(poppler) 负责渲染，RapidOCR(onnxruntime, CPU) 负责识别，
    两者都不依赖 GPU。识别行按检测框顶部 y 坐标排序，适配单栏书籍版面。
    """
    ocr = _get_ocr_engine()
    prefix = str(Path(tmp_dir) / f"p{page_number}")
    subprocess.run(
        ["pdftoppm", "-f", str(page_number), "-l", str(page_number),
         "-r", str(dpi), "-png", "-singlefile", pdf_path, prefix],
        check=True, timeout=120, capture_output=True,
    )
    img = prefix + ".png"
    try:
        result, _ = ocr(img)
    finally:
        Path(img).unlink(missing_ok=True)
    rows = [r for r in (result or []) if len(r) >= 2 and r[1]]
    rows.sort(key=lambda r: min(p[1] for p in r[0]))
    return "\n".join(str(r[1]) for r in rows)


def parse_pdf(path: str) -> list[Page]:
    reader = PdfReader(path)
    pages = [Page(page_number=i + 1, text=p.extract_text() or "")
             for i, p in enumerate(reader.pages)]

    # OCR 兜底：只对提不出文本的页做栅格化 + 识别。
    # 纯文本 PDF 一个空页都没有 → 零 OCR 开销；
    # 纯扫描书 → 全部页 OCR；混合 PDF（正文文本 + 附录扫描）→ 只补扫描页。
    if not settings.ocr_enabled:
        return pages
    empty = [pg.page_number for pg in pages if len(pg.text.strip()) < _EMPTY_PAGE_CHARS]
    if not empty:
        return pages

    logger.info("PDF %s: %d/%d 页无文本层，启用 OCR 兜底（dpi=%d）",
                Path(path).name, len(empty), len(pages), settings.ocr_dpi)
    with tempfile.TemporaryDirectory(prefix="kp_ocr_") as tmp:
        for done, n in enumerate(empty, start=1):
            try:
                pages[n - 1].text = _ocr_page(path, n, settings.ocr_dpi, tmp)
            except Exception as e:  # noqa: BLE001 单页失败不中断整本
                logger.warning("OCR 第 %d 页失败: %s", n, e)
            if done % 20 == 0 or done == len(empty):
                logger.info("OCR 进度 %d/%d", done, len(empty))
    return pages
