<div align="center">

# Biz Partner

### 少给漂亮答案，多碰一点现实

一个会把判断落到下一步的 Agent Skill。

[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-biz--partner-111827?style=flat-square)](skills/biz-partner/SKILL.md)
[![Knowledge Pack](https://img.shields.io/badge/knowledge-40%20atoms-2563EB?style=flat-square)](skills/biz-partner/public-knowledge/USAGE.md)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-E11D48?style=flat-square)](LICENSE)

[中文](README.md) · [English](README_EN.md) · [知识包](skills/biz-partner/public-knowledge/USAGE.md) · [X / Twitter](https://x.com/ExpLang_Cn)

</div>

把真实情况丢给它。

没点子没关系。先说说你会什么、认识谁、每周能拿出多少时间；<br>
有了点子，先看谁会买、为什么买，以及你能不能交付；<br>
真卡住了，也别再做更大的计划。先把眼前这件事拆到今天。

证据不够，它会直接说。现在不该做，也会劝你先停一下。

## 安装并开始

已经安装 Node.js，可以直接运行：

```bash
npx skills add yuzaicn/biz-partner -g --skill biz-partner
```

打开一个新会话，加载：

```text
$biz-partner
```

然后讲真实情况，不用先学一套商业框架：

```text
我想找一个能在 30 天内验证的副业。我每周有 8 小时，会做自动化，能接触 20 家电商小团队，测试预算不超过 1000 元，也不想先开发产品。
```

它不会先塞给你一长串热门赛道。它会从你能接触的人、能交付的事和能承受的损失里找方向，再挑一个最便宜的办法去碰真实反馈。

Skill 已经载入，或者客户端支持隐式调用时，也可以直接用 `/biz ...`。当前会话已经聊了很多，不想重讲一遍，就输入：

```text
/biz intervene
```

它会读完现有上下文，判断现在先解决什么。少了关键事实，只问当前最要紧的那一个。

## 这些时候，可以直接找它

| 你的情况 | 可以这样说 | 它先做什么 |
| --- | --- | --- |
| 还没有生意点子 | `/biz 我想做副业，但不知道自己适合什么` | 缩小方向，先找可触达的客户 |
| 有想法，但不知道靠不靠谱 | `/biz 帮我判断这个想法有没有人愿意付钱` | 找出最危险的假设，设计一次收费测试 |
| 客户总说贵 | `/biz 我该降价、换客户，还是改产品？` | 先判断是价值、信任、成本，还是价格本身 |
| 想靠内容获客 | `/biz 根据这个产品做选题、标题和短视频脚本` | 先定受众和事实，再动笔 |
| 明知道该做，却一直拖 | `/biz 我卡住两周了，帮我拆一个今天能完成的动作` | 把动作拆小，写清做到哪算完成 |
| 团队对重要决定争得很厉害 | `/biz debate 这个产品要不要继续做` | 在客户端支持真实子 Agent 时组织独立审查和交叉质疑；否则如实说明采用的是结构化多角度复核 |

自然语言也可以。`/biz` 只是让触发更明确。

## 它怎么做判断

它不会急着交一份完整报告。先分清哪些是已经发生的，哪些只是猜测，再找出眼下最影响结果的那件事。

事实够了，就往前推一步。事实不够，它只追问会改变决定的那个问题。涉及实验、投入或继续开发时，它会把做到什么算完成、看到什么应该停，一起说清楚。

写文件、发布内容、付款、删除数据或向外发送消息前，它仍会把准确范围摆出来，等你确认。

除了生意判断，它也能整理产品方案、检查内容、处理行动受阻、记录长期决策、治理文件夹知识库，并只读审查本地 Skill。完整入口在 [Skill 文档](skills/biz-partner/SKILL.md)。

## 它手里有什么

Skill 内置 40 条可以检索的知识原子、9 套方法、48 个任务概念和 40 个检索回归用例。30 条知识原子来自整理材料的独立再表述，10 条来自鱼仔公开内容的提炼。

这些内容不是拿来背的。讨论客户、定价、内容或行动问题时，它会按当前问题去找；每条知识原子都有检索用例，可以检查它到底能不能被找到。

[知识包说明](skills/biz-partner/public-knowledge/USAGE.md) · [方法论](skills/biz-partner/public-knowledge/methods.md) · [概念词典](skills/biz-partner/public-knowledge/concept-dictionary.md) · [结构化清单](skills/biz-partner/public-knowledge/manifest.json)

整理材料保持匿名。真正使用了鱼仔的知识原子，结果里才会显示来源；只是搜到，不算。

## 它会记住什么

它可以根据你确认过的项目记录继续工作。新偏好和新判断先作为建议，确认后才会用于后续会话；过期或错误的信息可以停用、纠正。一次聊天不会变成对你的永久定义。

## 另一种安装方式

Codex 用户也可以使用内置安装器：

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo yuzaicn/biz-partner \
  --path skills/biz-partner
```

安装后打开新会话，加载 `$biz-partner`，再描述真实问题。

## 边界、许可和联系

Biz Partner 提供决策支持和受控工作流，不保证商业成功、平台审核通过、法律合规、投资收益或其他现实结果。重要决定仍要看当前证据，并由你做最终判断。

本项目采用 [PolyForm Noncommercial 1.0.0](LICENSE)。它是非商业 source-available 项目，不是 OSI 定义下的开源软件。商业使用需要另行获得授权，具体以许可证原文为准。

作者：鱼仔 · [X（Twitter）@ExpLang_Cn](https://x.com/ExpLang_Cn)
