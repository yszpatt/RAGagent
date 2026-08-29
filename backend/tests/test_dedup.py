"""检索结果近重复剔除的测试。

背景（实测）：语料里 7 篇文档只有 4 篇是不同内容，同一份合同存在 3 份副本，
9 个 chunk 里 4 个冗余。重复块原样挤占 top-k 名额，top_k=5 时实际多样性只剩 3。

度量用重叠系数（|A∩B| / min(|A|,|B|)）而非 Jaccard，默认阈值 0.90 ——
Jaccard 会惩罚长度差，实测 30 字与其 35 字扩写版的 Jaccard 只有 0.794，
低于任何合理阈值，真正的近重复反而漏网。
"""
from app.retrieval.dedup import dedup_hits, similarity


def _hit(content, **extra):
    d = {"content": content}
    d.update(extra)
    return d


def test_identical_chunks_collapse_to_one():
    dup = "乙方应对甲方提供的技术资料承担保密责任，保密期限三年。"
    hits = [_hit(dup, id="1"), _hit(dup, id="2"), _hit(dup, id="3")]
    out = dedup_hits(hits, threshold=0.9)
    assert len(out) == 1
    assert out[0]["id"] == "1"  # 保留排在最前的那个


def test_distinct_chunks_all_kept():
    hits = [
        _hit("生产环境服务器 IP 地址 10.20.31.47 部署在华东二区可用区 C。"),
        _hit("数据库每日凌晨两点自动全量备份，备份文件保留三十天。"),
        _hit("员工累计工作满一年可享受五天带薪年休假。"),
    ]
    assert len(dedup_hits(hits, threshold=0.9)) == 3


def test_near_duplicate_across_documents_removed():
    """不同文档里的相同套话条款（如保密义务）应被剔除，只留一条。"""
    a = "员工应当保守公司商业秘密，不得向第三方泄露客户信息与技术资料。"
    b = "员工应当保守公司商业秘密，不得向第三方泄露客户信息与技术资料，违者追责。"
    hits = [_hit(a, id="handbook"), _hit(b, id="contract")]
    out = dedup_hits(hits, threshold=0.9)
    assert len(out) == 1
    assert out[0]["id"] == "handbook"
    # 相似度确实超过阈值，验证剔除有依据而非偶然
    assert similarity(a, b) >= 0.9
    # 对照：同样一对文本，Jaccard 仅约 0.79，会漏判
    assert similarity(a, b) > _jaccard(a, b)


def test_keeps_best_ranked_of_each_duplicate_group():
    """输入顺序即相关性顺序，每个重复组保留排最前的，而不是随机一个。"""
    dup = "出差须提前在系统提交申请并经部门负责人审批。"
    other = "工资于每月十五日发放上月工资。"
    hits = [_hit(dup, id="best"), _hit(other, id="keep"), _hit(dup, id="worse")]
    out = dedup_hits(hits, threshold=0.9)
    assert [h["id"] for h in out] == ["best", "keep"]


def _jaccard(a: str, b: str, n: int = 3) -> float:
    """对照组：Jaccard，用于说明为何不采用它。"""
    sh = lambda s: {s[i:i+n] for i in range(len(s)-n+1)}  # noqa: E731
    sa, sb = sh(a), sh(b)
    return len(sa & sb) / len(sa | sb)


def test_threshold_boundary():
    a = "本合同总金额为人民币贰佰叁拾万元整。"
    b = "本合同总金额为人民币贰佰叁拾万元整，分十二期支付。"
    # 阈值 1.0 等价于只剔除完全相同；更低的阈值更激进
    assert len(dedup_hits([_hit(a), _hit(b)], threshold=1.0)) == 2
    assert len(dedup_hits([_hit(a), _hit(b)], threshold=0.5)) == 1


def test_empty_and_edge_cases():
    assert dedup_hits([]) == []
    assert len(dedup_hits([_hit("")])) == 1
    assert len(dedup_hits([_hit(""), _hit("")])) == 1
    # 超短文本（短于 n-gram 长度）不应崩溃
    assert len(dedup_hits([_hit("甲"), _hit("乙")])) == 2


def test_similarity_range():
    assert similarity("同一个文本", "同一个文本") == 1.0
    assert similarity("今天天气怎么样", "数据分类分为四级") < 0.3
    assert 0.0 <= similarity("", "任意文本") <= 1.0
