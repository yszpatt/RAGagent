"""中文条款感知切块（Clause-Aware Chunking）。

为什么不用通用递归切块
----------------------
实测（corpus: 技术服务合同 / 员工手册 / 财务制度 / 运维规范，chunk_size=500）：

  1. 整篇文档被塞进 1 个块。合同 477 字、财务 413 字、运维 388 字都小于
     chunk_size，于是「第一条 服务内容」到「第十二条 争议解决」共 8 个条款
     共处一块。后果是任意问题都命中同一块、拿到同一个分数 —— 实测域内查询
     top1-top2 相似度间隙中位数仅 0.0015，30 条里有 19 条 < 0.01，
     检索完全丧失区分度，「打官司去哪儿解决」的 top1 甚至落到了运维文档的
     服务器 IP 段落。
  2. 边界处硬切会切断词语。实测切出「司商业秘密，不得向第三方泄露…」，
     「员」字残留在上一块，既污染向量语义也污染引用展示。

核心主张
--------
中文企业文档的语义单元不是句子，而是**条款** —— 一条即一个自足的事实单元，
具备「主体 + 条件 + 后果」的完整结构。因此：

  * 条款/章节标题是一等切分边界，短条款原样成块，**不做跨条款切分**；
  * 只有单条本身超长时才回退到句子级递归切分，且切出的每个子块都带上标题前缀，
    保证子块自描述、可独立检索；
  * **重叠只在条款内部生效，绝不跨条款**。跨条款重叠会把上一条的语义带进下一条，
    恰好抵消掉按条切分换来的区分度。

标题回填：每块记录最近的祖先标题（写进 chunks.section_title），并拼在内容开头。
这让抽象提问（「打官司去哪儿解决」）能直接匹配到「第十二条 争议解决」，
而不仅依赖正文里「提交合同签署地人民法院诉讼解决」的字面重合。
"""

from __future__ import annotations

import re

# 条款/章节起始标记：第一条、第十二章、第一章、一、（一）、1.2、1、
# 匹配的是「行首」标记，正文中出现的编号（如 IP 10.20.31.47）不会误命中。
_CLAUSE_RE = re.compile(
    r"^\s*(?:"
    r"第\s*[一二三四五六七八九十百千零〇0-9]+\s*[条章节篇部]"      # 第一条 / 第 12 章
    r"|[一二三四五六七八九十]+\s*[、．]"                            # 一、/ 二．
    r"|[（(]\s*[一二三四五六七八九十0-9]+\s*[)）]"                  # （一）
    r"|[0-9]+(?:\.[0-9]+){1,3}\s*[、.．]?\s"                       # 1.2、/ 2.3.1
    r"|[0-9]+\s*[、．]"                                            # 1、/ 2．
    r")"
)

# Markdown 标题：# 一级 … ###### 六级
_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(\S.*?)\s*#*\s*$")

# 句子级分隔符（条款内部超长时的回退）。中文标点齐全，避免只在句号处切。
_SENTENCE_SEPS = ["\n\n", "\n", "。", "！", "？", "；", ". ", "，", "、", ",", " ", ""]


def _looks_like_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 60:
        return False
    if _HEADING_RE.match(stripped):
        return True
    return bool(_CLAUSE_RE.match(stripped))


def _clean_title(line: str) -> str:
    m = _HEADING_RE.match(line.strip())
    if m:
        return m.group(2).strip()
    return line.strip().rstrip("：:").strip()


def _split_sentences(text: str, chunk_size: int, overlap: int) -> list[str]:
    """把一个超长条款按句子级分隔符递归切到 chunk_size 以内。

    只在「单条超长」时被调用，因此 overlap 被限制在条款内部，不会跨条款污染。
    """
    overlap = min(overlap, max(0, chunk_size - 2))
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    for sep in _SENTENCE_SEPS:
        parts = text.split(sep) if sep else list(text)
        chunks: list[str] = []
        cur = ""
        for p in parts:
            piece = p + (sep if sep else "")
            if len(cur) + len(piece) > chunk_size and cur:
                chunks.append(cur.strip())
                cur = cur[-overlap:] if overlap else ""
            cur += piece
        if cur.strip():
            chunks.append(cur.strip())
        if len(chunks) > 1:
            # 仍有过长碎块则对碎块再切一层（分隔符层级已在循环内收敛到字符级）
            out: list[str] = []
            for c in chunks:
                if len(c) > chunk_size * 1.5:
                    out.extend(_split_sentences(c, chunk_size, overlap))
                else:
                    out.append(c)
            return out
    return [text]


def clause_aware_chunk(
    text: str,
    chunk_size: int = 500,
    overlap: int = 50,
    min_size: int = 80,
) -> list[dict]:
    """按条款结构切块。

    返回 [{"content": str, "section_title": str | None}, ...]。
    content 已包含标题前缀（提升语义匹配），section_title 供引用展示。

    min_size：过短的条款与相邻条款合并，避免产生「一句话块」导致上下文缺失。
    """
    if not text or not text.strip():
        return []

    lines = text.splitlines()
    doc_title: str | None = None
    sections: list[dict] = []   # {"title": str|None, "body": list[str]}
    current: dict | None = None

    def flush() -> None:
        nonlocal current
        if current is None:
            return
        body = "\n".join(current["body"]).strip()
        if body:
            sections.append({"title": current["title"], "body": body})
        current = None

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue
        if _looks_like_heading(line):
            flush()
            title = _clean_title(line)
            if doc_title is None:
                doc_title = title
            current = {"title": title, "body": []}
        else:
            if current is None:
                current = {"title": None, "body": []}
            current["body"].append(line.strip())
    flush()

    # 全文没有任何结构标记 → 退化为一节，交给句子级切分
    if not sections:
        sections = [{"title": None, "body": text.strip()}]

    # 合并规则：**条款块永不合并，只把无标题引导段并入其后的第一个条款块。**
    #
    # 早期实现按 min_size 链式合并短条款，结果合同里 8 个不足 80 字的条款
    # 被一路并回 1 个 467 字大块 —— 恰好抵消掉按条切分的全部收益。
    # 论依据：一条 = 一个自足的事实单元（主体+条件+后果），合并即损失区分度；
    # 而「技术服务合同」「甲方：…」这类引导段本身不构成事实单元，
    # 单独成块没有检索价值，只适合作为其后条款块的前缀上下文。
    merged: list[dict] = []
    pending_preamble: list[str] = []
    for sec in sections:
        if sec["title"] is None:
            # 长到足以自成一节的引导段（如无结构的长摘要）不并入，独立成块
            if len(sec["body"]) >= min_size:
                merged.append(sec)
            else:
                pending_preamble.append(sec["body"])
            continue
        if pending_preamble:
            # 标题由下面的组装步骤统一前置，此处不再重复插入，否则块内会出现两次标题。
            sec["body"] = "\n".join(pending_preamble + [sec["body"]])
            pending_preamble = []
        merged.append(sec)
    if pending_preamble:
        # 全文只有引导段（无任何条款结构）→ 原样成块
        body = "\n".join(pending_preamble)
        if merged:
            merged[-1]["body"] = f"{merged[-1]['body']}\n{body}"
        else:
            merged.append({"title": None, "body": body})

    # 长条款回退到句子级切分，每个子块保留标题前缀
    out: list[dict] = []
    for sec in merged:
        title = sec["title"]
        prefix = f"{title}\n" if title else ""
        body = sec["body"]
        if len(prefix) + len(body) <= chunk_size:
            out.append({"content": f"{prefix}{body}".strip(),
                        "section_title": title})
            continue
        head = title or (doc_title or "")
        for piece in _split_sentences(body, chunk_size, overlap):
            pfx = f"{head}\n" if head else ""
            out.append({"content": f"{pfx}{piece}".strip(),
                        "section_title": title or doc_title})

    return [o for o in out if o["content"]]
