def recursive_chunk(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """按分隔符优先级递归切块，带重叠。demo 版基于字符，生产换 tiktoken。"""
    if len(text) <= chunk_size:
        return [text] if text.strip() else []
    separators = ["\n\n", "\n", "。", ".", " ", ""]
    for sep in separators:
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
            return chunks
    return [text]
