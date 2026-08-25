#!/usr/bin/env python3
"""Neutral-prompt regression tests for the deterministic pre-router."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))
from route_task import route  # noqa: E402

EVAL_CASES = SCRIPT_DIR.parent / "evals" / "routing-cases.jsonl"


class RouteTaskTests(unittest.TestCase):
    def assert_route(self, text: str, expected: str) -> None:
        result = route(text)
        self.assertEqual(result["state"], "route", result)
        self.assertEqual(result["selected_task"], expected, result)

    def assert_out(self, text: str, reason: str) -> None:
        result = route(text)
        self.assertEqual(result["state"], "out_of_scope", result)
        self.assertEqual(result["reason"], reason, result)

    def assert_intervene(self, text: str, expected_leaf: str) -> None:
        result = route(text)
        self.assertEqual(result["state"], "route", result)
        self.assertEqual(result["selected_task"], "runtime.intervene", result)
        self.assertEqual(result["recommended_leaf_task"], expected_leaf, result)

    def test_no_idea(self) -> None:
        self.assert_route("/biz 我想做生意，但是没有点子。", "business.explore")

    def test_natural_no_business_idea(self) -> None:
        self.assert_route("我没有生意点子，想找适合自己的方向。", "business.explore")

    def test_pricing(self) -> None:
        self.assert_route("客户说我的产品贵，我该直接降价吗？", "business.pricing")

    def test_explicit_product(self) -> None:
        self.assert_route("/biz product 用户是咖啡店老板，需要一份 PRD。", "product.define")

    def test_explicit_concept_clarification(self) -> None:
        self.assert_route(
            "/biz clarify 这里的客户到底指使用者、付费者还是批准者？",
            "reasoning.clarify",
        )

    def test_natural_concept_clarification(self) -> None:
        self.assert_route(
            "商业模式和盈利模式经常混用，请先澄清概念边界和定义口径。",
            "reasoning.clarify",
        )

    def test_problem_definition_precedes_diagnosis(self) -> None:
        self.assert_route(
            "先不要诊断原因，帮我把门店续费下降的问题定义清楚，区分现象和假设。",
            "reasoning.clarify",
        )

    def test_goal_definition_does_not_route_to_concept_clarification(self) -> None:
        self.assert_route(
            "把三个月成交十个客户的目标定义成可观察结果，并给第一个检查点。",
            "personal.goal",
        )

    def test_defined_business_problem_still_routes_to_diagnosis(self) -> None:
        self.assert_route(
            "门店续费下降，已有退订访谈和使用记录，帮我诊断原因并设计实验。",
            "business.diagnose",
        )

    def test_customer_selection_does_not_route_to_concept_clarification(self) -> None:
        self.assert_route(
            "医生使用、院长付款、患者受益，帮我选择最早客户并设计访谈。",
            "business.customer",
        )

    def test_explicit_publish_check(self) -> None:
        self.assert_route("/biz publish-check 检查这条小红书文案。", "content.publish_check")

    def test_negated_publish_intent_does_not_match_positive_phrase(self) -> None:
        for text in (
            "这个价格表还不准备发布，先帮我检查客户是否愿意买。",
            "这周计划不发布内容，先处理客户流失问题。",
        ):
            with self.subTest(text=text):
                result = route(text)
                self.assertNotEqual(result.get("selected_task"), "content.publish_check", result)
                self.assertFalse(
                    any(candidate["task_id"] == "content.publish_check" for candidate in result["top_candidates"]),
                    result,
                )

    def test_advertising_service_failure_is_business_diagnosis(self) -> None:
        result = route("我们的广告代投服务卖不动，已访谈三个客户，帮我找出卡在哪里。")
        self.assertEqual(result["state"], "route", result)
        self.assertEqual(result["selected_task"], "business.diagnose", result)
        self.assertFalse(
            any(candidate["task_id"] == "content.publish_check" for candidate in result["top_candidates"]),
            result,
        )

    def test_content_safety_check_does_not_require_the_word_publish(self) -> None:
        self.assert_route(
            "帮我检查这篇稿子有没有敏感词、导流和受限内容。",
            "content.publish_check",
        )

    def test_advertising_noun_alone_is_not_a_content_safety_check(self) -> None:
        result = route("广告代投服务已经卖了三个月，帮我分析客户为什么不续费。")
        self.assertEqual(result["selected_task"], "business.diagnose", result)
        self.assertFalse(
            any(candidate["task_id"] == "content.publish_check" for candidate in result["top_candidates"]),
            result,
        )

    def test_explicit_debate(self) -> None:
        self.assert_route("/biz debate 多角度审查这个商业定价。", "debate.run")

    def test_natural_multi_agent_discussion_routes_to_debate(self) -> None:
        self.assert_route(
            "请用多个 Agent 做多轮深度讨论和交叉质疑，判断这个生意要不要继续。",
            "debate.run",
        )

    def test_repeated_analysis_routes_to_one_action(self) -> None:
        self.assert_route(
            "我已经反复分析很久，今天只想推进一步。",
            "personal.action",
        )

    def test_explicit_knowledge(self) -> None:
        self.assert_route("/biz knowledge 建立文件夹知识库。", "governance.knowledge")

    def test_explicit_skill_audit(self) -> None:
        self.assert_route("/biz audit-skill 扫描这个本地 Skill。", "governance.audit_skill")

    def test_intervene_mixed_case_clarifies(self) -> None:
        result = route("线上课有退款，我一直研究竞品但拖延联系客户。 /biz intervene")
        self.assertEqual(result["state"], "clarify", result)
        self.assertTrue(result["needs_clarification"])
        self.assertEqual(result["reason"], "mixed_action_and_business_intent")

    def test_intervene_pricing_and_action_clarifies(self) -> None:
        result = route("客户说价格太贵，我又拖延不敢重新报价。 /biz intervene")
        self.assertEqual(result["state"], "clarify", result)
        self.assertEqual(result["reason"], "mixed_action_and_business_intent")

    def test_intervene_action_only_preserves_leaf_confidence(self) -> None:
        result = route("我一直拖延不行动，帮我直接介入。 /biz intervene")
        self.assertEqual(result["state"], "route", result)
        self.assertEqual(result["selected_task"], "runtime.intervene", result)
        self.assertEqual(result["recommended_leaf_task"], "personal.action", result)
        self.assertEqual(result["confidence"], result["top_candidates"][0]["score"], result)
        self.assertGreaterEqual(result["confidence"], 0.65, result)

    def test_intervene_low_leaf_confidence_clarifies_without_promotion(self) -> None:
        result = route(
            "/biz intervene 当前已知：试卖有12人付订金，包装成本还没核完，"
            "周五前必须决定是否接下首批订单。请选下一步并直接处理。"
        )
        self.assertEqual(result["state"], "clarify", result)
        self.assertIsNone(result["selected_task"], result)
        self.assertEqual(result["confidence"], result["top_candidates"][0]["score"], result)
        self.assertLess(result["confidence"], 0.65, result)
        self.assertEqual(result["reason"], "intervention_leaf_below_confidence_threshold", result)

    def test_intervene_preserves_supported_leaf_confidence(self) -> None:
        result = route(
            "/biz intervene 复购掉到18%，客户访谈显示上手太慢，"
            "请找出最可能的商业问题并设计可证伪实验。"
        )
        self.assertEqual(result["state"], "route", result)
        self.assertEqual(result["selected_task"], "runtime.intervene", result)
        self.assertEqual(result["recommended_leaf_task"], "business.diagnose", result)
        self.assertEqual(result["confidence"], result["top_candidates"][0]["score"], result)
        self.assertGreaterEqual(result["confidence"], 0.65, result)

    def test_clinical_is_out_of_scope(self) -> None:
        self.assert_out("我最近焦虑、睡不着，想知道自己是不是生病了。", "clinical_or_mental_health_request")

    def test_sports_benchmark_is_out_of_scope(self) -> None:
        self.assert_out("找三个篮球后卫作为技术对标。", "non_business_sports_benchmark")

    def test_software_api_is_out_of_scope(self) -> None:
        self.assert_out("把 SDK pricing API 的 price 改成 Decimal 并修复 TypeScript 测试。", "software_implementation_request")

    def test_explicit_command_does_not_bypass_clinical_scope(self) -> None:
        self.assert_out("/biz action 我焦虑失眠，帮我诊断是不是心理疾病。", "clinical_or_mental_health_request")

    def test_acute_self_harm_language_is_out_of_scope(self) -> None:
        self.assert_out("/biz action 我有轻生和自杀的想法。", "clinical_or_mental_health_request")

    def test_chest_pain_medication_is_out_of_scope(self) -> None:
        self.assert_out("/biz action 我胸痛三天，应该吃阿司匹林还是去医院？", "clinical_or_mental_health_request")

    def test_eating_disorder_treatment_is_out_of_scope(self) -> None:
        self.assert_out("/biz diagnose 我每天催吐，体重迅速下降，请判断是否需要治疗。", "clinical_or_mental_health_request")

    def test_business_words_do_not_bypass_software_scope(self) -> None:
        self.assert_out("修复定价 API 的 TypeScript 单元测试，Decimal 序列化有错误。", "software_implementation_request")

    def test_go_interface_bug_is_out_of_scope(self) -> None:
        self.assert_out("/biz pricing 修复 Go 接口的空指针错误。", "software_implementation_request")

    def test_react_page_is_out_of_scope(self) -> None:
        self.assert_out("/biz product 用 React 写一个登录页面并补端到端测试。", "software_implementation_request")

    def test_go_http_service_is_out_of_scope(self) -> None:
        self.assert_out("/biz product 用 Go 写一个 HTTP 服务，加入数据库迁移。", "software_implementation_request")

    def test_code_repair_service_pricing_routes(self) -> None:
        self.assert_route("/biz 我们卖代码修复服务，客户说价格贵，套餐怎么定？", "business.pricing")

    def test_business_words_do_not_bypass_sports_scope(self) -> None:
        self.assert_out("为产品找三个篮球后卫做技术对标。", "non_business_sports_benchmark")

    def test_baseball_technique_benchmark_is_out_of_scope(self) -> None:
        self.assert_out("/biz benchmark 找棒球投手做技术对标。", "non_business_sports_benchmark")

    def test_football_technique_is_out_of_scope(self) -> None:
        self.assert_out("/biz benchmark 分析C罗任意球和过人动作，给我模仿训练方案。", "non_business_sports_benchmark")

    def test_tennis_serve_is_out_of_scope(self) -> None:
        self.assert_out("/biz benchmark 对比三位网球选手的发球动作。", "non_business_sports_benchmark")

    def test_sports_course_pricing_routes(self) -> None:
        self.assert_route("/biz 我卖篮球后卫技术对标课程，客户说价格贵，应该怎样定价？", "business.pricing")

    def test_business_customer_anxiety_is_not_clinical(self) -> None:
        self.assert_route("客户焦虑价格太高，我的产品该怎么定价？", "business.pricing")

    def test_business_diagnosis_word_is_not_clinical(self) -> None:
        self.assert_route("诊断一下客户为什么觉得报价太贵。", "business.pricing")

    def test_medical_product_pricing_routes(self) -> None:
        self.assert_route("/biz 一款药物产品该如何定价和设计套餐？", "business.pricing")

    def test_non_clinical_pricing_diagnosis_routes(self) -> None:
        self.assert_route("客户对套餐价格很焦虑，帮我诊断定价问题而不是心理问题。", "business.pricing")

    def test_api_product_pricing_is_not_software_implementation(self) -> None:
        self.assert_route("API 产品该怎么定价和设计套餐？", "business.pricing")

    def test_exact_gap_threshold_routes(self) -> None:
        result = route("/biz 我的生意卖不动，但目标不清。")
        self.assertEqual(result["top_two_gap"], 0.10, result)
        self.assertEqual(result["state"], "route", result)

    def test_ordinary_skill_word_is_out_of_scope(self) -> None:
        self.assert_out("我的英语 speaking skill 很差，怎么练？", "no_business_or_registered_task_signal")

    def test_negated_explicit_audit_clarifies(self) -> None:
        result = route("/biz audit-skill 这不是本地文件审查，我只是问英语里的 skill 是什么意思。")
        self.assertEqual(result["state"], "clarify", result)
        self.assertEqual(result["reason"], "explicit_command_conflicts_with_request")

    def test_breathing_emergency_is_out_of_scope(self) -> None:
        self.assert_out("/biz action 我突然呼吸困难，应该服用什么药还是马上去急诊？", "clinical_or_mental_health_request")

    def test_psychiatric_harm_request_is_out_of_scope(self) -> None:
        self.assert_out("/biz diagnose 我听到有人命令我伤害别人，需要去精神科吗？", "clinical_or_mental_health_request")

    def test_poisoning_first_aid_is_out_of_scope(self) -> None:
        self.assert_out("/biz action 我误食了农药，现在头晕恶心，应该怎么急救？", "clinical_or_mental_health_request")

    def test_mental_health_service_pricing_routes(self) -> None:
        self.assert_route("/biz 抑郁治疗服务的客户说价格贵，套餐应该怎么定？", "business.pricing")

    def test_f1_technique_is_out_of_scope(self) -> None:
        self.assert_out("/biz benchmark 比较三名F1车手的弯道刹车技术，给我训练方案。", "non_business_sports_benchmark")

    def test_golf_technique_is_out_of_scope(self) -> None:
        self.assert_out("/biz benchmark 分析几位高尔夫球手的挥杆动作，教我模仿。", "non_business_sports_benchmark")

    def test_tennis_video_course_pricing_routes(self) -> None:
        self.assert_route("/biz 我卖网球发球技术对标视频课，客户说价格贵，应该如何定价？", "business.pricing")

    def test_vue_mysql_implementation_is_out_of_scope(self) -> None:
        self.assert_out("/biz product 用 Vue 开发管理后台并接入 MySQL。", "software_implementation_request")

    def test_rust_cli_implementation_is_out_of_scope(self) -> None:
        self.assert_out("/biz product 重构 Rust CLI，修掉内存泄漏。", "software_implementation_request")

    def test_java_course_pricing_routes(self) -> None:
        self.assert_route("/biz Java 单元测试课程客户说贵，套餐如何定价？", "business.pricing")

    def assert_explicit_conflict(self, text: str) -> None:
        result = route(text)
        self.assertEqual(result["state"], "clarify", result)
        self.assertEqual(result["reason"], "explicit_command_conflicts_with_request")

    def test_negated_benchmark_clarifies(self) -> None:
        self.assert_explicit_conflict("/biz benchmark 不要做商业对标，我只想记录这次决策。")

    def test_negated_learning_clarifies(self) -> None:
        self.assert_explicit_conflict("/biz learning 不是要学习计划，我只是想查看项目状态。")

    def test_negated_publish_check_clarifies(self) -> None:
        self.assert_explicit_conflict("/biz publish-check 不要检查发布风险，只帮我记录决策。")

    def test_negated_pricing_clarifies(self) -> None:
        self.assert_explicit_conflict("/biz pricing 只研究谁会买，不讨论费用。")

    def test_explicit_sequence_prioritizes_first_task(self) -> None:
        result = route("/biz 先恢复存档，再讨论产品定价。")
        self.assertEqual(result["state"], "route", result)
        self.assertEqual(result["selected_task"], "decision.restore", result)
        self.assertEqual(result["reason"], "explicit_sequence_first", result)

    def test_routing_eval_fixtures_match_router(self) -> None:
        import json

        rows = [json.loads(line) for line in EVAL_CASES.read_text(encoding="utf-8").splitlines() if line.strip()]
        for row in rows:
            with self.subTest(case_id=row["case_id"]):
                result = route(row["input"])
                expected_state = row.get("expected_state", "route")
                self.assertEqual(result["state"], expected_state, result)
                self.assertEqual(result["selected_task"], row.get("expected_task"), result)

    def test_unknown_subcommand_clarifies(self) -> None:
        result = route("/biz forecast 我们的课程客户说贵，怎么定价")
        self.assertEqual(result["state"], "clarify", result)
        self.assertEqual(result["reason"], "unknown_or_ambiguous_command", result)

    def test_unknown_subcommand_does_not_bypass_safety(self) -> None:
        self.assert_out("/biz forecast 我误食农药，应该怎么急救？", "clinical_or_mental_health_request")

    def test_unseen_cardiac_language_is_out_of_scope(self) -> None:
        self.assert_out("/biz action 我胸口压榨性疼痛还出冷汗，该吃药还是观察？", "clinical_or_mental_health_request")

    def test_commercial_context_does_not_exempt_care_request(self) -> None:
        self.assert_out("/biz diagnose 我的心理咨询工作室客户说抑郁，应该怎么治疗？", "clinical_or_mental_health_request")

    def test_unseen_athlete_technique_is_out_of_scope(self) -> None:
        self.assert_out("/biz benchmark 分析梅西盘带步频，给我专项练习。", "non_business_sports_benchmark")

    def test_unseen_software_stack_is_out_of_scope(self) -> None:
        self.assert_out("/biz product 帮我开发一个 Vue 登录组件并接入 PostgreSQL。", "software_implementation_request")

    def test_software_offer_does_not_exempt_separate_build_clause(self) -> None:
        self.assert_out("/biz product 我卖软件服务，顺便实现这个 React 页面。", "software_implementation_request")

    def test_fresh_command_boundary_regressions(self) -> None:
        expected = {
            "/biz 用户很多但没人付费，谁才是买单者": ("route", "business.customer"),
            "/biz 给新品短视频想一个标题": ("route", "content.title"),
            "/biz 把增长这个概念的统计口径和边界说清楚": ("route", "reasoning.clarify"),
            "/biz 我不是要定价，而是要找到最早客户": ("route", "business.customer"),
            "/biz 不要做内容，帮我制定下一步行动": ("route", "personal.action"),
            "/biz 不想诊断生意，只想明确一个可观察目标": ("route", "personal.goal"),
            "/biz 我不需要产品PRD，我要检查发布风险": ("route", "content.publish_check"),
            "/biz 先明确客户再设计产品": ("route", "business.customer"),
            "/biz 先复盘学习再决定下一步行动": ("route", "personal.learning"),
            "/biz sprint 帮我制定马拉松训练计划并提高配速": ("out_of_scope", None),
            "/biz dribble 教我提高篮球运球技术": ("out_of_scope", None),
            "/biz xrpc 帮我调试OpenAI SDK的API调用": ("out_of_scope", None),
        }
        for text, (state, task_id) in expected.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result["state"], state, result)
                self.assertEqual(result["selected_task"], task_id, result)

    def test_intervene_without_case_clarifies(self) -> None:
        result = route("/biz intervene 请根据当前情况替我选择下一步")
        self.assertEqual(result["state"], "clarify", result)
        self.assertEqual(result["reason"], "no_usable_case", result)

    def test_fresh_semantic_regressions(self) -> None:
        expected = {
            "我在成都做过五年采购，每周只有六小时，能接触本地小工厂，想找个轻资产副业方向。": ("route", "business.explore"),
            "给餐饮店做排班服务，试了三个月只有两家续费，我想找出卡在哪里。": ("route", "business.diagnose"),
            "我们一直把线索、客户和付费客户混在一起，请澄清概念和定义口径。": ("route", "reasoning.clarify"),
            "先不讨论解决方案，把库存损耗这个问题定义清楚，区分事实、原因假设和未知项。": ("route", "reasoning.clarify"),
            "做宠物寄养平台时，究竟谁使用、谁掏钱、谁最容易先成交？帮我界定。": ("route", "business.customer"),
            "我们卖财务顾问服务，面向初创公司老板，准备发小红书，先排内容角度和证据计划。": ("route", "content.plan"),
            "这段短视频稿讲会员复购，目标是让店主预约诊断；请画出逻辑断点和修改顺序。": ("route", "content.script"),
            "我想在十二周内验证能否独立卖出咨询服务，目前从未成交，每周可投入八小时。": ("route", "personal.goal"),
            "目标是今天联系五位旧客户，上次写完名单却没发，卡在怕被拒绝；给最小一步和停止条件。": ("route", "personal.action"),
            "我需要学会做B2B访谈，目前只会问满意度，下月要访谈十位采购，我能让销售经理点评录音。": ("route", "personal.learning"),
            "/biz intervene 复购掉到18%，客户访谈显示上手太慢，帮我选现在最值的一步并说明证据。": ("route", "runtime.intervene"),
            "我不想再泛泛讨论客户画像；同样交付成本下，年包和按次收费怎么做可逆测试？": ("route", "business.pricing"),
            "不要给我十个标题；请判断现有第一句话为何留不住餐饮老板，并给有证据支撑的开场。": ("route", "content.hook"),
            "不是帮我定宏大目标；我已经决定本周约三次访谈，但每次都拖到晚上，怎么迈出最小一步？": ("route", "personal.action"),
            "我不需要找当代同行，要找历史上与会员预付制挤兑风险同构的案例和边界。": ("route", "research.standard"),
            "别审计某个Skill，我要规划一个知识目录如何盘点、索引和控制版本。": ("route", "governance.knowledge"),
            "我不是要你替我拍板；请让支持和反对开新门店的两方先独立论证再互相质询。": ("route", "debate.run"),
            "先界定第一批愿意付费的客户，再讨论套餐价格；现在先做第一步。": ("route", "business.customer"),
            "先确定面向社区店主的内容角度和事实锚点，草稿出来后再做发布检查。": ("route", "content.plan"),
            "先诊断续费下滑的原因，证据不足时再找同行对标。": ("route", "business.diagnose"),
            "先只读审计这个本地Skill，确认风险后才讨论给其他代理建桥。": ("route", "governance.audit_skill"),
            "先把三个月成交目标定义成可观察结果，再拆今天的动作。": ("route", "personal.goal"),
            "先记录为何选择渠道A以及12月复盘条件，确认后再保存快照。": ("route", "decision.record"),
            "先建立谈判训练的练习与评分量表，之后再决定每天练哪一步。": ("route", "personal.learning"),
            "/biz miracle 直接告诉我该把降压药加到多少毫克。": ("out_of_scope", None),
            "/biz coach 教我纠正自由泳划水动作，给每组训练次数。": ("out_of_scope", None),
            "/biz goal 我胸痛两天了，替我决定今晚吃哪种药和剂量。": ("out_of_scope", None),
            "/biz product 根据我的血糖记录调整胰岛素方案，今天就执行。": ("out_of_scope", None),
            "连锁健身房会员续费下降，已有到店频次和退卡访谈，帮我找可证伪原因与实验。": ("route", "business.diagnose"),
            "我准备商业化青少年网球教练服务，先分清学员、家长付款人和最容易触达的首批客户。": ("route", "business.customer"),
            "我们销售给诊所的慢病随访软件，医生使用、院长采购、患者受益，帮我形成客户定义和访谈测试。": ("route", "business.customer"),
            "帮我判断短视频的第一句话和标题哪个更该先改，只问一个能决定路线的问题。": ("clarify", None),
            "仓储SaaS既可能是定位错了，也可能是产品范围错了，请问一个能决定先诊断商业问题还是先写PRD的问题。": ("clarify", None),
            "我既想把半年目标定清，也想解决今天迟迟没行动的问题，请用一个问题决定先后。": ("clarify", None),
            "我们给开发团队卖代码审查SaaS，每月推理成本约两千，现有按席位收费常被质疑，设计可逆的定价测试。": ("route", "business.pricing"),
            "给一篇关于门店损耗控制的文章拟标题，读者是连锁店长，证据来自三个月盘点记录。": ("route", "content.title"),
        }
        for text, (state, task_id) in expected.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result["state"], state, result)
                self.assertEqual(result["selected_task"], task_id, result)

    def test_generalized_routing_families_and_safety_gates(self) -> None:
        expected = {
            "/biz 项目证据和本周限制都在上文，请依据现有讨论选下一步。": ("route", "runtime.intervene"),
            "别重新分析原因，只汇总项目现状、未完成事项和停止条件。": ("route", "runtime.status"),
            "客户范围太泛，请收窄早期客户并安排访谈验证。": ("route", "business.customer"),
            "不要用历史类比，比较仍在运营的同类公司在获客与履约上的做法。": ("route", "research.benchmark"),
            "不要照搬同行，找结构相似的过去案例、反例和适用边界。": ("route", "research.standard"),
            "文案不改语法和标题，只检查是否站在受众处境说话，有没有立场错位。": ("route", "content.resonate"),
            "稿子准备发布，包含价格、私信入口和用户照片，请做广告、隐私和人工复核检查。": ("route", "content.publish_check"),
            "把当前判断整理为可恢复快照，只给预览和落盘位置，确认前不写入。": ("route", "decision.save"),
            "团队多端指令在漂移，请确定唯一真源、薄适配层、升级和回退规则。": ("route", "governance.workbench"),
            "核心库不变，只规划旧 Agent 如何从不同目录发现它并做兼容验证。": ("route", "governance.bridge"),
            "本地 Skill 可能有下载脚本，请只读检查权限和提示注入风险，先报告。": ("route", "governance.audit_skill"),
            "让多个立场先各自论证，再交叉质询，最后列出供我选择的方案。": ("route", "debate.run"),
            "把它处理一下。": ("clarify", None),
            "检查某个文件夹并直接建知识库。": ("clarify", None),
            "写好标题后登录账号直接发布。": ("clarify", None),
            "登录对手系统导出他们的客户资料给销售使用。": ("out_of_scope", None),
            "比较两位足球运动员谁更强，只看竞技成绩。": ("out_of_scope", None),
        }
        for text, (state, task_id) in expected.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result["state"], state, result)
                self.assertEqual(result["selected_task"], task_id, result)

    def test_dynamic_top_three_explains_rejections_and_route_changes(self) -> None:
        result = route("客户说贵，MVP范围也可能不对，团队还在拖延联系客户，我要判断先做什么。")
        self.assertEqual(len(result["top_candidates"]), 3, result)
        for index, candidate in enumerate(result["top_candidates"], 1):
            self.assertEqual(candidate["rank"], index, result)
            self.assertIn("selected", candidate, result)
            self.assertIn("rejection_reason", candidate, result)
            self.assertTrue(candidate["route_change_condition"], result)

    def test_composite_intents_and_domain_boundaries(self) -> None:
        expected = {
            "前面的聊天里预算、客户反馈和试验都已说全，请直接选现在最值得推进的下一步。": ("route", "runtime.intervene"),
            "团队对高端服务各有定义，请把词义边界说清并形成决策问题。": ("route", "reasoning.clarify"),
            "我每周只有八小时，能联系本地店主，但还没有具体副业方向。": ("route", "business.explore"),
            "签约率连续下降，请找最可能断在哪并设计证伪测试。": ("route", "business.diagnose"),
            "这个工具由护士长操作、院办采购、财务出钱，请分清角色和首访对象。": ("route", "business.customer"),
            "找三家公司比较获客、收费和交付成本，并提炼能迁移的机制。": ("route", "research.benchmark"),
            "这份口播请标出论证断点、观众流失位置和修改顺序，不要重写。": ("route", "content.script"),
            "项目编号 q3-retention，请从已保存版本恢复，标出过期风险后给下一步。": ("route", "decision.restore"),
            "我批准查看 /workspace/me/notes 这个目录，先做只读清单，再给索引和版本规则。": ("route", "governance.knowledge"),
            "核心 Skill 只维护一份，两个目标端规则不同，请设计桥接、验收和回滚。": ("route", "governance.bridge"),
            "帮我整理一下电脑里的知识库，乱得很。": ("clarify", None),
            "这个标题能发吗？": ("clarify", None),
            "帮我订明早从虹桥机场到苏州的车，直接下单。": ("out_of_scope", None),
            "把这段日语小说翻译成中文，保留文学语气。": ("out_of_scope", None),
            "我连续失眠和心慌，能不能判断我是不是焦虑症？": ("out_of_scope", None),
            "分析我和伴侣谁更爱谁，替我决定要不要分手。": ("out_of_scope", None),
        }
        for text, (state, task_id) in expected.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result["state"], state, result)
                self.assertEqual(result["selected_task"], task_id, result)

    def test_v3_failure_regressions(self) -> None:
        expected = {
            "请把我们前面关于社区咖啡订阅、企业团购和周末市集的讨论重新读一遍，替我判断眼下最该推进哪一件事，并说明为什么不是另外两件。": ("route", "runtime.intervene"),
            "/biz intervene 当前已知：试卖有12人付订金，包装成本还没核完，周五前必须决定是否接下首批订单。请选下一步并直接处理。": ("clarify", None),
            "团队一直说要找“高价值客户”，销售理解为客单价高，交付理解为需求稳定。我需要用这个词决定本季度筛选名单，请先把定义边界和可观察指标讲清楚。": ("route", "reasoning.clarify"),
            "同一款家庭记账工具，真正每天用的是妻子，决定是否付费的是丈夫，推荐者常是理财顾问。访谈里三方对“省时间”的理解不同，我需要先确定早期销售该瞄准谁。": ("route", "business.customer"),
            "我们想把面向设计公司的按月顾问服务做成标准套餐。请比较国内三种真实的同类服务在客户、计价方式、交付边界和信任机制上的差异，目标是决定哪些机制值得做小实验，不复制文案。": ("route", "research.benchmark"),
            "这篇文章事实和结构都已经核过，但几位目标读者说“像在教训人”。受众是首次创业失败后准备再试的人，稿件在上文。请判断他们处境、情绪与叙述立场是否错位，只做最小修改建议。": ("route", "content.resonate"),
            "我说想“建立个人品牌”，但目前每月只发布一篇文章，也没有线索记录。未来90天每周最多投入5小时，不接广告，目标受益者是我的咨询业务。请把愿望改成可观察目标、非目标和检查点。": ("route", "personal.goal"),
            "我的可观察目标是周四前约到3位老客户访谈。昨天我打开通讯录后一直修改邀请语，40分钟后没有发出一条；今天还有30分钟，最担心被拒绝。请找最早断点并给一个可完成的下一动作。": ("route", "personal.action"),
            "项目标识 northstar-retainer。请从当前交接内容提取已确认事实、已接受判断、实验、阻塞和下一动作，生成带版本号与父哈希的完整快照预览；先告诉我目标位置，不要落盘。": ("route", "decision.save"),
            "只读盘点文件夹 /workspace/shared/research/retail-notes：操作是建立索引方案，仅处理 md、pdf，排除 raw-audio 和 credentials；原文件是事实源，不允许移动或写入。请列版本冲突、重复和敏感风险。": ("route", "governance.knowledge"),
            "我们要让同一套商业案例库同时服务Codex、内部网页助手和离线检索器。规范源固定在 /srv/knowledge/cases，内容团队拥有写权，各消费者只读单向同步，格式分别是JSONL、HTTP查询和SQLite。请设计源映射、适配契约、版本矩阵和回滚。": ("route", "governance.workbench"),
            "我们必须在明天决定是否把顾问服务从按项目收费改成订阅。已知续约需求不稳定、交付容量有限、三位客户表达过月度需求。请让独立角色分别论证、互相质询，再给出保留分歧的综合和供我选择的方案。": ("route", "debate.run"),
            "客户嫌我们的年度服务贵，而且续费率也在降。到底该先重做套餐，还是先判断整个生意哪里出了问题？": ("clarify", None),
            "我认识不少社区团长，但不确定他们是不是客户，也不知道该围绕他们找机会还是先定义购买者。": ("clarify", None),
            "我想找几个现实案例和几个历史案例，看看会员制为什么会失效。你帮我对标一下。": ("clarify", None),
            "我想把“做得更专业”这件事讲清楚，然后定一个三个月目标。先做哪个都行。": ("clarify", None),
            "这段口播让人没感觉，可能是逻辑断了，也可能是立场不对。帮我改改。": ("clarify", None),
            "文章已经写完了，我只想让第一眼更有吸引力，标题和开头你选一个优化。": ("clarify", None),
            "帮我看看这条内容能不能发，平台规则应该挺严的。": ("clarify", None),
            "找几个优秀同行对比一下，看看我们能学什么。": ("clarify", None),
            "给我们的内部协作工具写个PRD，越完整越好。": ("clarify", None),
            "给我写三个爆款开头，主题你看着办。": ("clarify", None),
            "把规范Skill接到所有agent上，链接和配置该改就改。": ("clarify", None),
            "我们应该停止低价套餐，帮我正式记下来。": ("clarify", None),
            "我想学会做商业分析，给我排一套课程。": ("clarify", None),
            "根据我这份血常规和持续发热症状，判断最可能是哪种感染，并给治疗方案。": ("out_of_scope", None),
            "我三个月后跑全马，最近膝盖偶尔疼，请给每周里程、配速和恢复安排。": ("out_of_scope", None),
            "把PostgreSQL这张五千万行表在线拆分成分区表，给我可直接执行的迁移SQL和回滚脚本。": ("out_of_scope", None),
            "把我上传的证件照背景换成蓝色，并去掉眼镜反光。": ("out_of_scope", None),
        }
        for text, (state, task_id) in expected.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result["state"], state, result)
                self.assertEqual(result["selected_task"], task_id, result)

    def test_professional_oos_rules_preserve_commercial_requests(self) -> None:
        expected = {
            "我们卖感染检测咨询服务，医院客户说价格贵，应该怎么设计套餐？": "business.pricing",
            "我卖全马训练课程，首批客户是第一次参赛的上班族，套餐如何定价？": "business.pricing",
            "我们提供PostgreSQL分区迁移服务，客户嫌报价高，如何做可逆定价测试？": "business.pricing",
            "商品证件照处理服务准备商业化，目标客户是谁、谁会付费？": "business.customer",
        }
        for text, task_id in expected.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result["state"], "route", result)
                self.assertEqual(result["selected_task"], task_id, result)

    def test_reported_natural_route_gaps(self) -> None:
        expected = {
            "我周末有七小时，会做表格自动化，认识几家培训机构，想找个能卖的方向": "business.explore",
            "我想给小团队做客户回访自动化，这个点子值得试吗": "business.diagnose",
            "访问量涨了但订单反而少了，帮我诊断生意哪里断了": "business.diagnose",
            "支持成本和交付范围都不清楚，现在报价该从哪里算": "business.pricing",
            "别做发布计划，先告诉我这种服务最该卖给谁": "business.customer",
            "学了三周还是没动手，今天给我一个能完成的小动作": "personal.action",
            "把这份访谈记录提炼成知识原子和方法，先只分析不入库": "governance.knowledge",
            "请三名独立Agent分别审查，然后互相反驳这个定价方案": "debate.run",
        }
        for text, task_id in expected.items():
            with self.subTest(text=text):
                self.assert_route(text, task_id)

    def test_reported_intervention_route_gaps(self) -> None:
        expected = {
            "/biz intervene 健身房流失提醒已有演示和数据承诺，现在要决定继续还是暂停。": "business.diagnose",
            "/biz intervene 牙科回访已有八家客户，续费下降，也有退订访谈，请判断先查哪里。": "business.diagnose",
            "/biz intervene 客户与交付已经明确，但工时、差旅和售后成本未知，先做哪项定价工作。": "business.pricing",
            "/biz intervene 这不是文案任务；员工使用、人事选择、财务审批，先找谁谈。": "business.customer",
            "/biz intervene 今晚要完成服务说明，我因完美主义改标题两小时，还剩四十分钟，只给最小动作。": "personal.action",
            "/biz intervene 材料在 /workspace/review/interviews，项目知识库根目录是 /workspace/project/.biz-partner/knowledge-packs/interviews；只生成候选原子、概念和检索样例，禁止写入。": "governance.knowledge",
            "/biz intervene 是否关店还是再试三个月已有亏损和订单证据，请让支持、反对和风险角色交叉质疑，保留分歧。": "debate.run",
        }
        for text, task_id in expected.items():
            with self.subTest(text=text):
                self.assert_intervene(text, task_id)

    def test_unseen_route_rewrites(self) -> None:
        expected = {
            "我在县城做了六年婚庆摄影，周末能空出一天，认识二十多家花店和司仪，但还没确定能卖什么轻服务，帮我从这些关系里挑一个最先验证的生意机会。": "business.explore",
            "手头最多只能亏三千元，我会给宠物店拍短视频，也能每周联系五位店主；想摸索一个不用囤货的创业切口，第一轮该试什么？": "business.explore",
            "我们给连锁牙科做员工培训，最近试听人数没变，签约却从十家掉到两家；先判断损耗发生在信任、方案还是审批，并给一个能排除错误原因的试验。": "business.diagnose",
            "社区团购的订单还在涨，但退款和客服工时一起翻倍，我想知道是承诺过头、履约失配还是客群选错，先查哪条证据？": "business.diagnose",
            "我的上门收纳服务每单要占两名员工四小时，企业客户常要求季度结算；请判断按面积、按工时还是按项目报价更能覆盖容量波动。": "business.pricing",
            "我们卖给培训机构的排课工具有基础版和协作版，现有用户集中使用高成本客服；想设计一轮月付与年付套餐测试，观察哪类人愿意升级。": "business.pricing",
            "我们做养老院夜班交接工具，护理员天天操作，院长拍板，财务付款；请收窄首轮访谈该找哪一种角色，以及他们真正想避免的损失。": "business.customer",
            "我准备卖一套家庭厨房过敏原管理卡，家长购买、孩子使用、营养师可能推荐；先界定最早值得验证的购买者和触发场景。": "business.customer",
            "周五前我要约到三位店主演示，名单已经列好，却每天都在改开场白，怕对方当场拒绝；替我定一个今天就能发出的最小动作和停止条件。": "personal.action",
            "本周要完成两次收费访谈，我已经打开通讯录三回都没拨号，卡在担心熟人觉得我在推销；先帮我跨过最早那个断点。": "personal.action",
            "请只读盘点 /workspace/studio-notes 这套资料库，标出重复文件、来源不明条目和版本冲突，再给索引计划，不要写入。": "governance.knowledge",
            "范围只限 /workspace/team-archive/research-vault，先列知识资产清单，区分过期材料与仍可追溯来源，并提出版本规则，暂不改文件。": "governance.knowledge",
            "关于是否在下季度砍掉定制交付，请让支持保留和主张砍掉的独立角色分别论证，再交叉质询成本与客户证据，最终选项留给我。": "debate.run",
            "我们要不要把首个市场从学校换到诊所？请安排赞成迁移和主张留守的角色各自举证，第二轮专门攻击对方最弱假设，最后只汇总可选路径。": "debate.run",
        }
        for text, task_id in expected.items():
            with self.subTest(text=text):
                self.assert_route(text, task_id)

    def test_unseen_route_boundaries_and_cross_intents(self) -> None:
        expected = {
            "我想靠自己做点生意，你帮我看看。": ("clarify", None),
            "帮我探索周末适合新手的徒步路线。": ("out_of_scope", None),
            "这门生意最近有点不对劲，替我找原因。": ("clarify", None),
            "我这台咖啡机出水忽快忽慢，帮我诊断故障。": ("out_of_scope", None),
            "这项服务到底该怎么收钱？": ("clarify", None),
            "查一下这本旧书当年的售价，只返回书目信息。": ("out_of_scope", None),
            "我做了个产品，但还没想清楚该找什么人，你先帮我看看。": ("clarify", None),
            "把我通讯录里的联系人按姓氏分组。": ("out_of_scope", None),
            "我的生意一直推进不动，接下来怎么办？": ("clarify", None),
            "给我一套十公里跑步提速训练计划，包含每周里程和恢复安排。": ("out_of_scope", None),
            "把我电脑里的知识库整理成可检索的样子。": ("clarify", None),
            "请把‘知识库’这三个字翻译成英文，不要扫描任何目录。": ("out_of_scope", None),
            "找几个人从不同角度争一争。": ("clarify", None),
            "比较梅西和 C 罗谁的竞技表现更伟大，不讨论商业价值，也不要多角色辩论。": ("out_of_scope", None),
            "这项上门照护服务的客户已经确定，不要做客户画像；请只比较按小时和按月收费对现金流的影响。": ("route", "business.pricing"),
            "我们的课程续费连续三个月下滑，先别改价格，也不要找新客群；请找出承诺、使用和交付哪一环最可能断掉，并给排除试验。": ("route", "business.diagnose"),
            "我还没决定做哪种生意，报价和套餐以后再说；每周只有六小时，能接触到十家社区门店，先找一个可验证方向。": ("route", "business.explore"),
            "目标客户还不能只写成‘餐饮业’，这次不讨论副业方向；请界定店长、区域经理和财务谁使用、谁拍板、谁付款，安排首轮访谈。": ("route", "business.customer"),
            "周三前要给两位客户发方案，价格已经定了，也不做业务诊断；我卡在反复改附件，帮我选今天能完成的最小一步。": ("route", "personal.action"),
            "只读盘点 /workspace/field-notes 的来源与重复项；不要召集多角色讨论，也不要替我设计产品。": ("route", "governance.knowledge"),
            "是否继续给大客户做定制？客户定义和报价先不动；请让支持与反对两方独立论证、交叉质询交付成本，最后由我决定。": ("route", "debate.run"),
            "我们既不知道该服务谁，也不知道该怎么收费，现有访谈又互相矛盾；先问我一个最能决定该走客户研究还是价格测试的问题。": ("clarify", None),
            "不要诊断业务，也不要调整价格；我只是要把这段英文合同逐句翻译成中文。": ("out_of_scope", None),
            "这套运动课程卖给跑团，学员觉得贵，但我现在只想要一套十公里个人训练计划，不要分析课程收费。": ("out_of_scope", None),
        }
        for text, (state, task_id) in expected.items():
            with self.subTest(text=text):
                result = route(text)
                self.assertEqual(result["state"], state, result)
                self.assertEqual(result["selected_task"], task_id, result)

    def test_route_expansion_does_not_capture_unrelated_requests(self) -> None:
        cases = (
            "我没有想法，只想把这封道歉邮件润色得自然一点。",
            "小说主角没有人生方向，请只校对这一段。",
            "我的论文卡住了，请分析论证为什么失败。",
            "客服记录里有一句‘客户说贵’，请只抽取原文，不要做商业判断。",
            "医院里谁使用这台仪器、谁来付款？我是在核对操作流程，不是定义目标客户。",
            "我在游戏关卡里卡住了，下一步往哪走？",
            "这里只是在文档里提到知识库，不要盘点、索引或治理。",
            "这篇论文讨论多个 Agent 的辩论机制，请翻译摘要。",
            "不要让多个 Agent 讨论，也不要交叉质疑，只给我一个简短答案。",
        )
        for text in cases:
            with self.subTest(text=text):
                result = route(text)
                self.assertNotEqual(result["state"], "route", result)
                self.assertIsNone(result["selected_task"], result)

    def test_second_unseen_route_rewrites(self) -> None:
        direct = {
            "我认识不少本地商户，每周能拿出6小时，但完全不知道该拿什么去赚钱，帮我找一个可以先试的方向。": "business.explore",
            "这个会员服务做了三个月，报名越来越少，老客也在走，我想先弄清是哪一环坏了再改。": "business.diagnose",
            "给店主提供代运营，每月收三千总被嫌不值，我想试试按结果收还是固定月费。": "business.pricing",
            "护士天天用，院长拍板，财务付款；首轮该先找哪一方谈？": "business.customer",
            "资料看了一堆，也想了很久，始终没动手；今天只给我一个能完成的小动作。": "personal.action",
            "把这批访谈纪要纳入现有知识体系，先查重复和冲突，再给我可确认的更新预览。": "governance.knowledge",
            "拉三个独立视角，把继续投和马上停两边都论证一遍，彼此挑最弱前提，结论留给我。": "debate.run",
        }
        for text, task_id in direct.items():
            with self.subTest(text=text):
                self.assert_route(text, task_id)

        interventions = {
            "/biz intervene 我认识本地商户，每周能拿出6小时，但不知道拿什么赚钱。请选下一步。": "business.explore",
            "/biz intervene 过去三个月报名从20个变成5个，老客也在走。我想先弄清哪一环坏了，请选下一步。": "business.diagnose",
            "/biz intervene 三位客户说这个月费不值，我想试按结果收还是固定月费，请选下一步。": "business.pricing",
            "/biz intervene 已做10次访谈：护士天天用，院长拍板，财务付款。首轮该找谁谈？请选下一步。": "business.customer",
            "我昨天看资料2小时仍没动手，今天还剩30分钟，请选下一步。 /biz intervene": "personal.action",
            "/biz intervene 本周新增12份访谈纪要，要纳入现有知识体系并先查重复冲突。请选下一步。": "governance.knowledge",
            "/biz intervene 明天必须决定是否续投，已有3位客户反馈。我想让几个独立视角把两边论证一遍，再请选下一步。": "debate.run",
        }
        for text, task_id in interventions.items():
            with self.subTest(text=text):
                self.assert_intervene(text, task_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
