# 公开知识包

这套知识包把商业判断分成六层。每一层只做一件事，最终结论仍要回到当前客户、成本、交付和结果证据。

## 六层怎么配合

1. **来源层 `sources.jsonl`**：登记公开材料的权利边界和来源标识，帮助追溯知识从哪里来。
2. **原子层 `atoms.jsonl`**：保存一次只表达一个判断的最小知识单元，并写清适用条件和限制。
3. **方法层 `methods.jsonl` / `methods.md`**：把多个原子组合成带步骤、判断门槛和停止条件的做法。
4. **概念层 `concepts.jsonl` / `concept-dictionary.md`**：统一工作词和分析概念，避免同一个词在不同任务里悄悄换意思。
5. **检索层 `retrieval-cases.jsonl`**：用直接问法和口语问法检查原子、方法和概念能否被稳定找到。
6. **网络层 `knowledge-network.md` / `knowledge-graph.json`**：让每条来源、原子、概念和方法都能通过稳定链接打开，并查看已经声明的正向与反向关系。

## 先搜一次

在 Skill 目录运行：

```bash
python3 scripts/knowledge_runtime.py pack-search \
  --sources public-knowledge/sources.jsonl \
  --atoms public-knowledge/atoms.jsonl \
  --query '客户为什么不愿意付费' \
  --limit 5
```

检索先帮助定位相关原子；需要完整做法时再读 [methods.md](methods.md)，概念含义不清或容易混用时读 [concept-dictionary.md](concept-dictionary.md)，想顺着关系浏览时打开 [knowledge-network.md](knowledge-network.md)。搜索结果是候选材料，不替代当前事实。

`sources.jsonl`、`atoms.jsonl`、`methods.jsonl`、`concepts.jsonl` 和 `retrieval-cases.jsonl` 是运行时与测试使用的确定性数据，不建议手工修改。`knowledge-graph.json` 和 `knowledge-network.md` 都从这些数据自动生成，不是第二份知识来源。

## 让它学习你的新材料

新增知识默认进入用户指定项目里的私有知识包。Agent 先分析材料并生成候选，再检查重复、冲突、隐私、权利和关系；只有你确认了准确预览，工具才会写入一个新的可回退版本。完整流程见 [Knowledge Learning](../references/knowledge-learning.md)。这不会自动修改内置公开包，也不会自动同步 GitHub。

## 这里没有什么

公开包只有独立改写的知识原子、方法、概念定义和检索样例，不含来源原文、采集记录、审核底稿、本机路径或个人运行记忆。

仓库许可证只覆盖本项目重新写过的表达和编排，不授予来源文字、插图、表格、案例或其他原始表达的权利，也不能据此反向还原被排除的材料。
