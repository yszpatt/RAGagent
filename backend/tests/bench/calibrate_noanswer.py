"""No-Answer 阈值标定工具。

为什么需要它
------------
实测发现（docs/plans/2026-08-29-optimization-plan.md 实验 B）：
**绝对阈值会随语料规模漂移** —— 语料从 15 篇增到 35 篇后，域外查询的最高相似度
从 0.526 涨到 0.600（偶然撞上相似片段的概率上升），原本干净的判定边界出现重叠。

所以阈值不能拍脑袋，也不能一劳永逸。本工具让你用**自己的真实语料**重新标定，
直接输出应写入配置的 ANSWER_GATE 值。

用法
----
    # 1) 用内置合成语料快速试跑（验证工具本身可用）
    python tests/bench/calibrate_noanswer.py

    # 2) 用自己的语料（每行一个片段）
    python tests/bench/calibrate_noanswer.py --corpus my_docs.txt

    # 3) 用自己的问答对（JSON: [{"query": "...", "in_domain": true}, ...]）
    python tests/bench/calibrate_noanswer.py --corpus my_docs.txt --queries my_qa.json

    # 4) 不加载 reranker，只标定向量门控（快很多）
    python tests/bench/calibrate_noanswer.py --no-rerank

输出
----
信号分布统计、混淆矩阵、阈值网格搜索 Top-N，以及推荐写入 .env 的配置值。

注意：本文件不以 test_ 开头，不会被 pytest 收集（它是工具，不是断言测试）。
"""
from __future__ import annotations

import argparse
import json
import statistics as st
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# 内置合成语料 + 问答对（企业制度/合同场景），保证工具开箱可跑
# ---------------------------------------------------------------------------

DEFAULT_CORPUS = [
    "第八条 违约责任：任何一方违反本合同约定，应向守约方支付违约金人民币壹拾万元整，并赔偿因此造成的直接经济损失。",
    "第九条 保密义务：乙方应对甲方提供的技术资料、商业信息承担保密责任，保密期限自合同终止之日起三年。",
    "第五条 付款方式：甲方应于每月五日前支付上月服务费，逾期按日万分之五计收滞纳金。",
    "第十二条 争议解决：因本合同引起的纠纷，双方应友好协商解决；协商不成的，提交合同签署地人民法院诉讼解决。",
    "第三章 休假制度：员工累计工作满一年不满十年的，年休假五天；满十年不满二十年的，年休假十天。",
    "差旅费报销标准：一线城市住宿费上限每晚四百元，市内交通费凭票据实报销，餐补每人每天八十元。",
    "第二条 服务期限：本合同自二零二六年一月一日起生效，有效期两年，期满前三十日双方未提出异议的自动续期一年。",
    "设备采购流程：单笔金额超过五万元的采购须经部门负责人、财务负责人及总经理三级审批后方可执行。",
    "第十一条 不可抗力：因地震、台风、洪水等自然灾害致使合同无法履行的，遭受不可抗力一方可部分或全部免除责任。",
    "绩效考核：季度考核结果分为优秀、良好、合格、不合格四档，连续两个季度不合格的，公司有权调整工作岗位。",
    "第四条 知识产权：乙方在履行本合同过程中开发的软件著作权归甲方所有，乙方享有署名权。",
    "第六章 培训管理：公司每年为员工提供不少于四十小时的专业技能培训，培训费用由公司承担。",
    "员工入职流程：新员工须在入职当日提交身份证复印件、学历证明及原单位离职证明，逾期未提交视为放弃录用。",
    "服务器运维规范：生产环境数据库每日凌晨两点自动全量备份，备份文件保留三十天，恢复演练每季度一次。",
    "第十条 合同解除：一方严重违约致使合同目的无法实现的，另一方有权单方解除合同并要求赔偿损失。",
]

DEFAULT_IN_DOMAIN = [
    "违约金是多少",
    "如果一方不履行合同要赔多少钱",
    "签了字能反悔吗，要付什么代价",
    "晚交钱会有什么后果",
    "打官司去哪儿解决",
    "我在公司干了八年能休几天假",
    "去上海出差住宿能报多少",
    "合同会不会自己续期",
    "买设备要走什么流程",
    "台风来了算不算免责",
    "代码写了算谁的",
    "新员工要交什么材料",
    "数据库坏了能恢复吗",
    "什么情况能把合同撕了",
    "一年有多少小时培训",
]

DEFAULT_OUT_DOMAIN = [
    "今天天气怎么样",
    "教我做一道红烧肉",
    "NBA 总决赛谁赢了",
    "量子计算机原理是什么",
    "怎么给猫洗澡",
    "推荐一部好看的电影",
    "Python 怎么连接 MySQL",
    "北京房价现在多少一平",
    "感冒了吃什么药好得快",
    "信用卡怎么申请",
    "如何练习吉他和弦",
    "太阳系有多少颗行星",
    "怎么做短视频涨粉",
    "孩子不爱吃饭怎么办",
    "汽车保养多久做一次",
]


# ---------------------------------------------------------------------------

def _p10(sorted_vals: list[float]) -> float:
    return sorted_vals[max(0, int(len(sorted_vals) * 0.1))]


def _f1(tp: int, fn: int, fp: int) -> float:
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    return 2 * prec * rec / (prec + rec) if prec + rec else 0.0


def measure(corpus: list[str], queries: list[tuple[str, bool]], use_rerank: bool):
    """对每个查询采集三个信号：v_top1 余弦相似度、rr_top1 精排分、rr_margin。"""
    from sentence_transformers import SentenceTransformer

    emb = SentenceTransformer("BAAI/bge-m3")
    vecs = emb.encode(corpus, normalize_embeddings=True)
    rr = None
    if use_rerank:
        from sentence_transformers import CrossEncoder
        rr = CrossEncoder("BAAI/bge-reranker-v2-m3")

    rows = []
    for q, in_domain in queries:
        qv = emb.encode([q], normalize_embeddings=True)[0]
        sims = [float(v @ qv) for v in vecs]
        order = sorted(range(len(sims)), key=lambda i: -sims[i])
        v_top1 = sims[order[0]]

        if rr is not None:
            top10 = order[:10]
            scores = [float(s) for s in rr.predict([(q, corpus[i]) for i in top10])]
            pairs = sorted(zip(top10, scores), key=lambda x: -x[1])
            rr_top1 = pairs[0][1]
            rr_top2 = pairs[1][1] if len(pairs) > 1 else 0.0
        else:
            rr_top1 = rr_top2 = 0.0
        rows.append((q, in_domain, v_top1, rr_top1, rr_top1 - rr_top2))
    return rows


def report(rows, rerank_enabled: bool = True):
    ind = [r for r in rows if r[1]]
    out = [r for r in rows if not r[1]]

    print("\n" + "=" * 88)
    print("信号分布（判断域内/域外是否可分）")
    print("=" * 88)
    print(f"{'信号':<12}{'域内min':>10}{'域内中位':>10}{'域外max':>10}{'域外中位':>10}  可分性")
    for name, i in (("v_top1", 2), ("rr_top1", 3), ("rr_margin", 4)):
        a = sorted(r[i] for r in ind)
        b = sorted(r[i] for r in out)
        ok = a[0] > b[-1]
        print(f"{name:<12}{a[0]:>10.4f}{st.median(a):>10.4f}{b[-1]:>10.4f}"
              f"{st.median(b):>10.4f}  {'干净' if ok else '重叠 <<'}")

    print("\n" + "=" * 88)
    print("阈值网格搜索（最大化 F1 = 少误杀 + 少漏拒）")
    print("=" * 88)

    def ev(pred):
        tp = sum(1 for r, p in zip(rows, pred) if r[1] and p)
        fn = sum(1 for r, p in zip(rows, pred) if r[1] and not p)
        fp = sum(1 for r, p in zip(rows, pred) if not r[1] and p)
        return tp, fn, fp, _f1(tp, fn, fp)

    results = []
    for thr in [x / 200 for x in range(40, 180)]:
        results.append((ev([r[2] >= thr for r in rows]), f"仅 v_top1 >= {thr:.3f}", thr))
    grid = [x / 1000 for x in range(0, 400, 5)]
    for tv in [x / 100 for x in range(40, 80, 2)]:
        for tr in grid:
            pred = [(r[2] >= tv) and (r[3] >= tr) for r in rows]
            results.append((ev(pred), f"AND: v_top1>={tv:.2f} 且 rr_top1>={tr:.3f}", tv))

    results.sort(key=lambda x: (-x[0][3], x[0][1], x[0][2]))
    print(f"{'F1':>7}  {'规则':<42}{'正确回答':>9}{'误杀':>7}{'漏拒':>7}")
    print("-" * 88)
    seen = set()
    shown = 0
    for (tp, fn, fp, f1), rule, _ in results:
        if rule in seen:
            continue
        seen.add(rule)
        print(f"{f1:>7.4f}  {rule:<42}{tp:>9}{fn:>7}{fp:>7}")
        shown += 1
        if shown >= 10:
            break

    # 当前基线（旧逻辑：rerank 0.3）
    tp, fn, fp, f1 = ev([r[3] >= 0.3 for r in rows])
    print("-" * 88)
    if rerank_enabled:
        print(f"{f1:>7.4f}  {'【旧基线】rr_top1 >= 0.30':<42}{tp:>9}{fn:>7}{fp:>7}")
    else:
        print(f"{'n/a':>7}  {'【旧基线】rr_top1 >= 0.30':<42}{'（--no-rerank 模式无精排分，基线不可比）'}")

    # 推荐值：取 F1 最优且仅依赖 v_top1 的规则中最稳健的一个（可行区间中点）
    ind_v = sorted(r[2] for r in ind)
    out_v = sorted(r[2] for r in out)
    if ind_v[0] > out_v[-1]:
        rec = (out_v[-1] + ind_v[0]) / 2
        note = "域内外无重叠，取间隙中点（最稳健）"
    else:
        best_f1, best_t = -1.0, 0.55
        for t in [x / 200 for x in range(40, 180)]:
            tp = sum(1 for r in rows if r[1] and r[2] >= t)
            fn = sum(1 for r in rows if r[1] and r[2] < t)
            fp = sum(1 for r in rows if not r[1] and r[2] >= t)
            f = _f1(tp, fn, fp)
            if f > best_f1:
                best_f1, best_t = f, t
        rec = best_t
        note = "域内外存在重叠，取 F1 最优点（建议扩充语料后重标）"

    print("\n" + "=" * 88)
    print("推荐配置")
    print("=" * 88)
    print(f"  ANSWER_GATE = {rec:.2f}     ({note})")
    print("  写入 backend/.env：")
    print(f"      ANSWER_GATE={rec:.2f}")
    print("      ANSWER_GATE_ENABLED=true")
    print("      LLM_FINAL_CHECK=true    # Tier3 兜底，抗语料增长漂移")
    return rec


def load_corpus(path: str | None) -> list[str]:
    if not path:
        return DEFAULT_CORPUS
    lines = [ln.strip() for ln in Path(path).read_text(encoding="utf-8").splitlines()]
    docs = [ln for ln in lines if ln]
    if not docs:
        sys.exit(f"语料文件为空：{path}")
    return docs


def load_queries(path: str | None) -> list[tuple[str, bool]]:
    if not path:
        return ([(q, True) for q in DEFAULT_IN_DOMAIN]
                + [(q, False) for q in DEFAULT_OUT_DOMAIN])
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return [(d["query"], bool(d["in_domain"])) for d in data]


def main():
    ap = argparse.ArgumentParser(description="No-Answer 阈值标定工具")
    ap.add_argument("--corpus", help="语料文件，每行一个片段（默认用内置合成语料）")
    ap.add_argument("--queries", help="问答对 JSON：[{query, in_domain}]")
    ap.add_argument("--no-rerank", action="store_true", help="跳过 reranker，只标定向量门控（更快）")
    args = ap.parse_args()

    corpus = load_corpus(args.corpus)
    queries = load_queries(args.queries)
    n_in = sum(1 for _, b in queries if b)
    n_out = len(queries) - n_in

    print("=" * 88)
    print("No-Answer 阈值标定")
    print("=" * 88)
    print(f"  语料       : {len(corpus)} 段" + (f"  ({args.corpus})" if args.corpus else "  (内置)"))
    print(f"  域内查询   : {n_in}（期望回答）")
    print(f"  域外查询   : {n_out}（期望拒答）")
    print(f"  reranker   : {'关闭' if args.no_rerank else '启用'}")

    if n_in == 0 or n_out == 0:
        sys.exit("域内/域外查询都至少需要 1 条，否则无法评估。")

    rows = measure(corpus, queries, use_rerank=not args.no_rerank)
    report(rows, rerank_enabled=not args.no_rerank)


if __name__ == "__main__":
    main()
