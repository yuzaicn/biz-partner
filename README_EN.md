<div align="center">

# Biz Partner

### Make the next business decision testable

[![Agent Skill](https://img.shields.io/badge/Agent%20Skill-biz--partner-111827?style=flat-square)](skills/biz-partner/SKILL.md)
[![Knowledge Pack](https://img.shields.io/badge/knowledge-60%20atoms-2563EB?style=flat-square)](skills/biz-partner/public-knowledge/USAGE.md)
[![License](https://img.shields.io/badge/license-PolyForm%20Noncommercial-E11D48?style=flat-square)](LICENSE)

[中文](README.md) · [English](README_EN.md) · [Knowledge pack (Chinese)](skills/biz-partner/public-knowledge/USAGE.md) · [X / Twitter](https://x.com/ExpLang_Cn)

</div>

Start with the situation you actually have.

The conversation can be in English. The built-in knowledge pack and its retrieval vocabulary are currently Chinese-first, so English-only queries may use less of the packaged knowledge.

No idea yet? Start with who you can reach, what you can deliver, and how much time you really have.<br>
Already have one? Look at the customer, the reason to buy, the price, and the delivery promise.<br>
Stuck? Make the work smaller instead of adding another plan.

## Start here

With Node.js installed, run:

```bash
npx skills add yuzaicn/biz-partner -g --skill biz-partner
```

Open a new conversation and load the Skill:

```text
$biz-partner
```

Then give it a real case:

```text
I want a side business I can validate in 30 days. I have eight hours a week, I know automation, I can reach 20 small e-commerce teams, and my test budget is under $150. I do not want to build a product first.
```

It will not start with a catalogue of popular markets. It starts with your access to customers, your delivery limits, and what you can afford to lose. The first recommendation is a test, not a promise.

When the Skill is already active, `/biz ...` works as a direct entry point. If the useful context is already in the conversation, use:

```text
/biz intervene
```

That tells Biz Partner to read the conversation and decide what needs attention now. If one missing fact could change the decision, it asks for that fact first.

## Try it when

| Situation | Example | What happens first |
| --- | --- | --- |
| You need a business direction | `/biz I want a side business, but I do not know what fits me` | Narrow the field around customers you can actually reach |
| You have an idea but little evidence | `/biz Would anyone pay for this?` | Find the riskiest assumption and design a paid test |
| Customers keep saying the price is high | `/biz Should I lower the price, change the customer, or change the offer?` | Separate a price problem from weak value, trust, or costly delivery |
| You need content that can bring customers | `/biz Turn this offer into topics, titles, and a short-video script` | Establish the audience and factual anchor before drafting |
| You keep postponing the work | `/biz Give me one action I can finish today` | Shrink the task and make “done” observable |

For a disputed decision, `/biz debate ...` can run independent reviews and cross-examination when the host supports real sub-agents. Otherwise it says plainly that it is doing a structured multi-perspective review.

## How it makes a call

Biz Partner separates what happened from what is assumed, then looks for the point most likely to change the result.

When the evidence is good enough, it moves one step. When it is not, it asks for the missing fact. Tests and investments include a finish line and a reason to stop.

Files, publishing, payments, deletion, and external messages remain under your control. The exact target and scope must be shown before anything is changed or sent.

See the [Skill entry file](skills/biz-partner/SKILL.md) for its other capabilities and operating boundaries.

## What it has to work with

The knowledge pack has 60 knowledge atoms, 12 methods, 30 work terms, 50 analytical concepts, and 84 retrieval regression cases. Together they form 163 linkable nodes and 477 declared relationships. Each layer has a different job:

| Layer | In plain language |
| --- | --- |
| Knowledge atoms | One idea, rule, or practice that can be retrieved and judged on its own. |
| Methods | A usable process assembled from related atoms, with guidance on when to use it, what to do, and when to stop. |
| Work dictionary and analytical concepts | The work dictionary gives shared meanings to terms such as customer, product, and evidence; analytical concepts offer another way to break down a problem when needed. |
| Structured data | Machine-readable, checkable JSON/JSONL records for atoms, terms, concepts, and tests. |
| Knowledge network | Every source, atom, concept, and method has a stable link. It shows the source, concept, method, and usage relationships that are actually declared; it does not invent missing support, refinement, or contradiction links. |
| Retrieval regression | Fixed questions paired with expected atoms, rerun after a pack change to catch missing matches. |

Open the [online knowledge network](skills/biz-partner/public-knowledge/knowledge-network.md) or the [machine-readable graph](skills/biz-partner/public-knowledge/knowledge-graph.json). The repository also includes the [knowledge-pack guide (Chinese)](skills/biz-partner/public-knowledge/USAGE.md), [12 methods (Chinese)](skills/biz-partner/public-knowledge/methods.md), [work dictionary and analytical concepts (Chinese)](skills/biz-partner/public-knowledge/concept-dictionary.md), [atom data](skills/biz-partner/public-knowledge/atoms.jsonl), [method data](skills/biz-partner/public-knowledge/methods.jsonl), [concept data](skills/biz-partner/public-knowledge/concepts.jsonl), [retrieval regression data](skills/biz-partner/public-knowledge/retrieval-cases.jsonl), and [knowledge-pack manifest and version information](skills/biz-partner/public-knowledge/manifest.json).

## It can learn new material without silently rewriting itself

Ask it to analyze an approved document, project review, or source set. It first prepares candidate atoms, methods, concepts, dictionary terms, relationships, and retrieval questions, then checks duplicates, conflicts, privacy, rights, and scope. Local evidence files are checked against their actual hashes; web and conversation evidence stays visibly unverified when it cannot be checked locally.

Candidates do not become active immediately. Only after you confirm the exact change preview will it create a new private knowledge-pack version inside the project you selected. Search results expose the atom rule or procedure, concept boundaries and common misuse, and method inputs and checks. Older versions remain available, including a new revision that restores the pack to an empty state. The workflow never silently changes the built-in public pack, commits Git changes, or uploads anything to GitHub.

Confirmed project records can carry useful context into later conversations. New preferences and judgments begin as proposals; they become active only after confirmation. Outdated or incorrect information can be corrected or suppressed. One conversation does not become a permanent profile.

## Codex installer

Codex users can install without the Agent Skills CLI:

```bash
python3 ~/.codex/skills/.system/skill-installer/scripts/install-skill-from-github.py \
  --repo yuzaicn/biz-partner \
  --path skills/biz-partner
```

Start a new conversation after installation and load `$biz-partner`.

## Limits and license

Biz Partner supports decisions and controlled workflows. It does not guarantee business success, platform approval, legal compliance, investment returns, or any other real-world result.

The project uses [PolyForm Noncommercial 1.0.0](LICENSE). It is noncommercial source-available software, not OSI open source. Commercial use requires separate permission.

Created by Yuzai · [X (Twitter) @ExpLang_Cn](https://x.com/ExpLang_Cn)
