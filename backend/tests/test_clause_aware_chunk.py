"""条款感知切块的回归测试。

每条断言都对应一个实测到的具体缺陷，注释里写明「不修会怎样」。
"""
from app.ingestion.chunkers.clause_aware import clause_aware_chunk

CONTRACT = """技术服务合同

甲方：星辰科技有限公司
乙方：智源信息技术有限公司

第一条 服务内容
乙方向甲方提供企业级知识库系统的开发、部署与运维服务。

第二条 服务期限
本合同自二零二六年一月一日起生效，有效期两年。

第八条 违约责任
任何一方违反本合同约定，应向守约方支付违约金人民币壹拾万元整。

第十二条 争议解决
因本合同引起的纠纷，双方应友好协商解决；协商不成的，提交合同签署地人民法院诉讼解决。
"""

MANUAL = """员工手册

第一章 入职与试用
新员工须在入职当日提交身份证复印件、学历证明及原单位离职证明。

第六章 行为规范
员工应保守公司商业秘密，不得向第三方泄露客户信息与技术资料。
"""


def test_each_clause_becomes_its_own_chunk():
    """整篇文档不能塌成 1 块。

    实测：477 字合同 < chunk_size 500，旧切块器输出 1 块，8 个条款语义互相
    稀释，任意问题命中同一块，top1-top2 相似度间隙中位数仅 0.0015。
    """
    chunks = clause_aware_chunk(CONTRACT)
    assert len(chunks) == 4, [c["section_title"] for c in chunks]
    assert [c["section_title"] for c in chunks] == [
        "第一条 服务内容", "第二条 服务期限", "第八条 违约责任", "第十二条 争议解决",
    ]


def test_short_clauses_are_never_merged_back():
    """短条款不许被链式并回大块。

    早期按 min_size 合并的实现把上述 4 条又并成 1 块，等于白切。
    """
    chunks = clause_aware_chunk(CONTRACT, min_size=80)
    assert len(chunks) == 4
    assert all(len(c["content"]) < 200 for c in chunks)


def test_leading_preamble_attaches_to_first_clause():
    """文档名与缔约方不构成事实单元，应并入其后的第一个条款块，而非单独成块。"""
    chunks = clause_aware_chunk(CONTRACT)
    first = chunks[0]["content"]
    assert "技术服务合同" in first
    assert "甲方：星辰科技有限公司" in first
    assert "第一条 服务内容" in first
    # 其余条款不应携带引导段
    assert "甲方" not in chunks[1]["content"]


def test_content_carries_title_for_semantic_match():
    """标题拼进正文，使抽象提问（「打官司去哪儿解决」）能匹配「第十二条 争议解决」。"""
    chunks = clause_aware_chunk(CONTRACT)
    dispute = [c for c in chunks if c["section_title"] == "第十二条 争议解决"][0]
    assert dispute["content"].startswith("第十二条 争议解决")
    assert "人民法院诉讼解决" in dispute["content"]


def test_no_word_is_cut_in_half_at_boundary():
    """切块不得切断词语。

    实测旧切块器把「员工应保守公司商业秘密」切成上一块以「员」结尾、
    下一块以「司商业秘密…」开头，污染向量语义与引用展示。
    """
    chunks = clause_aware_chunk(MANUAL)
    joined = "".join(c["content"] for c in chunks)
    assert "员工应保守公司商业秘密" in joined
    # 任何一块都不应以半个词开头
    for c in chunks:
        body = c["content"].split("\n")[-1]
        assert not body.startswith("司商业秘密")


def test_markdown_heading_is_recognized():
    text = "# 报销制度\n出差须提前申请。\n\n## 住宿标准\n一线城市每晚四百元。"
    chunks = clause_aware_chunk(text)
    assert [c["section_title"] for c in chunks] == ["报销制度", "住宿标准"]


def test_oversized_clause_recurses_with_title_prefix():
    """单条超长时回退句子级切分，每个子块仍带标题，保证自描述可检索。"""
    body = "本条内容非常长。" * 60  # ≈ 540 字，远超 chunk_size
    text = f"第九条 保密义务\n{body}"
    chunks = clause_aware_chunk(text, chunk_size=200, overlap=30)
    assert len(chunks) > 1
    assert all(c["content"].startswith("第九条 保密义务") for c in chunks)
    assert all(len(c["content"]) <= 200 * 1.5 + 20 for c in chunks)


def test_text_without_any_structure_falls_back():
    """无条款结构的长文走句子级切分，且切分结果有界。"""
    text = "公司实行标准工时制。" * 100
    chunks = clause_aware_chunk(text, chunk_size=200)
    assert len(chunks) > 1
    assert all(len(c["content"]) <= 200 * 1.5 + 20 for c in chunks)


def test_empty_input():
    assert clause_aware_chunk("") == []
    assert clause_aware_chunk("   \n\n  ") == []


def test_content_is_not_lost():
    """切块不得吞字：所有正文字符都应原样保留。

    按字符多重集比较而非字符串相等 —— 标题会被有意前置到块首，
    顺序本就与原文不同，但不允许多字（重复）或少字（缺失）。
    """
    from collections import Counter
    import re

    norm = lambda s: re.sub(r"\s+", "", s)  # noqa: E731
    chunks = clause_aware_chunk(CONTRACT)
    assert Counter(norm("".join(c["content"] for c in chunks))) == Counter(norm(CONTRACT))


def test_title_appears_exactly_once_per_chunk():
    """标题前置实现早期会在引导段合并时重复插入标题，导致块内出现两次。"""
    chunks = clause_aware_chunk(CONTRACT)
    for c in chunks:
        assert c["content"].count(c["section_title"]) == 1, c["content"][:60]


def test_chinese_numeric_headings():
    text = "一、总则\n本制度适用于全体员工。\n二、细则\n具体标准见附件。"
    chunks = clause_aware_chunk(text)
    assert [c["section_title"] for c in chunks] == ["一、总则", "二、细则"]
