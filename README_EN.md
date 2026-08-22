<div align="center">

# Biz Partner

### Turn a business idea into the next testable step

An Agent Skill that questions assumptions, diagnoses problems, and helps you move.

[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-biz--partner-111827?style=flat-square)](skills/biz-partner/SKILL.md)
[![Knowledge Pack](https://img.shields.io/badge/knowledge-40%20atoms-2563EB?style=flat-square)](skills/biz-partner/public-knowledge/USAGE.md)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-E11D48?style=flat-square)](LICENSE)

[中文](README.md) · [English](README_EN.md) · [Knowledge pack](skills/biz-partner/public-knowledge/USAGE.md) · [X / Twitter](https://x.com/ExpLang_Cn)

</div>

You do not need to learn a business framework or figure out the perfect question first. Describe the situation as it is.

It is built for individuals and small teams finding a side-business direction, validating an idea, or running a product and content operation.

No idea yet? It helps you find a direction.<br>
Already building? It examines the customer, product, price, and delivery model.<br>
Stuck? It turns the blockage into one step you can complete today.

Think of it as a partner that asks for evidence, remembers past decisions, and sometimes tells you to stop. You still make the final call.

## Install and start in 60 seconds

With Node.js installed, run:

```bash
npx skills add yuzaicn/biz-partner -g --skill biz-partner
```

Open a new conversation and load:

```text
$biz-partner
```

Then describe the situation:

```text
I want a side business I can validate in 30 days. I have eight hours a week, I know automation, I can reach 20 small e-commerce teams, and my test budget is under $150. I do not want to build a product first.
```

Biz Partner will not respond with a generic list of popular markets. It first identifies your reachable customers, constraints, and validation conditions. Then it proposes candidate directions, risky assumptions, first interviews, and stop conditions.

Once the Skill is active, or when the client supports implicit invocation, you can also start with `/biz ...`. If the current conversation already contains the context, use:

```text
/biz intervene
```

It reads the conversation, ranks the most useful directions, chooses one primary task, and starts. If a critical fact is missing, it asks one high-information question in the current turn.

## Bring it these situations

| Your situation | Say this | What it moves forward |
| --- | --- | --- |
| You have no business idea | `/biz I want a side business, but I do not know what fits me` | Forms three to five testable directions from your time, skills, resources, and reachable customers |
| You have an idea but little evidence | `/biz Help me judge whether anyone would pay for this` | Breaks down the customer, job, pain evidence, delivery cost, and smallest paid test |
| Customers keep saying it is expensive | `/biz Should I lower the price, change the customer, or change the product?` | Separates value, positioning, trust, price, and cost instead of defaulting to a discount |
| You want content that brings customers | `/biz Turn this product into topics, titles, and short-video scripts` | Sets the audience and goal, creates the content, and checks it before publishing |
| You know what to do but keep delaying | `/biz I have been stuck for two weeks. Give me one action I can finish today` | Diagnoses the blockage and creates a minimum action, checkpoint, and stop condition |
| Your team strongly disagrees | `/biz debate Should we keep building this product?` | Runs independent views, cross-examination, and synthesis while preserving disagreements for your decision |

Natural language works too. `/biz` simply makes the trigger explicit.

## How it works with you

Each run does five things:

1. Defines the problem that matters now.
2. Separates known facts, reasonable inferences, and unknowns.
3. Selects one highest-value task.
4. Proposes a next step with an observable result.
5. States success criteria, stop conditions, and actions that need your approval.

When evidence is missing, it says what is unknown and how to test it. Important actions such as writing files, publishing, paying, deleting data, or sending external messages remain under your control.

## Another installation option

The Agent Skills CLI above asks you to choose a target when it detects multiple Agent clients. Codex users can also use the built-in installer:

For Codex on macOS or Linux:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo yuzaicn/biz-partner \
  --path skills/biz-partner
```

Open a new conversation after installation, load `$biz-partner`, and then describe the real problem.

## Capability map

| Area | What it can do |
| --- | --- |
| Business judgment | Direction finding, customer identification, demand evidence, pricing, unit economics, benchmarks, and historical analogues |
| Product management | Product definition, MVP, priorities, acceptance criteria, metric trees, and experiment plans |
| Content and growth | Topics, titles, resonance checks, long and short content, short-video scripts, and pre-publishing risk checks |
| Personal action | Goal clarification, procrastination and rush diagnosis, action cards, learning plans, and reviews |
| Long-term governance | Decision records, folder knowledge bases, content assets, multi-agent workbenches, and read-only local Skill audits |

It does not dump every capability into one answer. By default, it advances the single most useful step.

## Built-in public knowledge

The public package includes a searchable, traceable knowledge pack. A knowledge atom is one judgment unit that can be found, cited, and combined on its own.

- 40 knowledge atoms: 30 independently worded atoms distilled from curated materials, plus 10 distilled from Yuzai's public writing.
- 9 methods for customer validation, business judgment, communication, content, action, and review.
- 48 task concepts: 18 runtime concepts and 30 selected concepts redefined for practical use.
- 40 retrieval cases that verify every atom can be found.

Explore the [knowledge-pack guide](skills/biz-partner/public-knowledge/USAGE.md), [methods](skills/biz-partner/public-knowledge/methods.md), [concept dictionary](skills/biz-partner/public-knowledge/concept-dictionary.md), and [structured manifest](skills/biz-partner/public-knowledge/manifest.json).

Curated materials stay anonymous in the public pack. Yuzai is named only when a Yuzai-derived atom materially supports the final judgment; retrieval alone does not trigger attribution. Yuzai is a registered external knowledge source, never the runtime user's identity.

## It can learn your context without defining you

Biz Partner can follow project and action progress, then propose updates to user preferences, project state, decision records, and working playbooks.

Long-term information starts as a proposal. It becomes active only after confirmation. Outdated or rejected information can be suppressed or deleted. More use can make the Skill better aligned with your constraints, but one conversation never becomes a permanent personality judgment.

## Limits

Biz Partner provides decision support and controlled workflows. It does not guarantee business success, platform approval, legal compliance, investment returns, or other real-world outcomes. Important decisions still require current evidence and human judgment.

## License and contact

This project uses the [PolyForm Noncommercial 1.0.0](LICENSE). It is noncommercial source-available, not OSI open source. Commercial use requires separate permission; refer to the license text for the governing terms.

Created by Yuzai · [X (Twitter) @ExpLang_Cn](https://x.com/ExpLang_Cn)
