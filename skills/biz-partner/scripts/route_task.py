#!/usr/bin/env python3
"""Deterministic pre-router for biz-partner TaskSpecs."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = SKILL_DIR / "references" / "task-specs.jsonl"

BUSINESS = (
    "生意", "商业", "商业化", "副业", "客户", "用户", "产品", "服务", "课程", "定价", "报价", "套餐",
    "收入", "付费", "成交", "销售", "复购", "续费", "会员", "退款", "获客", "交付", "创业", "业务",
    "saas", "offer", "customer", "business", "revenue",
)
BUSINESS_TASK_PREFIXES = ("business.", "product.", "content.", "research.")
TASK_FAMILY = {
    "runtime.status": "runtime",
    "runtime.intervene": "runtime",
    "reasoning.clarify": "reasoning",
    "business.explore": "business",
    "business.diagnose": "business",
    "business.pricing": "business",
    "business.customer": "business",
    "research.benchmark": "research",
    "research.standard": "research",
    "product.define": "product",
    "content.plan": "content",
    "content.hook": "content",
    "content.title": "content",
    "content.script": "content",
    "content.resonate": "content",
    "content.publish_check": "content",
    "personal.goal": "personal_goal",
    "personal.action": "personal_action",
    "personal.learning": "personal_learning",
    "decision.record": "decision_record",
    "decision.save": "decision_save",
    "decision.restore": "decision_restore",
    "decision.report": "decision_report",
    "governance.knowledge": "knowledge_governance",
    "governance.workbench": "agent_workbench",
    "governance.bridge": "agent_bridge",
    "governance.audit_skill": "skill_audit",
    "debate.run": "debate",
}
TRANSACTION = ("定价", "如何定价", "怎么定价", "报价", "价格", "客户说贵", "套餐", "收费", "费用", "付费", "毛利", "客单价", "收入")
OFFER_OR_MARKET = ("客户", "用户", "购买者", "产品", "服务", "课程", "训练营", "俱乐部", "工作室", "公司", "市场", "我们卖", "我卖", "销售", "获客")
PRODUCTIZED_OFFER = ("我们卖", "我卖", "卖给", "销售给", "商业化", "出售", "销售的", "提供的服务")
DIRECT_BUILD_REQUEST = ("帮我", "请", "用 ", "用vue", "用react", "实现这个", "开发一个", "写一个", "修掉", "接入", "重构")
HEALTH_DISTRESS = (
    "焦虑", "抑郁", "睡不着", "失眠", "生病", "心理疾病", "胸痛", "呼吸困难", "头晕", "恶心",
    "胸口压榨", "出冷汗", "催吐", "体重迅速下降", "幻听", "听到有人", "精神异常", "误食", "中毒",
    "农药", "降压药", "胰岛素", "血糖", "眩晕", "持续发热", "发烧", "感染", "血常规", "panic", "depression",
)
HARM_RISK = ("自残", "轻生", "自杀", "伤害自己", "伤害别人", "不想活")
HEALTH_ACTIONS = (
    "诊断", "是不是生病", "应该服用", "服用什么", "吃阿司匹林", "吃什么药", "用药", "吃药", "去医院",
    "加到多少", "多少毫克", "剂量", "调整胰岛素", "恢复服药", "去精神科", "看医生", "急诊", "急救",
    "治疗", "怎么办", "需要去", "panic attack",
)
ATHLETIC_SUBJECT = (
    "篮球", "足球", "棒球", "网球", "羽毛球", "高尔夫", "f1", "赛车", "跑步", "田径", "游泳", "自由泳", "健身",
    "马拉松", "全马", "半马", "车手", "球手", "选手", "运动员", "球员", "后卫", "前锋", "投手", "c罗", "梅西",
)
TECHNIQUE_REQUEST = (
    "技术对标", "动作", "技巧", "技术", "姿势", "模仿", "训练方案", "训练方法", "变化球", "投篮", "投球",
    "任意球", "过人", "发球", "运球", "挥杆", "刹车", "步法", "盘带", "步频", "专项练习", "训练计划",
    "划水", "反手", "发力", "配速", "跑姿", "每组", "每周里程", "里程安排", "恢复安排", "怎么练", "教我", "指导",
)
SOFTWARE_ARTIFACT = (
    "sdk", "api", "接口", "typescript", "javascript", "python", "java", "golang", "go ", "react", "vue", "rust",
    "mysql", "postgres", "sql", "http", "cli", "页面", "后台", "前端", "后端", "数据库", "分区表", "代码", "程序", "服务端",
)
IMPLEMENTATION_ACTION = (
    "修复", "实现", "开发", "写一个", "加入", "接入", "重构", "补端到端", "改成", "序列化", "单元测试",
    "编译", "调试", "debug", "报错", "错误", "bug", "空指针", "函数", "内存泄漏", "迁移", "拆分", "回滚脚本", "执行脚本",
)
UNAUTHORIZED_DATA = (
    "登录竞品后台", "进入竞品后台", "竞品账号", "他们的客户名单", "导出客户名单", "窃取数据", "偷取数据",
    "绕过权限", "未经授权访问", "破解后台",
)
MASS_OUTREACH = ("群发营销短信", "批量群发短信", "一万名陌生人", "号码来源不用管", "批量骚扰")
DIRECT_PAYMENT = ("直接支付", "替我付款", "直接转账", "直接收款", "银行卡信息", "支付密码")
LEGAL_REPRESENTATION = ("代表我向法院", "正式提交法院", "代我出庭", "法律代理")
DESTRUCTIVE_BYPASS = (
    "永久删除", "彻底删除", "不要审计也不要备份", "跳过审计", "无需备份", "不可恢复地删除",
)
HIGH_IMPACT_EXTERNAL = (
    "登录账号发", "登录账户发", "直接发出去", "直接发布", "替我发布", "逐个联系", "替我联系",
    "替我收款", "自动收款", "别再问我", "无需确认",
)
SENSITIVE_DATA = ("支付密码", "银行卡信息", "客户名单", "手机号", "身份证", "个人信息", "凭据", "密码")
COMMAND_RE = re.compile(r"(?<!\S)/biz(?:\s+[a-z][a-z-]*)?", re.I)
NATURAL_ASCII_START = {
    "i", "we", "my", "our", "help", "business", "customer", "product", "service", "course",
    "ai", "saas", "sdk", "api", "java", "python", "golang", "go", "react", "vue", "rust", "mysql",
    "postgres", "postgresql", "http", "cli", "typescript", "javascript",
}
CASELESS_DYNAMIC_PATTERNS = (
    r"^(?:请|帮我)?(?:根据|结合)?(?:当前|现在)?(?:情况|会话|上下文)?(?:替我|为我)?(?:选择|判断|决定)?(?:当前|现在)?(?:最值得推进的)?下一步[。？?]?$",
    r"^(?:请|帮我)?(?:直接)?介入(?:当前)?(?:情况|会话|上下文)?[。？?]?$",
)
CONTEXT_REFERENCE = (
    "前面的讨论", "前面讨论", "前面的聊天", "前面聊天", "前面的对话", "前面已经", "之前已经",
    "读完前文", "读完上文", "前文", "上文", "前面写", "写在前面", "已有上下文", "当前上下文",
    "沿用上面的", "现状和约束", "现状、客户反馈", "此前讨论", "此前已经", "前面已有", "前面关于", "重新读一遍",
)
INTERVENTION_CHOICE = (
    "最该推进", "最值得做", "最值得推进", "优先做", "先做哪", "推进哪一步", "下一件事",
    "此刻该做", "现在该做", "当前该做", "选下一步", "判断下一步", "最该推进哪", "该推进哪", "推进哪一件",
)
AMBIGUOUS_REQUESTS = (
    r"^(?:请|麻烦|帮我)?(?:先)?(?:优化|处理|完善|改进|看看|看一下)(?:一下)?(?:这个|那个|它|这东西|这个东西)?[。！!？?]?$",
    r"^(?:请|麻烦|帮我)?把(?:这个|那个|它|这东西|这个东西)(?:优化|处理|完善|改进)(?:一下)?[。！!？?]?$",
    r"^(?:请|麻烦|帮我)?继续(?:吧|一下)?[。！!？?]?$",
)
ORDINARY_TASK_TERMS = {
    "状态", "目标", "客户", "产品", "服务", "价格", "报价", "收费", "毛利", "竞品", "同行", "机制",
    "标题", "内容", "学习", "练习", "保存", "恢复", "复盘", "知识库", "工作台", "桥接", "skill", "风险",
}
COMPOUND_CONNECTORS = (
    "还是", "或者", "也想", "又想", "顺便", "也许", "也可能", "可能是", "随便哪个", "都行", "二选一", "两个都", "选一个",
)
NEGATED_TASK_TERMS: dict[str, tuple[str, ...]] = {
    "reasoning.clarify": ("澄清概念", "概念澄清", "问题定义", "定义问题", "澄清口径"),
    "governance.audit_skill": ("本地文件审查", "文件审查", "skill 审查", "审查", "扫描"),
    "business.pricing": ("定价", "报价", "价格", "套餐", "收费", "费用"),
    "business.customer": ("客户画像", "客户", "谁会买", "购买者", "用户需求"),
    "business.diagnose": ("诊断生意", "生意诊断", "诊断", "分析"),
    "product.define": ("产品", "prd", "mvp"),
    "research.benchmark": ("商业对标", "对标", "竞品", "同行", "benchmark"),
    "research.standard": ("历史案例", "历史类比", "案例类比", "同构案例", "过去案例"),
    "content.plan": ("做内容", "内容计划", "内容规划", "选题"),
    "content.hook": ("开头", "第一句话", "钩子", "hook"),
    "content.title": ("标题",),
    "content.script": ("脚本", "逐字稿", "正文逻辑", "文稿逻辑"),
    "content.resonate": ("共鸣", "受众立场", "传播性"),
    "personal.goal": ("宏大目标", "目标"),
    "personal.learning": ("学习计划", "学习", "练习"),
    "content.publish_check": ("发布风险", "发布检查", "检查发布", "检查", "审核"),
    "governance.knowledge": ("知识库治理", "治理体系", "目录治理", "知识库"),
    "governance.workbench": ("工作台", "唯一真源", "规范源"),
    "governance.bridge": ("桥接", "适配"),
    "debate.run": ("辩论", "讨论", "质询"),
}

KEYWORDS: dict[str, tuple[str, ...]] = {
    "runtime.status": (
        "状态", "进展", "status", "已确认事实", "未证实假设", "阻塞点", "停止条件", "未完成事项",
        "下一动作", "当前证据", "目前的证据", "项目现状", "事实汇总",
    ),
    "reasoning.clarify": (
        "澄清概念", "概念澄清", "概念边界", "概念混用", "这个概念", "这个词是什么意思",
        "术语是什么意思", "定义口径", "澄清口径", "统一口径", "问题定义", "定义问题",
        "问题边界", "问题陈述", "把问题说清", "问题到底是什么", "区分现象和假设", "讲明白",
        "成功的定义", "成功定义", "什么算成功",
    ),
    "business.explore": ("没想法", "没有想法", "没点子", "没有点子", "没有生意点子", "没生意点子", "没有创业点子", "创业点子", "做什么生意", "什么副业", "副业方向", "轻资产副业", "找个副业", "找方向", "适合我的生意", "可证伪的方向"),
    "business.diagnose": ("能不能做", "卖不动", "复购", "续费下降", "续费下滑", "流失", "退款", "商业模式", "生意诊断", "找出卡在哪里", "卡在哪里", "可证伪原因", "定位错", "卡住", "为什么失败", "改交付", "改产品"),
    "business.pricing": ("客户说贵", "定价", "定价测试", "报价", "降价", "价格", "套餐", "收费", "年包", "按次收费", "按席位收费", "毛利", "单位经济"),
    "business.customer": ("目标客户", "首批客户", "第一批", "最早客户", "早期客户", "明确客户", "客户定义", "客户是谁", "谁使用", "谁掏钱", "谁会买", "买单者", "付款人", "没人付费", "用户需求", "jtbd", "购买者", "付款者", "收窄客户", "收窄早期", "服务对象太宽", "访谈验证"),
    "research.benchmark": ("商业对标", "竞品", "同行", "学哪个账号", "对标分析", "benchmark", "同类公司", "同类服务", "当代案例", "仍在运营", "现实公司", "获客做法", "履约做法", "留存做法"),
    "research.standard": ("历史同构", "同构的案例", "历史上", "历史案例", "过去怎么解决", "过去哪些", "反复有效", "结构相似", "机制", "反例", "适用边界", "能否类推", "哪些奏效", "哪些失败", "找个标准", "standard"),
    "product.define": ("prd", "mvp", "产品经理", "功能优先级", "验收标准", "指标树", "产品需求", "做产品", "产品方向", "产品范围", "功能范围", "最小范围", "非目标", "实验待办", "发现版"),
    "content.plan": ("选题", "内容方向", "内容角度", "内容计划", "证据计划", "事实锚点", "证明材料", "内容 brief", "可执行 brief", "系列内容", "做内容", "topic"),
    "content.hook": ("第一句话", "开场", "开头", "hook", "前3秒", "留不住"),
    "content.title": ("标题", "拟标题", "标题比较", "比较标题", "title"),
    "content.script": ("短视频稿", "文稿逻辑", "逻辑断点", "修改顺序", "逐字稿", "脚本", "逻辑衔接", "口播"),
    "content.resonate": ("共鸣", "戳中", "传播性", "完播", "受众情绪", "居高临下", "受众立场", "立场错位", "自嗨", "对应他们的处境", "最小调整"),
    "content.publish_check": ("发布检查", "检查发布", "发布风险", "能不能发", "准备发", "我要发", "敏感词", "导流", "私信引导", "广告", "隐私", "受限内容", "前后对比", "机器信号", "实质问题", "人工判断", "publish-check"),
    "personal.goal": ("十二周", "三个月目标", "成交目标", "目标定清", "目标不清", "澄清目标", "明确目标", "目标改成", "定义成可观察", "可观察结果", "可观察目标", "能验收", "验收的状态", "想变得更好", "目标是什么"),
    "personal.action": ("最小一步", "最小动作", "怕被拒绝", "名单却没发", "拖到", "拖延", "拖着", "迟迟没行动", "迟迟不", "做不动", "一直研究", "反复换方向", "不行动", "下一步行动", "制定行动", "贪快", "执行卡住"),
    "personal.learning": ("学会", "训练的练习", "设计练习", "评分量表", "评分标准", "点评录音", "反馈门", "系统学习", "学习计划", "复盘学习", "带我学习", "继续下一篇", "练习反馈", "刻意练习", "演练反馈"),
    "decision.record": ("记录为何选择", "记录决策", "决策记录", "复盘条件", "反转条件", "何时反转", "被否决选项", "选择依据", "做决定", "长期决策", "复盘决策"),
    "decision.save": ("保存当前", "保存一下", "诊断存档", "本地快照", "可恢复的快照", "可恢复快照", "快照预览", "落盘位置", "确认哈希", "save"),
    "decision.restore": ("接着上次", "恢复存档", "恢复上次", "读回", "读回来", "最近快照", "上周保存", "过期信息", "已经失效", "不要改文件", "restore"),
    "decision.report": ("决策报告", "项目复盘", "汇总复盘", "决策时间线", "实验结果", "实验输赢", "未决项", "仍未解决", "当季", "时间范围", "report"),
    "governance.knowledge": ("知识目录", "知识资产", "知识盘点", "盘点目录", "资产索引", "索引计划", "文件夹知识库", "知识库", "索引文件夹", "目录治理"),
    "governance.workbench": ("agent 工作台", "多端 agent", "单一真源", "唯一真源", "规范源", "薄适配层", "指令漂移", "版本矩阵", "升级与回退", "工作台"),
    "governance.bridge": ("skill 桥接", "多端桥接", "目标 agent", "旧 agent", "不同目录结构", "兼容性验证", "兼容矩阵", "桥接方案", "被多个 agent 发现", "bridge"),
    "governance.audit_skill": ("只读审计", "审计这个本地skill", "审计一下 skill", "审查本地 skill", "本地 skill", "下载命令", "提示注入", "权限风险", "脚本风险", "audit-skill", "skill 风险", "越权调用", "扫描 skill"),
    "debate.run": ("支持和反对", "不同立场", "各自论证", "独立论证", "互相质疑", "互相质询", "单一视角", "多 agent", "多角度讨论", "多轮讨论", "交叉质询", "保留给我决策", "debate"),
}


def load_registry(path: Path = DEFAULT_REGISTRY) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def contains_any(text: str, words: tuple[str, ...]) -> bool:
    return any(word.lower() in text for word in words)


def explicit_task(text: str, rows: list[dict]) -> str | None:
    aliases = sorted(
        ((alias.lower(), row["id"]) for row in rows for alias in row["aliases"] if alias not in {"/biz", "/biz intervene"}),
        key=lambda item: len(item[0]),
        reverse=True,
    )
    for alias, task_id in aliases:
        if re.search(rf"(?<!\S){re.escape(alias)}(?:\s|$)", text):
            return task_id
    return None


def unknown_command(text: str, rows: list[dict]) -> str | None:
    """Return an unregistered ASCII subcommand immediately following /biz."""
    match = re.search(r"(?<!\S)/biz\s+([a-z][a-z-]*)\b", text)
    if not match:
        return None
    known = {
        alias.lower().removeprefix("/biz ")
        for row in rows
        for alias in row["aliases"]
        if alias.lower().startswith("/biz ")
    }
    token = match.group(1)
    return None if token in known or token in NATURAL_ASCII_START else token


def semantic_text(text: str) -> str:
    """Remove the command token before classifying the request object."""
    return " ".join(COMMAND_RE.sub(" ", text).split())


def has_transaction_intent(text: str) -> bool:
    """Require both a monetary decision and a market actor or offer."""
    return contains_any(text, TRANSACTION) and contains_any(text, OFFER_OR_MARKET)


def describes_productized_offer(text: str) -> bool:
    """Recognize an offer description without exempting a direct build request."""
    offer_signal = contains_any(text, PRODUCTIZED_OFFER) or re.search(
        r"(?:我们|我|公司|团队).{0,16}(?:卖|销售|提供)", text
    )
    return bool(offer_signal) and not contains_any(text, DIRECT_BUILD_REQUEST)


def split_clauses(text: str) -> list[str]:
    """Split independent actions so one commercial clause cannot exempt another."""
    parts = re.split(
        r"[，,；;。！？?!]+|(?:但是|但|不过|另外|顺便|而不是|而是|只想|然后|之后)",
        text,
    )
    return [part.strip() for part in parts if part.strip()]


def clause_negates_task(task_id: str, text: str) -> bool:
    prefix = r"(?:不是要|不是|不要做|不要|别做|(?<!分)别|无需|不需要|不想|并非|不讨论|不检查|不分析|不研究)"
    suffix = r"(?:先)?(?:不改|不动|不用|不要|不需要|不讨论|不检查|不分析|不研究|已经定了)"
    return any(
        re.search(rf"{prefix}.{{0,16}}{re.escape(term)}", text)
        or re.search(rf"{re.escape(term)}.{{0,8}}{suffix}", text)
        for term in NEGATED_TASK_TERMS.get(task_id, ())
    )


def explicit_task_is_negated(task_id: str, text: str) -> bool:
    return any(clause_negates_task(task_id, clause) for clause in split_clauses(text))


def hard_scope_reason(text: str) -> str | None:
    """Return non-negotiable scope or safety exclusions before task routing."""
    if contains_any(text, HARM_RISK):
        return "clinical_or_mental_health_request"
    if contains_any(text, UNAUTHORIZED_DATA) or (
        re.search(r"(?:竞品|竞争对手|对手).{0,12}(?:后台|系统|账号)", text)
        and contains_any(text, ("导出", "客户资料", "客户名单", "下载数据"))
    ):
        return "unauthorized_access_or_data_exfiltration"
    if contains_any(text, MASS_OUTREACH):
        return "unsafe_mass_outreach"
    if contains_any(text, LEGAL_REPRESENTATION):
        return "legal_representation_or_filing"
    if contains_any(text, DESTRUCTIVE_BYPASS):
        return "destructive_operation_without_recovery_controls"
    if contains_any(text, ("直接支付", "替我付款", "直接转账")) or (
        contains_any(text, ("银行卡信息", "支付密码"))
        and contains_any(text, ("支付供应商", "直接付款", "直接支付", "直接转账"))
    ):
        return "financial_transaction_or_sensitive_credential_operation"
    if (
        contains_any(text, ("全仓", "满仓", "梭哈"))
        and contains_any(text, ("股票", "基金", "币", "期货"))
    ) or (
        contains_any(text, ("保证", "稳赚", "必赚"))
        and contains_any(text, ("收益", "赚", "回报"))
    ):
        return "high_risk_investment_instruction"
    return None


def is_contextual_intervention(text: str) -> bool:
    return contains_any(text, CONTEXT_REFERENCE) and contains_any(text, INTERVENTION_CHOICE)


def has_usable_intervention_case(text: str) -> bool:
    """Require concrete facts, constraints, or a deadline before autonomous intervention."""
    case_evidence = _count_true(
        contains_any(text, ("当前已知", "已知", "证据", "反馈", "访谈", "试卖", "试过", "实验", "付订金", "成交", "退款", "复购")),
        contains_any(text, ("预算", "成本", "容量", "限制", "只能", "必须", "不能", "还没", "未核", "截止", "期限")),
        bool(re.search(r"(?:今天|明天|周[一二三四五六日天]|月底|本周|下周|\d+[日天周月]内|\d+月\d+日)", text)),
        bool(re.search(r"\d+(?:人|家|元|%|次|条|单|小时|天|周|月)", text)),
    )
    next_step = contains_any(text, INTERVENTION_CHOICE) or contains_any(
        text, ("选择下一步", "请选下一步", "决定下一步", "下一步并", "下一项", "直接处理")
    )
    return case_evidence >= 1 and next_step


def has_project_identifier(text: str) -> bool:
    return bool(
        re.search(
            r"项目\s*(?:(?:id|编号|名称)\s*)?(?:是|为|[:：])?\s*[a-z][a-z0-9_-]{2,}",
            text,
            re.I,
        )
        or re.search(r"项目\s*[一-龥][一-龥a-z0-9_-]{1,}", text, re.I)
    )


def high_impact_clarification_reason(text: str) -> str | None:
    """Require exact scope and confirmation for ambiguous or external side effects."""
    if contains_any(text, HIGH_IMPACT_EXTERNAL):
        return "external_action_requires_scope_and_confirmation"
    if contains_any(text, SENSITIVE_DATA) and contains_any(
        text, ("联系", "收款", "发送", "群发", "导出", "登录")
    ):
        return "sensitive_data_or_credential_boundary"
    if contains_any(text, ("保存一下", "把它保存", "保存它")) and not contains_any(
        text, ("当前项目", "项目 id", "项目id", "快照", "handoff", "目标路径")
    ):
        return "save_target_or_project_missing"
    if contains_any(text, ("恢复上次", "上次那个项目", "恢复那个项目")) and not has_project_identifier(text):
        return "restore_project_identifier_missing"
    if (
        re.search(r"(?:检查|扫描|读取|盘点).{0,12}(?:文件夹|目录)", text)
        and contains_any(text, ("建成知识库", "建立知识库", "建知识库", "索引", "摄入"))
        and not re.search(r"(?:^|\s)/(?:[^\s，。；]+)", text)
        and not contains_any(text, ("指定目录", "获批目录", "明确批准"))
    ):
        return "knowledge_root_or_allowlist_missing"
    if contains_any(text, ("审计一下 skill", "审查一下 skill", "扫描一下 skill")) and contains_any(
        text, ("直接删", "直接改", "自动修复", "立即隔离")
    ):
        return "audit_scope_and_destructive_action_conflict"
    return None


def is_underspecified_request(text: str) -> bool:
    return any(re.fullmatch(pattern, text) for pattern in AMBIGUOUS_REQUESTS)


def explicit_path_present(text: str) -> bool:
    return bool(
        re.search(r"(?:^|\s)/(?:[^\s，。；]+)", text)
        or re.search(r"\b[a-z]:\\[^\s，。；]+", text, re.I)
    )


def out_of_scope_reason(text: str) -> str | None:
    """Return positive clinical, sports, or software exclusions."""
    clauses = split_clauses(text)
    health_signal = contains_any(text, HEALTH_DISTRESS)
    athletic_signal = contains_any(text, ATHLETIC_SUBJECT)
    for clause in clauses:
        commercial_clause = has_transaction_intent(clause) or describes_productized_offer(clause)
        if (
            health_signal
            and contains_any(clause, HEALTH_ACTIONS)
            and not commercial_clause
            and not contains_any(text, ("不是心理问题", "非心理问题", "不做心理诊断"))
        ):
            return "clinical_or_mental_health_request"
        if (
            athletic_signal
            and contains_any(clause, TECHNIQUE_REQUEST)
            and not commercial_clause
        ):
            return "non_business_sports_benchmark"
        if (
            contains_any(clause, SOFTWARE_ARTIFACT)
            and contains_any(clause, IMPLEMENTATION_ACTION)
            and not commercial_clause
        ):
            return "software_implementation_request"
    if athletic_signal and contains_any(text, ("竞技表现", "竞技成绩", "只按竞技", "谁更伟大", "运动表现排名")):
        return "non_business_sports_benchmark"
    if health_signal and (
        bool(re.search(r"(?:判断|看看|确认).{0,12}(?:是不是|是否).{0,12}(?:症|疾病|障碍)", text))
        or bool(re.search(r"是不是.{0,12}(?:症|疾病|障碍)", text))
        or (
            contains_any(text, ("血常规", "检查结果", "症状", "持续发热", "感染"))
            and contains_any(text, ("判断", "诊断", "最可能", "治疗方案", "治疗", "用药"))
        )
    ):
        return "clinical_or_mental_health_request"
    return None


def positive_domain_out_of_scope_reason(text: str) -> str | None:
    """Return explicit non-business request families before lexical routing."""
    travel_object = contains_any(
        text,
        ("机场", "火车站", "高铁站", "航班", "机票", "火车票", "高铁票", "网约车", "出租车", "酒店", "行程"),
    ) or bool(re.search(r"从.{1,24}到.{1,24}(?:的车|打车|叫车|乘车)", text))
    travel_action = bool(
        re.search(r"(?:帮我|替我|给我|请).{0,12}(?:订|预订|预约|叫|下单)", text)
        or re.search(r"(?:订|预订|预约|叫).{0,8}(?:车|票|酒店|航班)", text)
    )
    commercial_travel = describes_productized_offer(text) or contains_any(
        text, ("客户", "用户", "产品", "服务", "业务", "商业化", "订单流程", "下单流程")
    )
    if travel_object and travel_action and not commercial_travel:
        return "non_business_travel_booking"

    translation_action = bool(re.search(r"(?:翻译|译)(?:成|为|一下|这段|本文)|(?:把|将).{0,12}翻译", text))
    commercial_localization = contains_any(
        text,
        (
            "产品", "客户", "用户", "营销", "广告", "品牌", "市场", "文案", "产品页", "落地页",
            "本地化", "发布检查", "平台规则", "敏感词", "导流", "转化",
        ),
    )
    if translation_action and not commercial_localization:
        return "pure_translation_request"
    relationship_subject = contains_any(text, ("伴侣", "对象", "男朋友", "女朋友", "婚姻", "感情", "分手"))
    relationship_decision = contains_any(text, ("谁更爱", "爱不爱", "要不要分手", "该不该分手", "替我决定", "感情分析"))
    if relationship_subject and relationship_decision and not contains_any(text, BUSINESS):
        return "relationship_advice_outside_scope"
    image_object = contains_any(text, ("图片", "照片", "证件照", "头像", "海报", "上传的图", "上传的照片"))
    image_edit = contains_any(text, ("换背景", "背景换成", "去掉反光", "去反光", "磨皮", "裁剪", "修图", "抠图", "调色"))
    commercial_image = contains_any(text, ("商品图", "广告素材", "品牌", "营销", "内容选题", "发布策略", "转化"))
    if image_object and image_edit and not commercial_image:
        return "image_editing_request"
    return None


def generic_ambiguity_reason(text: str) -> str | None:
    """Recognize in-domain request shells that lack a discriminating object or goal."""
    if is_underspecified_request(text):
        return "object_goal_or_acceptance_missing"
    if (
        contains_any(text, ("这个项目", "那个项目", "项目下一步"))
        and contains_any(text, ("看看", "看一下", "下一步", "怎么办"))
        and not contains_any(text, CONTEXT_REFERENCE)
        and not contains_any(
            text,
            (
                "客户", "证据", "预算", "限制", "目标", "实验", "访谈", "报价",
                "已确认", "事实", "假设", "猜测", "阻塞", "卡点", "停止条件", "检查点",
            ),
        )
    ):
        return "project_context_missing"
    if (
        contains_any(text, ("这段内容", "这个内容", "这篇内容", "这个文案"))
        and contains_any(text, ("改好", "改得更好", "优化一下", "完善一下", "处理一下"))
        and not contains_any(text, ("受众", "读者", "平台", "标题", "开头", "逻辑", "共鸣", "发布"))
    ):
        return "content_object_or_outcome_missing"
    if contains_any(text, ("复盘一下", "帮我复盘", "做个复盘")) and not contains_any(
        text, ("项目", "决策", "实验", "学习", "时间范围", "本周", "本月", "季度", "今年")
    ):
        return "review_object_or_time_scope_missing"
    if (
        contains_any(text, ("行业对标", "做个对标", "做一下对标", "照着那家", "照最好", "照着最好"))
        and not contains_any(text, ("比较", "对比", "获客", "履约", "留存", "成本", "机制", "想学", "搬到", "迁移"))
    ):
        return "benchmark_outcome_or_scope_missing"
    if contains_any(text, ("争一争", "不同角度争", "找几个人", "多方讨论")) and not contains_any(
        text, ("是否", "要不要", "方案一", "方案二", "证据", "成本", "访谈", "决定", "季度")
    ):
        return "debate_case_or_decision_missing"
    if contains_any(text, ("电脑里的知识库", "电脑里知识库", "整理知识库")) and not explicit_path_present(text):
        return "knowledge_root_or_operation_missing"
    if contains_any(text, ("这个标题能发吗", "标题可以发吗", "标题能不能发")) and not contains_any(
        text, ("平台", "地区", "原文", "标题是", "敏感词", "广告", "隐私")
    ):
        return "title_or_publish_scope_missing"
    if (
        "skill" in text
        and contains_any(text, ("所有agent", "所有 agent", "多个agent", "多个 agent", "各个agent", "各个 agent"))
        and contains_any(text, ("接到", "接入", "连接", "适配", "桥接", "链接和配置", "配置该改"))
        and not explicit_path_present(text)
    ):
        return "bridge_root_targets_or_write_scope_missing"
    if (
        contains_any(text, ("记下来", "记录下来", "正式记录"))
        and contains_any(text, ("应该停止", "应该暂停", "决定停止", "决定暂停", "停止低价", "暂停低价"))
        and not contains_any(text, ("依据", "证据", "备选", "反转条件", "复盘", "复查", "日期"))
    ):
        return "decision_evidence_or_review_missing"
    return None


def _count_true(*values: bool) -> int:
    return sum(bool(value) for value in values)


def composite_task_signals(task_id: str, text: str) -> tuple[list[str], bool, bool]:
    """Return deduplicated feature groups, strong support, and primary speech-act support."""
    signals: list[str] = []

    def mark(name: str, condition: bool) -> bool:
        if condition:
            signals.append(name)
        return condition

    strong = False
    primary = False
    if task_id == "runtime.status":
        intent = mark("intent:status_summary", contains_any(text, ("汇总", "整理", "列出", "查看", "当前", "现状")))
        fields = _count_true(
            contains_any(text, ("已确认", "确认的事实", "当前证据")),
            contains_any(text, ("假设", "猜测", "未决")),
            contains_any(text, ("阻塞", "卡点")),
            contains_any(text, ("下一步", "下一动作", "检查点")),
            contains_any(text, ("停止条件", "何时停止")),
        )
        mark("output:status_fields", fields >= 2)
        strong = intent and fields >= 2
        primary = strong and contains_any(text, ("汇总", "整理", "列出", "查看"))
    elif task_id == "reasoning.clarify":
        term = mark(
            "object:ambiguous_term",
            contains_any(text, ("概念", "术语", "口径", "边界", "这个词", "混用"))
            or contains_any(text, ("问题定义", "定义问题", "把问题说清", "区分现象", "现象和假设"))
            or bool(re.search(r"有人.{0,18}有人", text))
            or bool(re.search(r"[“\"]([^”\"]{2,24})[”\"].{0,24}(?:讲清楚|说清楚|定义|边界)", text)),
        )
        output = mark(
            "output:clarification",
            contains_any(text, ("说清楚", "说清", "讲清楚", "讲清", "界定", "区分", "定义", "可观察指标", "真正要回答", "决策问题", "分别指")),
        )
        strong = term and output
        primary = strong
    elif task_id == "business.explore":
        no_direction = mark(
            "intent:find_direction",
            bool(re.search(r"(?:没有|还没|尚未|未有|不清楚).{0,10}(?:方向|点子|想法|生意)", text))
            or bool(re.search(r"(?:找|探索|想找).{0,10}(?:小生意|副业|生意方向|创业方向|机会)", text))
            or bool(re.search(r"(?:围绕|利用).{0,12}(?:找机会|探索机会)", text)),
        )
        resources = mark(
            "slot:constraints_resources",
            contains_any(text, ("每周", "预算", "资金", "时间", "会做", "擅长", "认识", "能联系", "能接触", "不想招人")),
        )
        access = mark("slot:customer_access", contains_any(text, ("店主", "老板", "客户", "工厂", "社群", "渠道", "联系")))
        strong = no_direction and contains_any(text, ("生意", "副业", "创业")) and (resources or access)
        primary = no_direction
    elif task_id == "business.diagnose":
        anomaly = mark(
            "object:business_anomaly",
            contains_any(text, ("下降", "下滑", "掉到", "卖不动", "流失", "退款", "签约率", "转化率", "复购", "续费", "没询盘")),
        )
        causal = mark(
            "intent:causal_diagnosis",
            contains_any(text, ("原因", "断在哪", "卡在哪里", "最可能", "证伪", "定位", "为什么", "问题出在", "哪里出了问题", "哪里出问题", "最该验证", "验证的环节"))
            or bool(re.search(r"(?:请|帮我|先|想|要).{0,8}诊断|诊断.{0,8}(?:生意|业务|原因|问题)", text)),
        )
        test = mark("output:falsifiable_test", contains_any(text, ("测试", "实验", "证伪", "证据缺口", "排除")))
        strong = anomaly and causal
        primary = strong and (test or contains_any(text, ("先找", "找出", "判断")))
    elif task_id == "business.pricing":
        market = mark("slot:offer_or_customer", contains_any(text, OFFER_OR_MARKET) or describes_productized_offer(text))
        peer_compare = contains_any(text, ("公司", "同行", "服务商", "机构")) and contains_any(text, ("比较", "对比", "找出", "研究"))
        decision = mark(
            "intent:pricing_decision",
            bool(re.search(r"(?:怎么|如何|是否|要不要|应该|该|设计|测试|比较|选择).{0,12}(?:定价|报价|价格|收费|套餐|降价|年包|按次)", text))
            or bool(re.search(r"(?:定价|报价|价格|收费|套餐|降价|年包|按次).{0,12}(?:怎么|如何|是否|测试|比较|选择|贵|高)", text)),
        )
        strong = market and decision and (
            not peer_compare or contains_any(text, ("定价", "报价", "价格", "套餐", "降价", "年包", "按次"))
        )
        primary = strong and not peer_compare
    elif task_id == "business.customer":
        roles = _count_true(
            bool(re.search(r"(?:谁|由谁|护士长|员工|学员|医生|妻子|丈夫|成员|团队).{0,12}(?:使用|操作|执行|每天用|实际用)", text))
            or contains_any(text, ("使用者", "实际使用者", "每天用的是")),
            bool(re.search(r"(?:谁|院办|院长|伴侣|家长|采购|妻子|丈夫).{0,12}(?:购买|采购|决定|下单|批准|付费)", text))
            or contains_any(text, ("购买决策者", "决定是否付费", "决定买不买")),
            bool(re.search(r"(?:谁|财务|预算).{0,8}(?:付款|付费|买单|出钱|来自)", text)),
            bool(re.search(r"(?:谁|护士|患者|团队).{0,8}(?:受益|获益|得到)", text)),
            contains_any(text, ("推荐者", "影响者", "介绍人", "转介绍")),
        )
        mark("object:customer_roles", roles >= 2)
        selection = mark(
            "intent:customer_selection",
            contains_any(text, ("分清", "界定", "收窄", "最早客户", "首批客户", "访谈对象", "客户定义", "谁会买", "谁掏钱", "瞄准谁", "先确定早期", "先确定谁")),
        )
        strong = (roles >= 2 and selection) or contains_any(text, ("收窄早期客户", "形成客户定义和访谈测试"))
        primary = strong
    elif task_id == "research.benchmark":
        compare = mark(
            "intent:compare_real_peers",
            contains_any(text, ("比较", "对比", "找", "找出", "研究", "对标"))
            and contains_any(text, ("公司", "同行", "服务商", "账号", "机构", "同类服务", "现实案例", "真实案例")),
        )
        dimensions = mark(
            "slot:comparison_dimensions",
            contains_any(text, ("获客", "触达", "履约", "交付", "留存", "复购", "收费", "计价", "客户", "信任", "成本", "现金流", "续约")),
        )
        transfer = mark(
            "output:transferable_mechanism",
            contains_any(text, ("搬到", "迁移", "照搬", "不复制", "可学习", "值得做", "借鉴", "能学", "适用", "机制")),
        )
        case_scope = mark("slot:real_case_scope", contains_any(text, ("现实案例", "真实案例", "当代案例")))
        strong = compare and (dimensions or transfer or case_scope)
        primary = strong and contains_any(text, ("比较", "对比", "找出", "研究"))
    elif task_id == "research.standard":
        structural = mark("intent:historical_analogue", contains_any(text, ("历史", "过去", "同构", "结构相似", "类推")))
        limits = mark("output:mechanism_limits", contains_any(text, ("反例", "适用边界", "哪些奏效", "哪些失败", "为什么失效", "为何失效", "机制")))
        strong = structural and limits
        primary = strong
    elif task_id == "content.plan":
        content = mark("object:content_series", contains_any(text, ("内容", "系列", "三期", "一个月", "选题")))
        planning = mark(
            "intent:plan_angles",
            contains_any(text, ("排角度", "角度排序", "内容方向", "证据计划", "事实锚点", "内容计划", "brief", "先排")),
        )
        strong = content and planning
        primary = strong
    elif task_id == "content.title":
        title = mark("object:title", "标题" in text)
        create = mark(
            "intent:create_or_compare_title",
            bool(
                re.search(r"(?:想|拟|起|写|给|比较|重做).{0,10}标题|标题.{0,12}(?:比较|排序|拟定|怎么写|怎样写|如何写|该写)", text)
            ),
        )
        strong = title and create and not contains_any(text, ("能发吗", "可以发吗", "能不能发"))
        primary = strong
    elif task_id == "content.script":
        script_object = mark("object:script", contains_any(text, ("口播", "短视频稿", "文稿", "逐字稿", "脚本")))
        inspect = mark(
            "intent:inspect_argument_flow",
            contains_any(text, ("论证断点", "逻辑断点", "流失的位置", "会流失", "修改顺序", "逻辑衔接"))
            and contains_any(text, ("标出", "找出", "检查", "判断", "请")),
        )
        bounded = mark("output:bounded_revision", contains_any(text, ("修改顺序", "不要重写", "不直接重写", "最小调整")))
        strong = script_object and inspect
        primary = strong and bounded
    elif task_id == "content.resonate":
        audience = mark("slot:audience_situation", contains_any(text, ("读者", "受众", "家长", "他们", "用户处境", "风险处境")))
        stance = mark(
            "intent:stance_gap",
            contains_any(text, ("处境", "没被看见", "没有站在", "站在他们", "担心", "害怕", "情绪", "立场", "叙述立场", "教训人", "自我介绍", "自嗨")),
        )
        edit = mark("output:minimum_edit", contains_any(text, ("最少改动", "最小改动", "最小修改", "最小调整", "最小修改建议", "哪些句子", "找出", "只判断", "不要重写")))
        strong = audience and stance and edit
        primary = strong
    elif task_id == "personal.goal":
        desired = mark("object:desired_change", contains_any(text, ("目标", "愿望", "想在", "三个月", "十二周", "今年")))
        observable = mark(
            "intent:observable_goal",
            contains_any(text, ("可观察", "可验收", "能验收", "结果指标", "目标卡", "有边界", "判断是否完成")),
        )
        constraints = mark("slot:baseline_constraints", contains_any(text, ("目前", "现状", "每周", "从零", "最多", "不能", "不想")))
        strong = desired and observable and constraints
        primary = strong
    elif task_id == "personal.action":
        goal_ready = mark(
            "slot:observable_goal",
            contains_any(text, ("可观察目标", "目标是", "周一前", "周二前", "周三前", "周四前", "周五前", "周末前"))
            or bool(re.search(r"(?:今天|明天|本周|周[一二三四五六日天]).{0,12}\d+(?:位|个|次|条|单)", text)),
        )
        failed_attempt = mark(
            "evidence:failed_attempt",
            contains_any(text, ("没有发出", "没发出", "没有行动", "没行动", "一直修改", "拖到", "打开通讯录", "写完名单")),
        )
        friction = mark(
            "object:action_friction",
            contains_any(text, ("担心被拒绝", "怕被拒绝", "最担心", "卡在", "一直研究", "反复修改", "拖延")),
        )
        next_action = mark(
            "output:next_action",
            contains_any(text, ("下一动作", "下一步", "最小一步", "最小动作", "最早断点", "立即动作", "今天先做")),
        )
        strong = goal_ready and failed_attempt and friction and next_action
        primary = strong
    elif task_id == "personal.learning":
        performance = mark(
            "object:target_performance",
            contains_any(text, ("学会", "能独立", "交付表现", "做出", "实际用途", "按表现")),
        )
        training = mark("intent:training_design", contains_any(text, ("训练", "练习", "安排训练", "评分", "量表")))
        feedback = mark("slot:baseline_feedback", contains_any(text, ("现在会", "目前只会", "基础", "反馈", "点评", "指出一个", "真实素材")))
        strong = performance and training and feedback
        primary = strong
    elif task_id == "decision.record":
        decision = mark(
            "object:made_decision",
            contains_any(text, ("已经决定", "我们决定", "口头同意", "形成结论", "选择了", "暂停", "放弃", "先服务")),
        )
        governance = mark(
            "intent:record_reversal",
            contains_any(text, ("反转条件", "复盘条件", "恢复的条件", "若", "如果", "复查", "约定"))
            and contains_any(text, ("复盘", "恢复", "反转", "复查", "日期", "月", "周")),
        )
        evidence = mark("slot:decision_evidence", contains_any(text, ("依据", "证据", "成本", "访谈", "备选", "替代方案", "毛利")))
        strong = decision and governance and evidence
        primary = strong
    elif task_id == "decision.save":
        save = mark(
            "intent:persist_snapshot",
            contains_any(text, ("保存", "快照", "存档", "handoff", "下次会话", "丢掉证据链")),
        )
        preview = mark("output:preview_target_checksum", _count_true(
            contains_any(text, ("预览", "哪些字段", "保存哪些字段")),
            contains_any(text, ("目标位置", "写到哪里", "落盘位置", "目标路径")),
            contains_any(text, ("校验", "确认哈希", "确认后", "等我确认")),
        ) >= 2)
        project = mark("slot:project_or_handoff", has_project_identifier(text) or contains_any(text, ("当前判断", "本轮诊断", "handoff", "结论已经形成")))
        strong = save and preview and project
        primary = strong
    elif task_id == "decision.restore":
        restore = mark(
            "intent:restore_snapshot",
            bool(re.search(r"(?:恢复|读回|接着).{0,18}(?:保存|存档|快照|版本|项目|状态)", text))
            or bool(re.search(r"(?:从|按).{0,16}(?:保存|存档|快照|版本).{0,12}恢复", text)),
        )
        project = mark("slot:project", has_project_identifier(text) or contains_any(text, ("上次保存", "旧快照", "已保存版本")))
        freshness = mark("output:staleness_next", contains_any(text, ("过期", "陈旧", "失效", "今天的事实", "下一步", "新鲜度")))
        strong = restore and project and freshness
        primary = strong
    elif task_id == "governance.knowledge":
        knowledge_object = mark(
            "object:knowledge_collection",
            contains_any(text, ("知识库", "知识目录", "知识资产", "文件夹知识", "资料库", "笔记库", "这个目录", "文件目录")),
        )
        root = mark("slot:exact_root", explicit_path_present(text) or contains_any(text, ("指定目录", "获批目录", "范围只限")))
        inventory = mark(
            "intent:knowledge_inventory",
            contains_any(text, ("只读清单", "只读盘点", "盘点", "清单", "重复", "来源不明", "过期资料", "索引", "版本规则", "版本冲突", "敏感风险", "摄取计划")),
        )
        strong = (knowledge_object or root) and root and inventory
        primary = strong
    elif task_id == "governance.workbench":
        consumers = mark("slot:multiple_agents", contains_any(text, ("多端", "三套 agent", "多个 agent", "消费者", "同时服务", "内部网页助手", "离线检索器", "sales-agent", "research-agent", "ops-agent")))
        canonical = mark("slot:canonical_source", contains_any(text, ("唯一源", "唯一真源", "单一真源", "规范源", "规范源固定", "canonical")))
        governance = mark("output:ownership_version_rollback", contains_any(text, ("所有权", "维护责任", "源映射", "适配契约", "适配器契约", "薄适配层", "版本矩阵", "回滚", "回退")))
        strong = consumers and canonical and governance
        primary = strong
    elif task_id == "governance.bridge":
        source = mark("slot:canonical_root", explicit_path_present(text) or contains_any(text, ("核心 skill", "核心库", "规范源", "源")))
        targets = mark("slot:target_agents", contains_any(text, ("目标端", "目标 agent", "旧 agent", "codex", "claude", "端 a", "端 b")))
        bridge = mark("intent:bridge_compatibility", contains_any(text, ("桥接", "接入", "连接", "发现", "清单文件", "兼容", "适配到", "适配给", "每端")))
        strong = source and targets and bridge
        primary = strong
    elif task_id == "governance.audit_skill":
        skill = mark("object:skill_path", "skill" in text and (explicit_path_present(text) or contains_any(text, ("本地 skill", "第三方 skill", "skill 目录"))))
        audit = mark("intent:read_only_audit", contains_any(text, ("只读", "审计", "检查", "核对实际文件", "文件证据", "不执行")))
        risk = mark("output:risk_findings", contains_any(text, ("权限", "脚本", "凭据", "上传", "外部地址", "提示注入", "风险等级", "修复建议", "越权")))
        strong = skill and audit and risk
        primary = strong
    elif task_id == "debate.run":
        positions = mark("intent:independent_positions", contains_any(text, ("不同立场", "多方", "独立角色", "独立分析", "独立论证", "分别论证", "各自论证", "支持和反对")))
        challenge = mark("output:cross_challenge", contains_any(text, ("互相挑战", "互相质疑", "互相质询", "交叉质询", "证据互相冲突")))
        decision = mark("slot:decision_question", contains_any(text, ("是否", "要不要", "决定留给我", "最后决定", "供我选择", "未来一个季度")))
        strong = positions and challenge and decision
        primary = strong
    return signals, strong, primary


def score_tasks(text: str, rows: list[dict]) -> list[dict]:
    registry_ids = {row["id"] for row in rows}
    business_context = contains_any(text, BUSINESS)
    scored: list[dict] = []
    for task_id, words in KEYWORDS.items():
        if task_id not in registry_ids:
            continue
        eligible_clauses = []
        hits = []
        for clause in split_clauses(text):
            if clause_negates_task(task_id, clause):
                continue
            eligible_clauses.append(clause)
            hits.extend(word for word in words if word.lower() in clause)
        if task_id == "runtime.status" and contains_any(text, ("下一步行动", "制定行动")):
            hits = [hit for hit in hits if hit != "下一步"]
        if task_id == "runtime.status" and contains_any(
            text, ("最小一步", "最小动作", "怕被拒绝", "迟迟没行动", "执行卡住")
        ):
            hits = [hit for hit in hits if hit not in {"停止条件", "下一动作"}]
        if task_id == "runtime.status" and contains_any(
            text, ("目标改成", "三个月后", "十二周内", "可观察目标", "验收的状态")
        ):
            hits = [hit for hit in hits if hit != "状态"]
        hits = list(dict.fromkeys(hits))
        task_text = " ".join(eligible_clauses)
        composite_signals, composite_strong, primary_request = composite_task_signals(task_id, task_text)
        if not hits and not composite_signals:
            continue
        ordinary_only = bool(hits) and all(hit.casefold() in ORDINARY_TASK_TERMS for hit in hits)
        if not hits:
            score = 0.45
        elif ordinary_only:
            score = 0.45
        else:
            score = min(0.65 + 0.08 * (len(hits) - 1), 0.86)
        mixed_offer_levers = contains_any(
            text,
            ("降价还是改交付", "定价还是改交付", "改产品还是定价", "产品还是定价", "价格还是产品"),
        )
        if task_id == "business.diagnose" and mixed_offer_levers:
            score = max(score, 0.98)
            primary_request = True
        if task_id == "business.pricing" and mixed_offer_levers:
            score = min(score, 0.83)
            composite_strong = False
            primary_request = False
        if task_id == "reasoning.clarify" and contains_any(
            text,
            (
                "澄清概念", "概念澄清", "概念边界", "定义口径", "澄清口径",
                "问题定义", "定义问题", "问题边界", "问题陈述", "把问题说清",
            ),
        ):
            score = max(score, 0.9)
        strong_intent = {
            "runtime.status": sum(
                signal in text for signal in ("已确认事实", "未完成事项", "停止条件", "项目现状", "当前证据")
            ) >= 2,
            "business.customer": contains_any(text, ("收窄", "使用者", "购买者", "付款者", "最早客户")),
            "research.benchmark": bool(
                re.search(r"(?:比较|对比|研究).{0,30}(?:公司|服务|同行)", text)
                and contains_any(text, ("获客", "履约", "留存", "复购", "运营"))
            ),
            "research.standard": contains_any(text, ("能否类推", "适用边界", "反例", "结构相似")),
            "product.define": (
                contains_any(text, ("产品", "prd", "mvp", "功能范围"))
                and contains_any(text, ("最小范围", "非目标", "实验待办", "验收标准", "指标树"))
            ),
            "content.plan": contains_any(text, ("内容 brief", "可执行 brief", "证明材料", "证据计划")),
            "content.hook": contains_any(text, ("开头 5 秒", "开头5秒", "第一句话", "前3秒")),
            "content.title": bool(re.search(r"(?:拟|比较|评估|重做).{0,8}标题|标题.{0,8}(?:比较|排序)", text)),
            "content.script": contains_any(text, ("论证链", "逻辑断点", "逐字稿", "行动号召")),
            "content.resonate": contains_any(text, ("居高临下", "立场错位", "受众立场", "只是我的自嗨")),
            "content.publish_check": (
                contains_any(text, ("准备发", "我要发", "能不能发", "发布检查", "检查发布", "审查发布"))
                and contains_any(text, ("广告", "隐私", "导流", "私信", "过审", "风险", "人工判断"))
            ),
            "personal.goal": (
                contains_any(text, ("目标", "愿望", "想在", "三个月", "十二周", "未来90天"))
                and contains_any(text, ("可观察", "能验收", "验收的状态", "检查点"))
            ),
            "personal.learning": (
                contains_any(text, ("练习", "演练"))
                and contains_any(text, ("评分", "反馈", "量表"))
            ),
            "decision.record": contains_any(text, ("被否决选项", "反转条件", "何时反转", "决策记录")),
            "decision.save": contains_any(text, ("快照预览", "可恢复的本地快照", "落盘位置", "确认哈希")),
            "decision.restore": contains_any(text, ("读回来", "读回", "恢复存档", "过期信息", "已经失效")),
            "decision.report": (
                contains_any(text, ("项目复盘", "决策报告", "决策时间线", "汇总"))
                and contains_any(text, ("决定", "实验", "未决", "未解决"))
            ),
            "governance.workbench": (
                contains_any(text, ("唯一真源", "单一真源", "规范源"))
                and contains_any(text, ("薄适配层", "消费者", "版本矩阵", "升级", "回退"))
            ),
            "governance.bridge": contains_any(text, ("不同目录结构", "兼容性验证", "兼容矩阵", "桥接方案")),
            "governance.audit_skill": (
                contains_any(text, ("本地 skill", "指定目录", "skill 目录"))
                and contains_any(text, ("权限", "脚本", "下载命令", "提示注入", "风险"))
            ),
            "debate.run": (
                contains_any(text, ("不同立场", "独立论证", "各自论证"))
                and contains_any(text, ("互相质疑", "互相质询", "交叉质询"))
            ),
        }.get(task_id, False)
        if strong_intent:
            score = max(score, 0.9)
        if composite_strong:
            score = max(score, 0.9)
        if primary_request:
            score = max(score, 0.96)
        elif len(composite_signals) >= 2:
            score = max(score, 0.6)
        if task_id == "debate.run" and composite_strong:
            score = max(score, 0.98)
        clarification_first = contains_any(
            text,
            ("问题定义", "定义问题", "把问题说清", "区分现象和假设", "区分事实、原因假设", "先不讨论解决方案"),
        )
        if task_id == "business.diagnose" and clarification_first:
            score = min(score, 0.78)
        restore_request = bool(
            re.search(r"(?:恢复|读回|接着).{0,18}(?:保存|存档|快照|版本|项目|状态)", text)
            or re.search(r"(?:从|按).{0,16}(?:保存|存档|快照|版本).{0,12}恢复", text)
        )
        if task_id == "runtime.status" and restore_request:
            score = min(score, 0.78)
        if business_context and hits and not ordinary_only and not primary_request and not composite_strong and (task_id.startswith(("business.", "product.", "content.", "research.")) or task_id == "personal.action"):
            score += 0.1
        signals = list(dict.fromkeys([*hits, *composite_signals]))
        scored.append(
            {
                "task_id": task_id,
                "score": round(min(score, 0.98), 2),
                "signals": signals,
                "primary": bool(primary_request),
                "strong": bool(composite_strong or strong_intent),
            }
        )
    return sorted(scored, key=lambda item: (-item["score"], item["task_id"]))


def first_ordered_task(text: str, rows: list[dict]) -> dict | None:
    """Honor an explicit 'first X, then Y' sequence when X maps cleanly."""
    match = re.search(
        r"(?:^|[，,；;。])?先(.+?)(?:[，,；;]?(?:再|然后)|之后(?:再)?|后(?:再|才))",
        text,
    )
    if not match:
        return None
    candidates = score_tasks(match.group(1), rows)
    return candidates[0] if candidates and candidates[0]["score"] >= 0.55 else None


def has_action_business_conflict(candidates: list[dict], dynamic: bool) -> bool:
    """Require intent clarification when intervention spans action and business work."""
    if not dynamic:
        return False
    action_supported = any(
        candidate["task_id"] == "personal.action" and candidate["score"] >= 0.65
        for candidate in candidates
    )
    other_supported = any(
        candidate["task_id"].startswith(BUSINESS_TASK_PREFIXES)
        and candidate["score"] >= 0.45
        and candidate.get("signals")
        for candidate in candidates
    )
    return action_supported and other_supported


def has_compound_task_conflict(text: str, candidates: list[dict]) -> bool:
    if contains_any(
        text,
        ("降价还是改交付", "定价还是改交付", "改产品还是定价", "产品还是定价", "价格还是产品"),
    ):
        return False
    if candidates and candidates[0]["task_id"] == "business.diagnose" and contains_any(
        text, ("最该验证", "验证的环节", "可证伪原因", "找出卡在哪里")
    ):
        return False
    task_ids = {candidate["task_id"] for candidate in candidates if candidate["score"] >= 0.45}
    if {"research.benchmark", "research.standard"}.issubset(task_ids) and bool(
        re.search(r"(?:现实|真实|当代).{0,24}历史|历史.{0,24}(?:现实|真实|当代)", text)
    ):
        return True
    if not contains_any(text, COMPOUND_CONNECTORS):
        return False
    explicit_alternative = contains_any(
        text,
        ("还是", "或者", "也可能", "可能是", "都行", "二选一", "选一个", "先做哪个"),
    )
    threshold = 0.45 if explicit_alternative else 0.65
    supported = [candidate for candidate in candidates if candidate["score"] >= threshold]
    if explicit_alternative and len({candidate["task_id"] for candidate in supported}) >= 2:
        return True
    families = {TASK_FAMILY.get(candidate["task_id"], candidate["task_id"]) for candidate in supported}
    if len(families) >= 2:
        return True
    if re.search(r"也许.+也许", text) and contains_any(
        text, ("定义", "澄清", "历史", "案例", "标准", "竞品", "同行")
    ):
        return True
    if supported:
        return False
    parallel_domains = (
        contains_any(text, ("内容", "选题", "标题")),
        contains_any(text, ("产品", "prd", "mvp")),
        contains_any(text, ("目标", "三个月")),
        contains_any(text, ("讲明白", "定义清楚", "澄清")),
        contains_any(text, ("历史案例", "历史同构", "类推")),
        contains_any(text, ("竞品", "同行", "当代案例")),
        contains_any(text, ("客户研究", "客户画像")),
        contains_any(text, ("定价", "报价", "套餐")),
    )
    return sum(parallel_domains) >= 2


def asks_for_route_question(text: str) -> bool:
    question_request = contains_any(text, ("只问一个", "问一个", "用一个问题", "一个能决定"))
    route_choice = contains_any(text, ("决定路线", "决定先后", "哪个更该先", "还是先", "研究路径"))
    return question_request and route_choice


def required_slot_clarification(task_id: str, text: str) -> str | None:
    """Stop a natural-language route when the leaf is clear but essential inputs are absent."""
    if task_id == "content.publish_check":
        material = contains_any(text, ("原文", "正文", "草稿", "稿子", "标题是", "内容是", "上文", "附件"))
        deictic_material = contains_any(text, ("这条内容", "这个内容", "这篇内容", "这条稿", "这个稿"))
        concrete_risk = contains_any(text, ("广告", "导流", "隐私", "私信", "价格", "用户照片", "受限内容", "敏感词"))
        if deictic_material and not material and not concrete_risk:
            return "publish_material_platform_or_risk_missing"
    elif task_id == "research.benchmark":
        comparison_scope = _count_true(
            contains_any(text, ("客户", "市场", "行业", "品类", "产品", "服务", "业务", "公司", "同行", "同类")),
            contains_any(text, ("获客", "交付", "履约", "留存", "收费", "定价", "成本", "信任", "机制")),
            contains_any(text, ("目标", "决定", "验证", "实验", "想学", "可学习", "借鉴", "迁移", "机制")),
        )
        if comparison_scope < 2:
            return "benchmark_scope_or_learning_goal_missing"
    elif task_id == "product.define":
        product_slots = _count_true(
            contains_any(text, ("用户", "客户", "使用者", "团队", "员工")),
            contains_any(text, ("问题", "痛点", "需求", "任务", "jtbd")),
            contains_any(text, ("场景", "流程", "什么时候", "在哪", "当前怎么做")),
        )
        if product_slots < 2:
            return "product_user_problem_or_scenario_missing"
    elif task_id == "content.hook":
        hook_slots = _count_true(
            contains_any(text, ("主题", "讲", "关于", "内容", "文章", "视频", "口播")),
            contains_any(text, ("受众", "读者", "客户", "店主", "老板", "家长")),
            contains_any(text, ("证据", "数据", "案例", "记录", "结果")),
            contains_any(text, ("平台", "小红书", "抖音", "视频号", "公众号")),
        )
        if hook_slots < 2:
            return "hook_topic_audience_or_evidence_missing"
    elif task_id == "personal.learning":
        learning_slots = _count_true(
            contains_any(text, ("学会", "能独立", "目标表现", "用于", "要做")),
            contains_any(text, ("目前", "现在", "只会", "基础", "不会")),
            contains_any(text, ("练习", "反馈", "点评", "评分", "量表", "真实素材")),
        )
        if learning_slots < 2:
            return "learning_performance_baseline_or_feedback_missing"
    return None


def explain_candidates(candidates: list[dict], selected_task: str | None) -> list[dict]:
    explained: list[dict] = []
    for index, candidate in enumerate(candidates):
        item = dict(candidate)
        item["selected"] = candidate["task_id"] == selected_task
        if item["selected"]:
            item["rejection_reason"] = None
            item["route_change_condition"] = "new safety conflict, explicit user correction, or stronger evidence for another task"
        else:
            item["rejection_reason"] = "lower supported score" if selected_task else "route remains ambiguous"
            item["route_change_condition"] = (
                "an explicit command or new evidence that makes this task the highest-confidence safe route"
            )
        item["rank"] = index + 1
        explained.append(item)
    return explained


def route(text: str, rows: list[dict] | None = None) -> dict:
    rows = rows or load_registry()
    normalized = " ".join(text.lower().split())
    explicit_intervene = "/biz intervene" in normalized
    request_text = semantic_text(normalized)
    contextual_intervention = is_contextual_intervention(request_text)
    dynamic = (
        explicit_intervene
        or contextual_intervention
        or re.search(r"(?<!\S)/biz(?:\s|$)", normalized) is not None
    )
    hard_excluded = hard_scope_reason(request_text)
    if hard_excluded:
        return {"state": "out_of_scope", "selected_task": None, "confidence": 1.0, "top_candidates": [], "needs_clarification": False, "reason": hard_excluded}
    high_impact_clarification = high_impact_clarification_reason(request_text)
    if high_impact_clarification:
        return {
            "state": "clarify",
            "selected_task": None,
            "confidence": 0.0,
            "top_candidates": [],
            "needs_clarification": True,
            "reason": high_impact_clarification,
        }
    excluded = out_of_scope_reason(request_text)
    if excluded:
        return {"state": "out_of_scope", "selected_task": None, "confidence": 1.0, "top_candidates": [], "needs_clarification": False, "reason": excluded}
    positive_excluded = positive_domain_out_of_scope_reason(request_text)
    if positive_excluded:
        return {"state": "out_of_scope", "selected_task": None, "confidence": 1.0, "top_candidates": [], "needs_clarification": False, "reason": positive_excluded}
    unsupported_command = unknown_command(normalized, rows)
    if unsupported_command:
        return {
            "state": "clarify",
            "selected_task": None,
            "confidence": 0.0,
            "top_candidates": [],
            "needs_clarification": True,
            "reason": "unknown_or_ambiguous_command",
        }
    direct = explicit_task(normalized, rows)
    if contextual_intervention and not direct:
        return {
            "state": "route",
            "selected_task": "runtime.intervene",
            "confidence": 0.9,
            "top_candidates": [
                {"task_id": "runtime.intervene", "score": 0.9, "signals": ["visible_context", "next_step_choice"]}
            ],
            "needs_clarification": False,
            "reason": "contextual_intervention_ready",
        }
    if explicit_intervene and has_usable_intervention_case(request_text):
        leaf_candidates = score_tasks(request_text, rows)[:3]
        top_leaf = leaf_candidates[0] if leaf_candidates else None
        top_two_gap = (
            round(top_leaf["score"] - leaf_candidates[1]["score"], 2)
            if top_leaf is not None and len(leaf_candidates) > 1
            else top_leaf["score"]
            if top_leaf is not None
            else 0.0
        )
        selected_leaf = (
            top_leaf["task_id"]
            if top_leaf is not None
            and top_leaf["score"] >= 0.65
            and top_two_gap >= 0.10
            else None
        )
        if selected_leaf is None:
            return {
                "state": "clarify",
                "selected_task": None,
                "confidence": top_leaf["score"] if top_leaf is not None else 0.0,
                "top_candidates": explain_candidates(leaf_candidates, None),
                "top_two_gap": top_two_gap,
                "needs_clarification": True,
                "reason": "intervention_leaf_below_confidence_threshold",
            }
        result = {
            "state": "route",
            "selected_task": "runtime.intervene",
            "confidence": top_leaf["score"],
            "top_candidates": explain_candidates(
                leaf_candidates,
                selected_leaf,
            ),
            "top_two_gap": top_two_gap,
            "needs_clarification": False,
            "reason": "intervention_case_ready",
            "recommended_leaf_task": selected_leaf,
        }
        return result
    if not direct and dynamic and any(re.fullmatch(pattern, request_text) for pattern in CASELESS_DYNAMIC_PATTERNS):
        return {
            "state": "clarify",
            "selected_task": None,
            "confidence": 0.0,
            "top_candidates": [],
            "needs_clarification": True,
            "reason": "no_usable_case",
        }
    if not request_text:
        return {
            "state": "clarify",
            "selected_task": None,
            "confidence": 0.0,
            "top_candidates": [],
            "needs_clarification": True,
            "reason": "no_usable_case",
        }
    ordered = first_ordered_task(request_text, rows)
    if direct:
        if explicit_task_is_negated(direct, request_text):
            return {
                "state": "clarify",
                "selected_task": None,
                "confidence": 0.0,
                "top_candidates": [{"task_id": direct, "score": 1.0, "signals": ["explicit_command"]}],
                "needs_clarification": True,
                "reason": "explicit_command_conflicts_with_request",
            }
        if ordered and ordered["task_id"] != direct:
            return {
                "state": "clarify",
                "selected_task": None,
                "confidence": 0.0,
                "top_candidates": [
                    {"task_id": direct, "score": 1.0, "signals": ["explicit_command"]},
                    ordered,
                ],
                "needs_clarification": True,
                "reason": "explicit_command_conflicts_with_sequence",
            }
        return {
            "state": "route",
            "selected_task": direct,
            "confidence": 1.0,
            "top_candidates": [{"task_id": direct, "score": 1.0, "signals": ["explicit_command"]}],
            "needs_clarification": False,
            "reason": "explicit leaf command",
        }
    if asks_for_route_question(request_text):
        return {
            "state": "clarify",
            "selected_task": None,
            "confidence": 0.0,
            "top_candidates": [],
            "needs_clarification": True,
            "reason": "user_requests_route_clarification",
        }
    ambiguity = generic_ambiguity_reason(request_text)
    if ambiguity:
        return {
            "state": "clarify",
            "selected_task": None,
            "confidence": 0.0,
            "top_candidates": [],
            "needs_clarification": True,
            "reason": ambiguity,
        }
    if ordered:
        return {
            "state": "route",
            "selected_task": ordered["task_id"],
            "confidence": max(ordered["score"], 0.65),
            "top_candidates": [ordered],
            "needs_clarification": False,
            "reason": "explicit_sequence_first",
        }
    candidates = score_tasks(request_text, rows)[:3]
    if not candidates:
        if contains_any(request_text, BUSINESS) or dynamic:
            return {"state": "clarify", "selected_task": None, "confidence": 0.0, "top_candidates": [], "needs_clarification": True, "reason": "no_supported_route"}
        return {"state": "out_of_scope", "selected_task": None, "confidence": 1.0, "top_candidates": [], "needs_clarification": False, "reason": "no_business_or_registered_task_signal"}
    top = candidates[0]
    gap = round(top["score"] - candidates[1]["score"], 2) if len(candidates) > 1 else top["score"]
    mixed_domain = has_action_business_conflict(candidates, dynamic)
    compound_conflict = has_compound_task_conflict(request_text, candidates)
    primary_dominates = bool(
        top.get("primary")
        and (len(candidates) == 1 or not candidates[1].get("primary"))
    ) or bool(top["task_id"] == "debate.run" and top.get("strong"))
    missing_slots = required_slot_clarification(top["task_id"], request_text)
    clarify = (
        top["score"] < 0.65
        or (len(candidates) > 1 and gap < 0.10 and not primary_dominates)
        or mixed_domain
        or compound_conflict
        or missing_slots is not None
    )
    reason = (
        "mixed_action_and_business_intent"
        if mixed_domain
        else "compound_task_intent"
        if compound_conflict
        else missing_slots
        if missing_slots
        else "low_confidence_or_close_candidates"
        if clarify
        else "highest_supported_route"
    )
    if explicit_intervene and not mixed_domain and not compound_conflict and top["score"] >= 0.55:
        return {
            "state": "route",
            "selected_task": "runtime.intervene",
            "confidence": top["score"],
            "top_candidates": explain_candidates(candidates, top["task_id"]),
            "recommended_leaf_task": top["task_id"],
            "top_two_gap": gap,
            "needs_clarification": False,
            "reason": "intervention_ready",
        }
    return {
        "state": "clarify" if clarify else "route",
        "selected_task": None if clarify else top["task_id"],
        "confidence": top["score"],
        "top_candidates": explain_candidates(candidates, None if clarify else top["task_id"]),
        "top_two_gap": gap,
        "needs_clarification": clarify,
        "reason": reason,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("text", nargs="?")
    parser.add_argument("--file", type=Path)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    args = parser.parse_args()
    if bool(args.text) == bool(args.file):
        parser.error("provide exactly one of text or --file")
    text = args.file.read_text(encoding="utf-8") if args.file else args.text
    print(json.dumps(route(text, load_registry(args.registry)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
