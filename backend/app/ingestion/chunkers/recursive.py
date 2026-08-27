def _split_oversized(
    chunks: list[str], chunk_size: int, overlap: int, next_start: int, separators: list[str]
) -> list[str]:
    """把超出 chunk_size*1.5 的单块递归到剩余更深层分隔符切分，避免超大无分隔片段整块返回。"""
    result = []
    for c in chunks:
        if len(c) > chunk_size * 1.5 and next_start < len(separators):
            result.extend(_recursive_chunk(c, chunk_size, overlap, next_start, separators))
        else:
            result.append(c)
    return result


def _recursive_chunk(
    text: str, chunk_size: int, overlap: int, start: int, separators: list[str]
) -> list[str]:
    """从 start 处的分隔符开始递归切块。

    每次递归都从下一层级分隔符继续，保证在到达字符级 "" 前必然终止；
    字符级切分在 overlap 被钳制后总能产出有界块。
    """
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    for sep_index in range(start, len(separators)):
        sep = separators[sep_index]
        parts = text.split(sep) if sep else list(text)
        chunks, cur = [], ""
        for p in parts:
            piece = p + (sep if sep else "")
            if len(cur) + len(piece) > chunk_size and cur:
                chunks.append(cur.strip())
                cur = cur[-overlap:] if overlap else ""
            cur += piece
        if cur.strip():
            chunks.append(cur.strip())
        if len(chunks) > 1:
            return _split_oversized(chunks, chunk_size, overlap, sep_index + 1, separators)
    return [text]


def recursive_chunk(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按分隔符优先级递归切块，带重叠。demo 版基于字符，生产换 tiktoken。

    overlap 被钳制在 chunk_size - 2 以内，保证重叠必然使 cur 收缩，
    避免 overlap >= chunk_size 时 cur[-overlap:] 不收缩导致的退化爆炸。
    """
    overlap = min(overlap, max(0, chunk_size - 2))
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    separators = ["\n\n", "\n", "。", ".", " ", ""]
    return _recursive_chunk(text, chunk_size, overlap, 0, separators)
