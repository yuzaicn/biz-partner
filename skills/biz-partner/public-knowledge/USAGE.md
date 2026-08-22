# 公开知识包

这套知识不是让 Skill 背出来的。遇到客户、定价、内容、沟通或行动问题时，先按当前问题搜索；找到的内容只是判断材料，能不能用还要看这次的事实。

## 先搜一次

在 Skill 目录运行：

```bash
python3 scripts/knowledge_runtime.py pack-search \
  --sources public-knowledge/sources.jsonl \
  --atoms public-knowledge/atoms.jsonl \
  --query '客户为什么不愿意付费' \
  --limit 5
```

需要一套完整做法时再读 [methods.md](methods.md)；概念含义不清或容易混用时，读 [concept-dictionary.md](concept-dictionary.md)。

`sources.jsonl`、`atoms.jsonl`、`concepts.jsonl` 和 `retrieval-cases.jsonl` 是给运行时和测试使用的确定性数据，不建议手工修改。面向人的说明放在 Markdown，结构化事实以 JSON/JSONL 为准。

## 来源什么时候出现

只有某条知识原子真正支撑了回答里的判断、方法或测试，才把它接入 Handoff 的证据链，再由 `scripts/render_source_attribution.py` 校验来源。

整理材料在公开结果中保持匿名。登记的命名来源只在实际采用时出现一次；只是搜索到了但没有使用，不署名，也不能把来源身份当成当前用户。

## 这里没有什么

公开包只有独立改写的知识原子、方法和概念定义，不含来源原文、采集记录、审核底稿、本机路径或个人运行记忆。

仓库许可证只覆盖本项目重新写过的表达和编排，不授予来源文字、插图、表格、案例或其他原始表达的权利，也不能据此反向还原被排除的材料。
