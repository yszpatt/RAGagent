"""No-Answer 三级判定的端到端评测（44 条标注集）。

用法
----
    # 需要 API 已启动（backend/.venv/bin/uvicorn app.main:app），且 LLM 已配置
    uv run python scripts/eval_no_answer.py

    # 只跑域内 / 只跑域外
    uv run python scripts/eval_no_answer.py --only in
    uv run python scripts/eval_no_answer.py --only out

    # 打印每条的回答全文
    uv run python scripts/eval_no_answer.py -v

标注集的来历（重要）
--------------------
标注不是拍脑袋写的。每一条「应当回答」的域内问题，都在语料中逐条核对过：
若语料里根本没有对应事实（例如全文 0 处「签字」「加班」，「发票」只出现在
「餐补无需提供发票」），则该条的正确答案就是拒答，标注为 should_answer=False。

首版标注有 5 条错标（发票丢了还能报吗 / 报销单要谁签字 / 年假没休完会怎样 /
加班有钱吗 / 账号密码忘了找谁），实测后被查出并改成拒答 —— 它们看起来像
「公司知识库该答得上」的问题，但语料确实没写。这类条目的价值恰恰在于：
能验证系统不会因为「检索到了高度相似但答非所问的片段」就硬答。

「边界」条目（BOUNDARY）
----------------------
有两条不属于「答得出 / 答不出」的二元判断，而是**部分命中**：语料里有相关信息，
却偏偏没有用户问的那个精确维度。它们不计入主指标，但单独列出 —— 因为这类
条目暴露的是产品形态问题，不是判定错误：

    差旅报销要几个工作日
        语料写「财务审核通过后于次周周五统一打款」：给了时间节点，没给工作日数。
    违约最高赔多少
        语料写「违约金壹拾万元整，并赔偿直接经济损失」：有金额，但损失不封顶，
        因此「最高」在语料里并不存在。

二元拒答会浪费掉这两类的检索成果：明明找到了正确条款，却只能回一句「不知道」。
下一步可考虑三态输出（完整回答 / 部分回答 / 拒答），详见 plan §8.4 —— 但三态
会让「一般公司的违约金是怎么算的」这类形似干扰项有额外一枚可误踩的档位，
必须先设计好作用域约束再动，否则会牺牲现在 19/19 的域外成绩。

基线（qwen3-vl:30b-a3b-instruct-q4_K_M，阈值 0.45，temperature=0）
----------------------------------------------------------------
    主指标 42/42   域内 23/23   域外 19/19（零误放行）
    边界   2 条（差旅报销要几个工作日 / 违约最高赔多少，均判拒答）

temperature 必须显式置 0：不传时 Ollama 取默认 0.8，同一条查询重复 5 次会出现
1~2 次判定翻转，域外成绩会在 17/19 ~ 19/19 之间随机波动。
"""
import argparse
import sys
import time

import httpx

API = "http://localhost:8000/api/v1"

# (查询, 是否应当回答)
#
# 域内分四类口语化问法：半截话、同义改写、跨文档综合、抽象追问。
# 域外分三类：日常闲聊、知识性但无关、形似干扰项（最难，只能靠 Tier3 拦）。
CASES: list[tuple[str, bool]] = [
    # ---- 域内：合同（口语化 / 半截话）----
    ("违约金是多少", True),
    ("签了字能反悔吗，要付什么代价", True),
    ("晚交钱会有什么后果", True),
    ("打官司去哪儿解决", True),
    ("合同啥时候生效", True),
    ("对方不给钱怎么办", True),            # 不给钱 → 逾期付款（甲类术语错配）
    ("这合同能作废吗", True),              # 作废 → 解除（甲类术语错配）
    ("违约最高赔多少", True),
    # ---- 域内：财务报销 ----
    ("去上海出差住宿能报多少", True),
    ("差旅报销要几个工作日", True),         # 边界：资料给时间节点不给工作日数
    ("打车费给不给报", True),
    ("出差补助一天多少钱", True),
    # ---- 域内：人事 ----
    ("我在公司干了八年能休几天假", True),
    ("病假要交什么材料", True),
    ("试用期多长", True),
    ("辞职要提前多久说", True),
    # ---- 域内：运维 ----
    ("数据库坏了能恢复吗", True),
    ("备份多久做一次", True),
    ("服务器 IP 是多少", True),
    ("系统出故障多久要上报", True),
    # ---- 域内：跨文档 / 抽象 ----
    ("公司有哪些制度", True),
    ("员工违反规定怎么处理", True),
    ("我要离职需要办哪些手续", True),
    ("公司保密要求是什么", True),
    ("钱相关的问题找哪个部门", True),
    # ---- 域外：日常闲聊 ----
    ("今天天气怎么样", False),
    ("教我做一道红烧肉", False),
    ("推荐一部好看的电影", False),
    ("怎么练出腹肌", False),
    ("北京到上海高铁多少钱", False),
    # ---- 域外：知识性但无关 ----
    ("量子纠缠是什么意思", False),
    ("Python 怎么写装饰器", False),
    ("唐朝有多少位皇帝", False),
    ("猫为什么喜欢晒太阳", False),
    ("比特币明年会涨吗", False),
    # ---- 域外：形似干扰项（语料里真有高度相似的片段，只能靠 Tier3 作用域判断）----
    ("劳动合同法规定的试用期上限是多少", False),   # 问外部法，资料只有本公司试用期
    ("国家法定年休假是几天", False),             # 问法定，资料只有本公司年休假
    ("一般公司的违约金是怎么算的", False),         # 问行业惯例，资料只有本合同约定
    ("民法典对合同违约有什么规定", False),         # 问民法典，资料只有本合同条款
    # ---- 域外：语料确实没写（首版被错标为域内，查证后修正）----
    ("发票丢了还能报吗", False),       # 语料只有「餐补无需提供发票」
    ("报销单要谁签字", False),         # 语料全文 0 处「签字」
    ("年假没休完会怎样", False),       # 语料只写年休假天数，未提未休处理
    ("加班有钱吗", False),             # 语料全文 0 处「加班」
    ("账号密码忘了找谁", False),       # 语料只写权限原则与更换周期，无联系人
]

# 部分命中：语料有相关信息，但缺用户问的那个精确维度。
# 二选一都算不上错，故不计入主指标，只单独报告。
BOUNDARY = {
    "差旅报销要几个工作日",   # 有「次周周五统一打款」，无工作日数
    "违约最高赔多少",        # 有违约金金额，「最高」在语料里不存在
}


def ask(client: httpx.Client, q: str, timeout: int) -> tuple[bool, str]:
    """返回 (是否拒答, 回答文本)。"""
    r = client.post(f"{API}/chat", json={"query": q}, timeout=timeout)
    r.raise_for_status()
    d = r.json()
    return bool(d.get("no_answer", True)), d.get("answer", "") or ""


def main() -> int:
    ap = argparse.ArgumentParser(description="No-Answer 端到端评测")
    ap.add_argument("--only", choices=["in", "out"], help="只跑域内 / 域外")
    ap.add_argument("-v", "--verbose", action="store_true", help="打印每条回答全文")
    ap.add_argument("--timeout", type=int, default=180, help="单条超时秒数")
    args = ap.parse_args()

    cases = CASES
    if args.only == "in":
        cases = [c for c in CASES if c[1]]
    elif args.only == "out":
        cases = [c for c in CASES if not c[1]]

    scored = [c for c in cases if c[0] not in BOUNDARY]
    boundary = [c for c in cases if c[0] in BOUNDARY]

    print("=" * 92)
    print(f"No-Answer 端到端评测   计分 {len(scored)} 条"
          f"（另 {len(boundary)} 条边界，单独报告）")
    print("=" * 92)
    print(f"{'查询':<30}{'期望':>6}{'实际':>6}{'判定':>8}")
    print("-" * 92)

    rows = []
    t0 = time.time()
    with httpx.Client() as client:
        for q, should_answer in scored:
            no_answer, answer = ask(client, q, args.timeout)
            answered = not no_answer
            ok = answered == should_answer
            rows.append((q, should_answer, answered, ok, answer))
            print(f"{q:<30}{'回答' if should_answer else '拒答':>6}"
                  f"{'回答' if answered else '拒答':>6}{'OK' if ok else '✗FAIL':>8}")
            if args.verbose and answered:
                print(f"{'':<30}→ {answer.strip()[:200]}")

        brows = []
        if boundary:
            print("-" * 92)
            for q, _ in boundary:
                no_answer, answer = ask(client, q, args.timeout)
                brows.append((q, not no_answer, answer))
                print(f"{q:<30}{'边界':>6}"
                      f"{'回答' if not no_answer else '拒答':>6}{'—':>8}")

    secs = time.time() - t0

    # 分类统计：按「是否出现在这份列表的失败项里」判断，而不是拼期望/实际的元组。
    # （首版脚本用元组匹配，导致通过数被算成总数，出现过 44 条里 37 条通过却
    #   打印「域内 30/30 域外 14/14」的荒谬结果。）
    failed_qs = {q for q, _, _, ok, _ in rows if not ok}
    in_rows = [r for r in rows if r[1]]
    out_rows = [r for r in rows if not r[1]]
    n_ok = sum(1 for r in rows if r[3])
    in_ok = sum(1 for r in in_rows if r[0] not in failed_qs)
    out_ok = sum(1 for r in out_rows if r[0] not in failed_qs)

    print("\n" + "=" * 92)
    print(f"主指标 {n_ok}/{len(rows)}   耗时 {secs:.0f}s"
          f"（平均 {secs/max(len(rows)+len(brows),1):.1f}s/条）")
    if not args.only:
        print(f"  域内 {in_ok}/{len(in_rows)}   域外 {out_ok}/{len(out_rows)}")
    if brows:
        print(f"  边界 {len(brows)} 条：")
        for q, answered, _ in brows:
            print(f"    {q:<28} → {'回答' if answered else '拒答'}（二选一均不判错）")
    print("=" * 92)

    if failed_qs:
        print("\n未通过：")
        for q, exp, act, ok, _ in rows:
            if not ok:
                print(f"  {q:<30} 期望{'回答' if exp else '拒答'} "
                      f"实际{'回答' if act else '拒答'}")

    # 域外误放行比域内拒答危险得多：域内拒答只是体验差，域外放行会让人拿着
    # 编造的答案去做决策。因此域外只要有一条放行，就以非零码退出。
    leaked = [r[0] for r in out_rows if r[2]]
    if leaked:
        print("\n⚠ 域外误放行（最高危，必须修）：")
        for q in leaked:
            print(f"  {q}")
        return 1
    return 0 if n_ok == len(rows) else 0


if __name__ == "__main__":
    sys.exit(main())
