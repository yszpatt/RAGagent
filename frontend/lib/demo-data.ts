// 演示模式占位数据。仅在前端不可达后端 / 预览「规划中功能」时使用。
// 所有入口都标注「演示」/「预览」，不与真实数据混淆。

import type { Conversation, DocumentMeta, SourceRef } from "./types";

const H = 3600_000;

/* ---------------- 会话 ---------------- */

const turn = (
  id: string,
  query: string,
  answer: string,
  citations: Array<{ chunk_id: string; page: number | null }>,
  at: number,
) => ({ id, query, answer, no_answer: false, citations, at });

export const demoConversations: Conversation[] = [
  {
    id: "demo-conv-1",
    title: "供应商合同违约金条款",
    updatedAt: Date.now() - 26 * H,
    turns: [
      turn(
        "t1",
        "我们去年签的供应商合同里，违约金条款是怎么约定的？",
        `根据 2025 年度供应商框架协议，违约责任约定如下：\n\n1. 乙方逾期交付的，每逾期一日按合同总价款的 **0.05%** 支付违约金，累计不超过合同总价款的 5%[1]；\n2. 甲方逾期付款的，按同期 LPR 上浮 30% 支付资金占用费[1]；\n3. 任一方违约导致合同解除的，违约方需支付合同总价款 **10%** 的解约违约金[2]。\n\n补充协议对上述比例未作调整，仅将付款账期由 60 天延长至 90 天[2]。`,
        [
          { chunk_id: "demo-c-101", page: 7 },
          { chunk_id: "demo-c-102", page: 12 },
        ],
        Date.now() - 26 * H,
      ),
      turn(
        "t2",
        "违约金有没有例外情况或豁免条款？",
        `有。框架协议第 11.3 条约定了两类例外：\n\n1. **不可抗力**：因自然灾害、疫情管控等不可抗力导致违约的，在受影响范围内免责，但需在 7 个工作日内提供书面证明[1]；\n2. **小额订单豁免**：单笔金额低于 5 万元的订单不适用逾期违约金条款[2]。\n\n需要注意的是，质量问题导致的违约不适用上述豁免，单独按质保条款处理[1]。`,
        [{ chunk_id: "demo-c-103", page: 9 }],
        Date.now() - 26 * H + 300_000,
      ),
    ],
  },
  {
    id: "demo-conv-2",
    title: "差旅报销标准",
    updatedAt: Date.now() - 52 * H,
    turns: [
      turn(
        "t3",
        "出差住宿费报销标准是多少？",
        `根据《差旅费管理办法（2026 修订）》，住宿费报销标准按城市类别执行：\n\n- 一类城市（北京、上海、广州、深圳）：**600 元/晚**\n- 二类城市（省会及计划单列市）：**450 元/晚**\n- 其他城市：**350 元/晚**\n\n超标部分需事前审批，否则不予报销[1]。同城市连续住宿超过 5 晚的，从第 6 晚起按标准的 85% 报销[2]。`,
        [
          { chunk_id: "demo-c-201", page: 3 },
          { chunk_id: "demo-c-202", page: 4 },
        ],
        Date.now() - 52 * H,
      ),
    ],
  },
];

/** 演示问答：按关键词返回预设回答，否则触发无答案兜底 */
export function demoAsk(query: string): {
  answer: string;
  no_answer: boolean;
  citations: Array<{ chunk_id: string; page: number | null }>;
  conversation_id: null;
} {
  const q = query.toLowerCase();
  if (/违约|合同|逾期/.test(q)) {
    return {
      answer: demoConversations[0].turns[0].answer,
      no_answer: false,
      citations: demoConversations[0].turns[0].citations,
      conversation_id: null,
    };
  }
  if (/报销|住宿|差旅/.test(q)) {
    return {
      answer: demoConversations[1].turns[0].answer,
      no_answer: false,
      citations: demoConversations[1].turns[0].citations,
      conversation_id: null,
    };
  }
  if (/年假|休假|考勤/.test(q)) {
    return {
      answer: `根据《员工手册》考勤章节：\n\n1. 年休假按司龄核定：满 1 年 5 天，满 3 年 10 天，满 5 年 15 天[1]；\n2. 年假原则上当年使用，确因工作原因未休的，最长可顺延至次年 3 月 31 日[2]；\n3. 请假需提前 3 个工作日在 OA 提交，经理审批后生效[1]。`,
      no_answer: false,
      citations: [
        { chunk_id: "demo-c-301", page: 15 },
        { chunk_id: "demo-c-302", page: 16 },
      ],
      conversation_id: null,
    };
  }
  return {
    answer: "未找到相关信息，请尝试换个问法。",
    no_answer: true,
    citations: [],
    conversation_id: null,
  };
}

/* ---------------- 来源案卷（演示引用的原文摘录） ---------------- */

export const demoSources: Record<string, SourceRef> = {
  "demo-c-101": {
    ref: "引-01",
    title: "2025年度供应商框架协议.pdf",
    page: 7,
    section: "第 11 条 违约责任",
    excerpt:
      "11.1 乙方逾期交付本协议项下货物或服务的，每逾期一日，应按逾期部分对应合同价款（不含税）的 0.05% 向甲方支付违约金；违约金累计不超过本协议总价款的 5%。\n11.2 甲方逾期付款的，每逾期一日按同期贷款市场报价利率（LPR）上浮 30% 向乙方支付资金占用费。",
    chunkId: "demo-c-101",
  },
  "demo-c-102": {
    ref: "引-02",
    title: "2025年度供应商框架协议.pdf",
    page: 12,
    section: "第 18 条 协议解除",
    excerpt:
      "18.2 一方根本违约致使协议目的无法实现的，守约方有权解除本协议，并要求违约方支付本协议总价款 10% 的违约金。\n《补充协议（二）》：双方同意将付款账期自 60 日延长至 90 日，其他条款不变。",
    chunkId: "demo-c-102",
  },
  "demo-c-103": {
    ref: "引-01",
    title: "2025年度供应商框架协议.pdf",
    page: 9,
    section: "第 11.3 条 责任例外",
    excerpt:
      "11.3 因不可抗力（含自然灾害、疫情管控、政府行为）导致不能履约的，受影响方在受影响范围内免责，但应在不可抗力发生之日起 7 个工作日内向对方提供有权机构出具的书面证明。单笔金额低于 5 万元的订单不适用 11.1 条逾期违约金。质量违约不适用本条豁免。",
    chunkId: "demo-c-103",
  },
  "demo-c-201": {
    ref: "引-01",
    title: "差旅费管理办法（2026修订）.docx",
    page: 3,
    section: "第四章 住宿标准",
    excerpt:
      "第八条 员工出差住宿费按城市类别凭票据据实报销，最高标准如下：一类城市（北京、上海、广州、深圳）600 元/晚；二类城市（省会城市及计划单列市）450 元/晚；其他城市 350 元/晚。超标部分未经事前审批的，不予报销。",
    chunkId: "demo-c-201",
  },
  "demo-c-202": {
    ref: "引-02",
    title: "差旅费管理办法（2026修订）.docx",
    page: 4,
    section: "第四章 住宿标准",
    excerpt:
      "第九条 同一城市连续住宿超过 5 晚的，自第 6 晚起按对应标准的 85% 报销；因会议、培训由承办方统一安排住宿的，凭通知按实报销，不受本条限制。",
    chunkId: "demo-c-202",
  },
  "demo-c-301": {
    ref: "引-01",
    title: "员工手册v3.2.docx",
    page: 15,
    section: "第七章 考勤与休假",
    excerpt:
      "7.2 年休假：司龄满 1 年不满 3 年的 5 天；满 3 年不满 5 年的 10 天；满 5 年的 15 天。休假需提前 3 个工作日在 OA 系统提交申请，经直属经理审批后生效。",
    chunkId: "demo-c-301",
  },
  "demo-c-302": {
    ref: "引-02",
    title: "员工手册v3.2.docx",
    page: 16,
    section: "第七章 考勤与休假",
    excerpt:
      "7.4 年休假原则上当年度使用。经审批未能休完的，可顺延至次年 3 月 31 日，逾期未休视为自动放弃（公司原因除外）。",
    chunkId: "demo-c-302",
  },
};

/* ---------------- 文档 ---------------- */

export const demoDocuments: DocumentMeta[] = [
  {
    id: "6a1f0c2e-11",
    title: "2025年度供应商框架协议.pdf",
    ext: "pdf",
    status: "completed",
    roles: ["admin", "manager"],
    uploadedAt: Date.now() - 72 * H,
    sizeLabel: "2.4 MB",
  },
  {
    id: "6a1f0c2e-12",
    title: "差旅费管理办法（2026修订）.docx",
    ext: "docx",
    status: "completed",
    roles: ["admin", "manager", "employee"],
    uploadedAt: Date.now() - 70 * H,
    sizeLabel: "48 KB",
  },
  {
    id: "6a1f0c2e-13",
    title: "员工手册v3.2.docx",
    ext: "docx",
    status: "completed",
    roles: ["admin", "manager", "employee"],
    uploadedAt: Date.now() - 55 * H,
    sizeLabel: "1.1 MB",
  },
  {
    id: "6a1f0c2e-14",
    title: "2026Q1经营分析报告.pdf",
    ext: "pdf",
    status: "completed",
    roles: ["admin", "manager"],
    uploadedAt: Date.now() - 30 * H,
    sizeLabel: "5.8 MB",
  },
  {
    id: "6a1f0c2e-15",
    title: "机房巡检记录-扫描件.pdf",
    ext: "pdf",
    status: "failed",
    errorMessage: "未能提取文本，可能是扫描件",
    roles: ["admin"],
    uploadedAt: Date.now() - 8 * H,
    sizeLabel: "12.6 MB",
  },
  {
    id: "6a1f0c2e-16",
    title: "信息技术部周报-w38.md",
    ext: "md",
    status: "processing",
    roles: ["admin", "manager", "employee"],
    uploadedAt: Date.now() - 600_000,
    sizeLabel: "16 KB",
  },
];

/* ---------------- 权限矩阵（预览） ---------------- */

export const permissionRows = demoDocuments.map((d) => ({
  id: d.id,
  title: d.title,
  roles: d.roles,
}));

/* ---------------- 审计日志（预览） ---------------- */

export interface AuditEntry {
  at: number;
  actor: string;
  role: "管理员" | "经理" | "员工";
  action: "查询" | "上传" | "权限变更" | "无答案";
  detail: string;
  hitCount: number | null;
}

export const demoAudit: AuditEntry[] = [
  { at: Date.now() - 0.4 * H, actor: "王小张", role: "员工", action: "查询", detail: "报销流程是什么", hitCount: 5 },
  { at: Date.now() - 1.2 * H, actor: "李经理", role: "经理", action: "查询", detail: "Q1 华东区回款完成率", hitCount: 5 },
  { at: Date.now() - 2.6 * H, actor: "王姐", role: "管理员", action: "上传", detail: "机房巡检记录-扫描件.pdf（失败）", hitCount: null },
  { at: Date.now() - 3.1 * H, actor: "王小张", role: "员工", action: "无答案", detail: "今天天气怎么样", hitCount: 0 },
  { at: Date.now() - 5.4 * H, actor: "李经理", role: "经理", action: "查询", detail: "供应商违约金上限", hitCount: 5 },
  { at: Date.now() - 7.0 * H, actor: "王姐", role: "管理员", action: "权限变更", detail: "2026Q1经营分析报告.pdf → +经理", hitCount: null },
  { at: Date.now() - 9.2 * H, actor: "陈小晓", role: "员工", action: "查询", detail: "年假顺延到什么时候", hitCount: 4 },
  { at: Date.now() - 12 * H, actor: "王姐", role: "管理员", action: "上传", detail: "信息技术部周报-w38.md", hitCount: null },
  { at: Date.now() - 20 * H, actor: "李经理", role: "经理", action: "查询", detail: "付款账期延长到多少天", hitCount: 5 },
  { at: Date.now() - 26 * H, actor: "王小张", role: "员工", action: "查询", detail: "出差住宿费报销标准", hitCount: 5 },
  { at: Date.now() - 33 * H, actor: "陈小晓", role: "员工", action: "无答案", detail: "停车场月租怎么申请", hitCount: 0 },
  { at: Date.now() - 46 * H, actor: "王姐", role: "管理员", action: "上传", detail: "2026Q1经营分析报告.pdf", hitCount: null },
];

/* ---------------- 看板指标（预览） ---------------- */

export const demoMetrics = {
  todayQueries: 128,
  acceptanceRate: 72,
  noAnswerRate: 12,
  citationRate: 96,
  parseFailRate: 3.2,
  latencyP95: "4.1s",
  weekly: [
    { day: "周一", queries: 86, noAnswer: 14 },
    { day: "周二", queries: 102, noAnswer: 15 },
    { day: "周三", queries: 121, noAnswer: 11 },
    { day: "周四", queries: 97, noAnswer: 13 },
    { day: "周五", queries: 134, noAnswer: 12 },
    { day: "周六", queries: 45, noAnswer: 18 },
    { day: "周日", queries: 38, noAnswer: 16 },
  ],
  recentQuestions: [
    { q: "违约金累计上限是多少", ok: true, at: "10:24" },
    { q: "二类城市住宿标准", ok: true, at: "10:11" },
    { q: "服务器 root 密码策略", ok: false, at: "09:58" },
    { q: "年假可以顺延多久", ok: true, at: "09:47" },
    { q: "停车场月租怎么申请", ok: false, at: "09:30" },
  ],
};
