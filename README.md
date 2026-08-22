<div align="center">

# Biz Partner

### 把生意想法，推进到下一步

一个会追问证据、拆解问题、陪你行动的 Agent Skill。

[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-biz--partner-111827?style=flat-square)](skills/biz-partner/SKILL.md)
[![Knowledge Pack](https://img.shields.io/badge/knowledge-40%20atoms-2563EB?style=flat-square)](skills/biz-partner/public-knowledge/USAGE.md)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-E11D48?style=flat-square)](LICENSE)

[中文](README.md) · [English](README_EN.md) · [知识包](skills/biz-partner/public-knowledge/USAGE.md) · [X / Twitter](https://x.com/ExpLang_Cn)

</div>

你不需要先学商业框架，也不用想好该问什么。把真实情况讲出来就行。

它适合正在找副业方向、验证生意点子，或者经营产品与内容的个人和小团队。

没有点子，它陪你找方向；有了点子，它帮你判断客户、产品、定价和交付；做着做着卡住了，它会把问题拆成今天能完成的一步。

它更像一个会追问证据、会翻决策记录、也敢劝你先别做的合伙人。最终决定仍由你做。

## 60 秒安装并开始

已经安装 Node.js，可以直接运行：

```bash
npx skills add yuzaicn/biz-partner -g --skill biz-partner
```

安装后打开新会话，先加载：

```text
$biz-partner
```

然后直接说：

```text
我想找一个能在 30 天内验证的副业。我每周有 8 小时，会做自动化，能接触 20 家电商小团队，测试预算不超过 1000 元，也不想先开发产品。
```

Biz Partner 不会马上丢给你一长串热门赛道。它会先找出你的可触达客户、能力边界和验证条件，再给出候选方向、关键假设、第一批访谈对象与停止条件。

Skill 已经载入，或者客户端支持隐式调用时，也可以用 `/biz ...` 快速开始。如果当前会话已经聊了很多，不想重新解释一遍：

```text
/biz intervene
```

它会读取现有上下文，列出最值得推进的几个方向，选择一个主任务直接开始。缺少关键事实时，当前轮只问一个最重要的问题。

## 这些时候，直接找它

| 你的情况 | 可以这样说 | 它会推进什么 |
| --- | --- | --- |
| 还没有生意点子 | `/biz 我想做副业，但不知道自己适合什么` | 从时间、能力、资源和可触达客户中形成 3 到 5 个可验证方向 |
| 有点子，但不知道靠不靠谱 | `/biz 帮我判断这个想法有没有人愿意付钱` | 拆客户、任务、痛点证据、交付成本和最小收费实验 |
| 客户总说贵 | `/biz 我该降价、换客户，还是改产品？` | 区分价值、定位、信任、价格和成本问题，不把降价当默认答案 |
| 想做内容获客 | `/biz 根据这个产品做选题、标题和短视频脚本` | 先确定受众与目标，再做内容，并在发布前检查风险 |
| 明知道该做，却一直拖 | `/biz 我卡住两周了，帮我拆一个今天能完成的动作` | 找阻力来源，生成最小动作、检查点和停止条件 |
| 团队意见分歧很大 | `/biz debate 这个产品要不要继续做` | 组织独立判断、交叉质询和综合结论，保留分歧给你决策 |

自然语言也可以。`/biz` 只是让触发更明确。

## 它会怎么和你一起工作

每次先做五件事：

1. 说清当前真正要解决的问题。
2. 分开已知事实、合理推断和未知信息。
3. 选择一个当前价值最高的任务。
4. 给出可以执行、可以观察结果的下一步。
5. 写明成功标准、停止条件和需要你确认的操作。

信息不足时，它会承认不知道，并告诉你怎样补证据。写文件、发布内容、付款、删除数据和发送外部消息等重要操作，不会绕过你的确认。

## 其他安装方式

上面的 Agent Skills CLI 如果检测到多个 Agent 客户端，会让你选择安装目标。Codex 用户也可以使用内置安装器：

适用于 macOS 或 Linux 上的 Codex：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo yuzaicn/biz-partner \
  --path skills/biz-partner
```

安装后请打开新会话，先加载 `$biz-partner`，再描述真实问题。

## 能力地图

| 方向 | 能做的事 |
| --- | --- |
| 生意判断 | 找方向、客户识别、需求证据、定价、单位经济、对标、过去结构相似的案例 |
| 产品管理 | 产品定义、MVP、优先级、验收标准、指标树、实验计划 |
| 内容增长 | 选题、标题、共鸣检查、长短内容、短视频脚本、发布风险检查 |
| 个人行动 | 目标澄清、拖延与贪快诊断、行动卡、学习计划、阶段复盘 |
| 长期治理 | 决策记录、文件夹知识库、内容资产、多 Agent 工作台、本地 Skill 只读审计 |

它不会一次把所有能力都堆给你。默认只推进当前最有价值的一步。

## 内置可检索的公开知识

公开版自带一套可检索、可追溯的知识包。“知识原子”就是一条可以单独找到、引用和组合的判断材料。

- 40 条知识原子：30 条来自 10 本书的独立再表述，10 条来自鱼仔公开内容的提炼。
- 9 套方法：覆盖客户验证、商业判断、沟通、内容、行动和复盘。
- 48 个任务概念：18 个运行时概念，30 个从书中筛选并重新定义的通用概念。
- 40 个检索用例：验证每条知识原子都能被找到。

继续查看：[知识包说明](skills/biz-partner/public-knowledge/USAGE.md) · [Book Metadata](skills/biz-partner/public-knowledge/book-metadata.md) · [方法论](skills/biz-partner/public-knowledge/methods.md) · [概念词典](skills/biz-partner/public-knowledge/concept-dictionary.md) · [结构化清单](skills/biz-partner/public-knowledge/manifest.json)

来源只有在真正支撑最终判断时才会出现。只是检索到但没有采用，不会硬塞作者名字。鱼仔是登记的外部知识来源，不是运行时用户。

## 它会逐渐了解你，但不会擅自定义你

Biz Partner 可以跟随你的项目和行动进度，提出对用户偏好、项目状态、决策记录与有效做法的更新建议。

这些长期信息默认只是候选。只有经过确认才会写入；过期、被否定或不再适用的信息可以被抑制或删除。使用得越久，它可以越贴近你的真实约束，但不会把一次对话当成永久人格结论。

## 公开版包含什么

这是完整可运行的公开版，不是私有研究目录的镜像。

包含运行核心、工作流、契约、状态管理、多 Agent 讨论协议、只读审计工具和提炼后的公开知识包。不会公开书籍原文、账号原文、词频与章节索引、采集记录、审核底稿、本机研究路径或个人数据。

书名和作者只用于来源说明。许可证只覆盖本项目重新写过的表达和编排，不授予原书文字、插图、表格、案例或其他原始表达的权利。

## 使用边界

Biz Partner 提供决策支持和受控工作流，不保证商业成功、平台审核通过、法律合规、投资收益或其他现实结果。重要决定仍要结合当前事实，并由你承担最终判断。

## 许可与联系

本项目采用 [PolyForm Noncommercial 1.0.0](LICENSE)。它是非商业 source-available 项目，不是 OSI 定义下的开源软件。商业使用需要另行获得授权，具体以许可证原文为准。

作者：鱼仔 · [X（Twitter）@ExpLang_Cn](https://x.com/ExpLang_Cn)
