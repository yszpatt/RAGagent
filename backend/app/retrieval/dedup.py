"""检索结果近重复剔除。

为什么需要（两个来源不同的问题）
--------------------------------
1. 同一份文档被重复上传。实测语料里 7 篇文档只有 4 篇是不同内容：
   同一份合同存在 3 份副本、员工手册存在 2 份，9 个块里 4 个是冗余的。
   重复块会原样挤占 top-k 名额 —— top_k=5 时实际多样性可能只剩 3。
2. 不同文档天然含有相同条款。企业语料里保密义务、离职流程这类套话
   常同时出现在员工手册与劳动合同中，这类重复无法通过入库去重消除。

因此去重分两层：入库侧按内容哈希拦截完全一致的文件（省存储与算力），
检索侧按文本相似度剔除近重复块（保 top-k 多样性）。本模块负责后者。

用法位置
--------
必须在 rerank **之前**执行。若等到 rerank 截到 top5 再去重，重复项早已挤掉
本可入选的其他块，多样性无法挽回。
"""

from __future__ import annotations

import re

_WHITESPACE = re.compile(r"\s+")


def _shingles(text: str, n: int = 3) -> set[str]:
    """字符 n-gram 集合。中文无词边界，字符 n-gram 比分词更稳且不依赖词典。"""
    t = _WHITESPACE.sub("", text or "")
    if not t:
        return set()
    if len(t) <= n:
        return {t}
    return {t[i:i + n] for i in range(len(t) - n + 1)}


def containment(a: set[str], b: set[str]) -> float:
    """重叠系数 |A∩B| / min(|A|,|B|)，取值 [0,1]。

    为什么不用 Jaccard：去重要回答的是「这块是否已被我保留的某块覆盖」，
    是不对称问题，而 Jaccard 会惩罚长度差。实测一段 30 字文本与它的 35 字
    扩写版（仅多一句），Jaccard 只有 0.794 —— 低于任何合理阈值，真正的
    近重复反而漏网；重叠系数则是 0.964，符合直觉。
    """
    if not a or not b:
        # 两边都空视为完全重合；一边空则视为无关（避免空块吃掉正常块）
        return 1.0 if not a and not b else 0.0
    inter = len(a & b)
    if not inter:
        return 0.0
    return inter / min(len(a), len(b))


def similarity(a: str, b: str, n: int = 3) -> float:
    """两段文本的重叠系数，取值 [0,1]。"""
    return containment(_shingles(a, n), _shingles(b, n))


def dedup_hits(hits: list[dict], threshold: float = 0.9, n: int = 3) -> list[dict]:
    """贪心去重：按输入顺序保留，内容被已保留项覆盖（重叠系数 >= threshold）的丢弃。

    hits 为 VectorStore.search 的输出（每项含 "content"）。输入顺序即相关性
    顺序，因此保留的总是每个重复组里排得最靠前的那个。
    """
    if not hits or threshold > 1.0:
        return list(hits)
    kept: list[dict] = []
    kept_shingles: list[set[str]] = []
    for h in hits:
        sh = _shingles(h.get("content", ""), n)
        is_dup = False
        for ks in kept_shingles:
            if containment(sh, ks) >= threshold:
                is_dup = True
                break
        if not is_dup:
            kept.append(h)
            kept_shingles.append(sh)
    return kept
