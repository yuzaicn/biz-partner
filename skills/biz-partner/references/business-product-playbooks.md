# Business and Product Playbooks

## Contents

- 1. Shared execution constraints
- 2. Explore: find a business under real constraints
- 3. Diagnose: decide what is worth testing
- 4. Pricing / Customer: choose customers and test price
- 5. Benchmark / Historical Standard: transfer mechanisms, not surfaces
- 6. Product / PRD: define the product and acceptance
- 7. Shared completion check

本文件实现商业与产品任务的操作层。它不替代 `runtime-kernel.md`、`task-registry.md` 或
`output-contract.md`；执行顺序、权限、安全状态和 Handoff 不变量以这些文件为准。

## 1. 共同执行约束

### 1.1 任务身份

| Playbook | 当前入口 | Handoff `task_id` |
|---|---|---|
| Explore | `/biz explore` | `business.explore@1.0.0` |
| Diagnose | `/biz diagnose` | `business.diagnose@1.0.0` |
| Pricing | `/biz pricing` | `business.pricing@1.0.0` |
| Customer | `/biz customer` | `business.customer@1.0.0` |
| Benchmark | `/biz benchmark` | `research.benchmark@1.0.0` |
| Historical Standard | `/biz standard` | `research.standard@1.0.0` |
| Product / PRD | `/biz product` | `product.define@1.0.0` |

任务身份必须来自 `task-specs.jsonl`。不得把 `pricing`、`customer`、`benchmark` 或
`standard` 运行伪装成 `business.diagnose`；注册表缺失或版本不匹配时输出 `blocked`
Handoff，blocker 为 `unregistered_task_spec`，不能静默执行。

### 1.2 Evidence gate

所有输入先进入冻结的 CasePacket。只接受以下证据身份：

- `fact`：可定位到用户原话、文件、交易、行为、可观察结果或带日期的外部来源；
- `user_claim`：用户陈述但尚未独立核验的事实；
- `inference`：由事实或主张推导出的解释；
- `constraint`：时间、预算、地域、技能、权限、风险或不可做事项；
- `unknown`：会改变判断但仍缺失的信息。

知识原子是分析镜头，不是当前生意的现实证据。引用 atom 时必须保留 atom ID、来源、
locator、as-of、置信度、状态与适用边界；当前候选/private-research 原子不能写成普适规律。

- 不得将历史或总量指标外推为当前剩余量：例如“每单总工时 × 未完成项目数”不等于剩余工时，除非有项目级进度证据；缺失时将当前剩余量标为 `unknown`。

Evidence gate 只有四种结果：

1. `pass`：required slots 完整，且最低现实信号满足本 Playbook 的门槛；
2. `clarify`：缺失项可跨轮通过最多 3 个高信息问题补齐，但当前一轮只问 1 个；先问最可能改变路线、价格测试或停止条件的缺失事实，不得把全部 required slots 枚举成一个复合问题；
3. `blocked`：两轮没有新增证据、关键来源不可用、任务未注册或无法接触验证对象；
4. `safe_stop`：任务需要未授权副作用、敏感数据或高风险专业判断。

外部市场、价格、竞争者或历史资料需要当前性时，只能使用 CasePacket 中已有材料，或在
`network_read` 已获同意且 TaskSpec 允许时读取。Playbook 本身不授予工具权限。

### 1.3 Handoff 最低要求

每次执行先产出符合 `output-contract.md` 的 Handoff，再渲染中文。除状态特有字段外：

- `claims`：每个非 `unknown` claim 都引用 `evidence_refs`；
- `assumptions`：列出对结论有影响、但尚未验证的前提和置信度；
- `artifacts`：只放本 Playbook 的结构化产物，不把自然语言当跨任务协议；
- `rejected_options`：记录淘汰方案及证据理由，不写“感觉不好”；
- `open_questions`：只保留会改变下一决定的问题；
- `next_action`：包含 owner、期限或时间盒、完成标准；
- `stop_condition`：必须是可观察谓词；
- `approvals`：只描述待批准的目标/正文/范围，不代表已经获批；
- `proposed_patches`：只提出状态变更，不直接写入；
- `memory_proposal`：默认 `null`，用户明确确认后另行提交；
- `tool_trace`：只记录实际发生且已授权的读取；不得虚构调用。

### 1.4 Explore / Diagnose 证据与实验约束

- Explore 的每个机会假设必须完整保留 `user_advantage`、`maximum_unknown`、
  `assumptions`、`major_risks`、`route_changing_evidence`；不得因渲染简洁而省略、合并或
  用空值占位。`route_changing_evidence` 写明什么新证据会改变当前排序或路由，不等同于
  单次实验的 falsifier。
- 实验信号分三层记录：`problem_evidence` 是最近真实行为、当前替代及已付代价；
  `commitment_evidence` 是投入时间、数据、访问权、排期、进入具体成交步骤，或签署含明确
  范围、价格和双方义务的试点/订单；`payment_evidence` 只记录可核验的真实付款、到账或定金。
  口头“愿意”“接受”“感兴趣”只能作为弱 `user_claim`，不是付款证据；已签订单属于强承诺，
  但在资金实际发生前不得升级为付款证据。
- 临时样本数、时间盒、价格和判定阈值必须标记为 `provisional_parameter`，同时记录
  当前依据与 `adjustment_trigger`；不得写成跨客户、渠道或场景都成立的普适规律。
- claim 强度不得超过本轮实验实际控制的客户、场景、渠道、offer、价格和时间范围。
  未控制的变量进入 assumptions/limits；小样本未通过不能直接判整个方向失败。
- 未通过时先分类，再决定下一步和停止范围：问题不存在则停止该客户-场景的问题假设；
  触达失败则调整名单、渠道或触达方式，不推断需求；信任不足则补证明、转介绍或降低承诺风险；
  offer 范围不清则收窄结果、边界和条款后重测；价格问题则固定其他条件测试价格/套餐，
  只否定已测价格；时机问题则记录触发条件和复查日期，只停止当前时间窗。只有多个可比、
  受控测试持续支持同一结论时，才扩大停止范围，并明确仍未覆盖的人群与路径。

## 2. Explore：无点子时对话式寻找生意

### Trigger

- 用户明确表示没有生意点子、不知道适合做什么，或要求从个人条件出发寻找方向；
- 用户有多个模糊方向，但没有可比较的客户、问题和最小验证路径；
- 不适用于已经有具体客户、问题和 offer 的诊断，此时路由到 Diagnose。

### Required slots

- `constraints`：每周可投入时间、预算上限、地域/语言、不可接受风险；
- `resources`：可交付技能、经验、资产、渠道、可信关系或现有受众；
- `access_to_customers`：当前能直接接触的具体人群及接触方式；
- 建议但非硬门槛：收入目标、启动期限、偏好的交付方式、是否接受销售和服务工作。

### Evidence gate

- required slots 至少由用户主张支持，并能落到具体描述；“我什么都可以”不算有效约束；
- 至少存在一个可接触人群或一条获得现实需求信号的路径；否则先 `clarify`；
- 不要求用户已有产品、交易或市场报告；这是发现假设，不是证明机会成立；
- 两轮仍无法指出任何技能、资源、限制或可接触人群时，输出 `blocked`，不继续罗列项目。

### 步骤

1. 确认目标是副业、全职、现金流、学习还是长期资产，并记录时间范围。
2. 用不超过 3 个问题收集 required slots；优先问会淘汰最多方向的问题。
3. 从用户能接触的人群出发，列出他们在具体场景中反复出现、已有替代方案的问题。
4. 将事实、用户主张和推断分开；禁止把兴趣直接等同于购买需求。
5. 生成 3–5 个机会假设。每个必须包含：客户、场景/JTBD、初始 offer、触达方式、
   交付方式、主要成本变量、falsifier，以及不可省略的 `user_advantage`、
   `maximum_unknown`、`assumptions`、`major_risks`、`route_changing_evidence`。
6. 依据 `customer access`、现实信号、首次交易速度、交付可行性、损失上限进行相对比较；
   不使用没有数据支撑的精确市场规模或成功率。
7. 选择一个最便宜、最快产生反证的假设作为当前下一步；其余进入 rejected/backlog，
   不自动串行执行。

### 输出契约

`artifacts` 至少包含一个 `opportunity_hypotheses` 产物：

- 3–5 个假设及其 customer、job、offer、channel、delivery、cost variables；
- 每个假设的 supporting refs、falsifier，以及完整的 `user_advantage`、`maximum_unknown`、
  `assumptions`、`major_risks`、`route_changing_evidence`；
- 一张相对比较表，不产生伪精确总分；
- 当前选择、未选原因及什么新证据会改变选择。

`next_action.acceptance` 必须描述获得了什么现实反馈，而不是“完成调研”。

### 最小实验

默认将 48–72 小时作为标记为 `provisional_parameter` 的时间盒初值：向一小组明确且可接触的
潜在客户询问最近一次真实行为、当前替代方案和付出，不先介绍完整方案；随后用一个具体、
可交付的小 offer 请求下一步行动。
分别预声明并记录 `problem_evidence`、`commitment_evidence`、`payment_evidence`；签署试点或
订单归入强承诺，真实付款、到账或定金才进入付款证据，不得把口头接受或未履行的签署义务
升级为付款。样本、时间盒、价格、成本上限、通过信号和 falsifier 均按当前场景设定；其中
临时值标记 `provisional_parameter`，附当前依据和 `adjustment_trigger`。

### 停止/升级条件

- 没有可接触客户或用户拒绝补充约束：`blocked`；
- 一个假设获得具体问题/行动/付费信号：发出 `needs_decision` 或 `needs_action`，不自动扩张；
- 需要最新市场/对标证据：发出 `needs_benchmark`；
- 涉及许可、医疗、金融、法律或敏感数据：`safe_stop`，并写入
  `requires_professional_escalation` blocker；
- 小样本未通过：按 1.4 分类问题不存在、触达失败、信任不足、offer 范围不清、价格或时机，
  执行对应下一步并限定停止范围，不直接淘汰整个方向；
- 同一路径两轮无新证据：停止生成更多点子。

### Optional public knowledge pack

Use only atoms whose pack is release-eligible, portable, and licensed. Knowledge can shape a hypothesis but cannot replace current customer, cost, or outcome evidence.

### 不得做的事

- 不根据人格标签、星座、年龄或单一兴趣断言“最适合你的生意”；
- 不虚构市场规模、客户采访、交易、利润、竞争者或用户能力；
- 不输出几十个无验证路径的点子清单；
- 不把用户的收入愿望当成需求证据；
- 不代替用户联系客户、发布内容、收款或保存长期画像。

## 3. Diagnose：判断生意是否值得继续验证

### Trigger

- 用户已有客户、问题或产品想法，要求判断“能不能做”“为什么卖不动”或下一步；
- 需要同时检查客户、JTBD、offer、渠道、交付、定价/成本、竞争和风险；
- 若问题只剩客户选择或价格设计，进入 Pricing / Customer 子模式。

### Required slots

- `customer`：具体客户/购买单位，不能只是“所有人”；
- `problem_or_job`：发生场景、触发、期望结果与当前替代；
- `offer_or_idea`：交付内容、边界、形式和预期结果；
- `decision`：本次要决定继续、修改、暂停还是验证哪个假设；
- 建议输入：渠道、价格、变量成本、交付能力、已有行为/交易/留存/拒绝信号。

### Evidence gate

- 至少一个可定位的现实信号：客户原话/行为、询价、试用、交易、流失、交付记录、
  支持问题或带日期的可核验市场材料；纯愿望不通过；
- 用户转述可以作为 `user_claim`，但不能升级为已核验事实；
- 缺 customer、JTBD 或 offer 中任一项时先 `clarify`；两轮仍只有愿望则 `blocked`；
- 没有成本或价格数据时仍可诊断其他环节，但单位经济必须标 `unknown`。

### 步骤

1. 明确当前决定、时间范围、验收标准和最大可承受损失。
2. 建立 evidence ledger：confirmed facts、user claims、inferences、conflicts、unknowns。
3. 检查 customer/JTBD：触发频率、紧迫性、现有替代、谁使用/付费/批准、切换阻力。
4. 检查 offer：承诺结果、交付机制、范围、非目标、证据和失败责任。
5. 检查渠道：客户是否可触达、获客动作是否可重复、信任如何建立。
6. 检查单位经济：价格、直接变动成本、交付/支持负担、退款/失败风险；未知值只列变量和
   测量办法，不填行业平均数。
7. 检查竞争和替代：包括“不购买、自行处理、维持现状”，不只看同类产品。
8. 找出一个约束全局的关键障碍，形成 1–3 个可证伪假设及反例。
9. 设计一个以 7 天为 `provisional_parameter` 初值、损失封顶、能改变决定的实验，并写明
   当前依据和 `adjustment_trigger`。

### 输出契约

`claims` 中的当前判断只能是 `supported`、`conditional`、`weak` 或 `unassessable` 的语义，
禁止“必成/必败”。`artifacts` 至少包含 `business_diagnosis`：

- 决定与当前判断；
- 客户/JTBD、offer、渠道、单位经济、竞争、交付、风险逐项状态；
- 最大证据缺口、关键障碍、假设、反证和 rejected options；
- 一个以前述临时时间盒为初值的实验及 owner、期限、成本上限、通过信号、falsifier、
  `adjustment_trigger`。

### 最小实验

只验证当前最关键假设，并分别声明要获得的 `problem_evidence`、`commitment_evidence` 和
`payment_evidence`。优先选择真实行为信号，例如真实付款或订金、签署含明确义务的试点、
预约、迁移、连续使用或完成关键任务；其中签署试点属于强承诺，只有真实资金动作属于付款证据。
若尚不适合收费，则观察客户最近一次真实行为和替代成本。口头“愿意/接受”、点赞、礼貌性
“感兴趣”或模型评分不能作为付款证据，也不能单独判定成立。临时样本、时间盒、价格和阈值标记
`provisional_parameter`，附当前依据与
`adjustment_trigger`；结论只覆盖本轮实际控制的对象和条件。

### 停止/升级条件

- 只有愿望且两轮没有现实信号：`blocked`；
- 价格或客户定义成为主瓶颈：进入 Pricing / Customer 子模式；
- 缺可比对象或历史机制：分别发出 `needs_benchmark`、`needs_standard`；
- 模型成立但用户卡在执行：发出 `needs_action`；
- 高风险专业判断、未授权外部动作或敏感数据：`safe_stop`，并写入
  `requires_professional_escalation` blocker；
- 实验命中预先声明的 falsifier：按 1.4 先归因并记录，不事后改门槛；停止范围只覆盖被该
  实验控制和证伪的客户、场景、渠道、offer、价格或时间窗，小样本不直接判整个方向失败。

### Optional public knowledge pack

Use only atoms whose pack is release-eligible, portable, and licensed. Knowledge can shape a hypothesis but cannot replace current customer, cost, or outcome evidence.

### 不得做的事

- 不用一个总分掩盖证据缺口或不同风险；
- 不把可获取用户数、浏览量或受访者称赞等同付费需求；
- 不用知识原子替代当前客户、成本和交付证据；
- 不承诺收入、增长、融资、合规或经营结果；
- 不自动执行下一 Playbook、写项目状态或发起外部实验。

## 4. Pricing / Customer：客户选择与价格假设

### Trigger

- `customer` 子模式：用户不清楚谁最可能购买、使用者与付款者不同，或反馈互相冲突；
- `pricing` 子模式：用户需要价格、套餐、价值计量、毛利边界或“客户说贵”的诊断；
- 两者同时不清晰时先 Customer，再 Pricing；不要先报一个价格数字。

### Required slots

Customer required slots：`candidate_customer`, `situation`, `desired_progress`；再补充
接触渠道、用户/付款者/批准者、当前替代和本次 `decision`。  
Pricing required slots：`customer`, `offer`, `price`, `cost_or_capacity`；再补充交付单位、
价格计量单位、直接变动成本、支持/失败成本、当前价格或候选区间、
客户可见价值及替代成本。

### Evidence gate

- Customer 至少需要一个具体可接触细分和一个问题/行为信号；否则回到 Explore；
- Pricing 必须有明确 offer、交付单位和成本变量。成本缺失时只输出测量表，不输出建议价；
- “太贵”必须保留原场景：谁说、在什么 offer/条款/时点、选择了什么替代；
- 价格、竞品和平台费率若要求当前值，必须有带日期来源或获准 `network_read`。

### 步骤

1. 声明当前是 `customer`、`pricing` 或顺序执行，且一次只解决一个决策。
2. Customer：按共同场景、触发、替代、购买角色、可触达性和切换阻力收窄细分。
3. Customer：区分用户、受益者、付款者和批准者，记录各自成功标准与反对理由。
4. Pricing：定义价值计量单位和交付单位；列出所有用户提供的成本变量及未知值。
5. Pricing：建立成本底线、客户价值/替代锚点和可交付差异三个视角；不凭空填数。
6. 形成 1–3 个 customer 或 packaging/price hypotheses，明确每个假设为何可能错。
7. 设计同一范围、可比较条款下的访谈、报价或付费试单；事前声明记录表和判定阈值。

### 输出契约

Customer 的 `artifacts` 包含 `customer_hypothesis`：细分、场景/JTBD、购买角色、现有替代、
证据信号、触达路径、反对理由、falsifier。  
Pricing 的 `artifacts` 包含 `pricing_hypothesis`：offer/边界、计量单位、成本变量、候选套餐/
区间、价值锚点、未知值、试验设计和停止条件。

没有成本数据时，`claims` 必须把价格结论标为 `unknown`，`next_action` 指向成本测量或真实报价，
不能以“行业通常”填补。

### 最小实验

- Customer：对一组同类、可触达对象记录最近一次问题、当前替代、已付成本和下一行动；
- Pricing：在相同范围和清楚条款下，向少量合格客户提出预先声明的套餐/报价，记录接受、
  反报价、拒绝原因和实际下一步。不要用含糊的“你愿意付多少”代替真实选择。

样本、期限、成本上限和通过阈值必须在执行前写入 Handoff，由当前场景决定。

### 停止/升级条件

- 无法接触候选客户：`blocked` 或回 Explore；
- 成本/交付单位未知：停止给价，先测量；
- 客户和付款者冲突且无人能决定：`needs_clarification`；
- 需要当前竞品套餐：`needs_benchmark`；
- 涉及受监管价格、歧视性定价、金融/医疗/法律承诺：`safe_stop`，并写入
  `requires_professional_escalation` blocker；
- 已有重复付费和可交付证据：发出 `needs_decision`，不自动涨价或扩量。

### Optional public knowledge pack

Use only atoms whose pack is release-eligible, portable, and licensed. Knowledge can shape a hypothesis but cannot replace current customer, cost, or outcome evidence.

### 不得做的事

- 不给缺少成本、条款和客户证据的“标准答案价”；
- 不把低价当作默认竞争策略，也不把高价包装成价值证明；
- 不隐瞒价格差异、虚构稀缺、假装已有客户或制造虚假社会证明；
- 不把用户、付款者和批准者混成一个“客户画像”；
- 不自动改价、发报价、收费、发布套餐或写入 CRM/项目文件。

## 5. Benchmark / Historical Standard：对标与历史同构

### Trigger

- Benchmark：用户需要找现实对标、比较产品/商业模式，或提炼可迁移做法；
- Historical Standard：用户需要从历史同构案例寻找反复出现的机制和失效条件；
- 两种模式都服务一个当前决定，不做无边界的资料堆积。

### Required slots

Benchmark required slots：`target_outcome`, `comparison_scope`；再补充 `focal_offer`,
`customer`, `decision`, `comparison_dimensions`，以及用户提供的候选对象或获准寻找候选的范围。  
Historical Standard required slots：`current_problem`, `structural_fingerprint`；再补充
`proposed_mechanism`, `decision`, `outcome_of_interest`, `structural_dimensions`，以及可核验
历史来源或获准读取的范围。

### Evidence gate

- Benchmark 每个比较值必须有对象、locator 和 as-of；营销文案只能证明其自我表述；
- Historical Standard 至少有一个可定位来源，但单一案例只生成候选机制，不能称“反复有效”；
- 没有获准来源时，只输出 research plan 或 `blocked`，不凭模型记忆补案例；
- 相似行业、人物或口号不算同构；必须比较客户/参与者、激励、约束、分配、反馈和失败路径；
- 过期、法域不同或平台机制不同的证据必须进入 assumptions/limits。

### 步骤

1. 固定当前决定和比较问题，删除与决定无关的维度。
2. Benchmark 选择 2–5 个功能、客户、渠道或商业机制可比的对象，说明入选/排除标准。
3. Benchmark 用同一时间窗口和维度记录 customer、JTBD、offer、price/metric、channel、
   delivery、trust、economics signals；未知就留空。
4. 将每个观察拆成 `surface feature`、`underlying mechanism`、`required condition` 和
   `non-transferable constraint`。
5. Historical Standard 先把当前问题写成因果机制，再寻找支持案例、反例和失败案例。
6. 按参与者、激励、资源约束、信息结构、反馈周期、权力/分配和外部条件做结构映射。
7. 输出共同机制、关键差异、替代解释和可证伪预测；不按案例数量投票决定真伪。
8. 只迁移一个可逆机制，设计当前环境中的小实验。

### 输出契约

Benchmark 的 `artifacts` 包含：`benchmark_matrix`、`transferable_mechanisms`、
`non_transferable_features`、source/as-of、证据缺口和一个迁移实验。  
Historical Standard 的 `artifacts` 包含：`analogue_cards`、结构映射、共同机制、差异、反例、
替代解释、当前预测和一个验证实验。

任何“有效”claim 都必须回到当前结果证据；历史来源只能支持“该案例中发生过什么”及有限解释。

### 最小实验

选择一个最小、可逆、可观察的机制，而不是复制完整产品或话术。记录当前 baseline、变更、
预期中间信号、失败信号、成本上限和复原方式。Historical Standard 还必须写出：若类比成立，
在当前环境下一步应观察到什么；未出现则降低类比置信度。

### 停止/升级条件

- Benchmark/Standard TaskSpec 缺失或版本不匹配：`blocked`，不得改用其他任务 ID；
- 没有可定位来源、只有二手口号或相似性只在表面：`blocked`；
- 需要最新外部证据但无 `network_read` 同意：给只读替代或 `blocked`；
- 发现法域、时代、平台、客户或激励结构关键不同：停止迁移，保留为反例；
- 涉及复制受保护内容、冒充、规避规则或未授权抓取：`safe_stop`；
- 可迁移机制已形成：发出 `needs_decision` 或 `needs_action`，不直接实施。

### Optional public knowledge pack

Use only atoms whose pack is release-eligible, portable, and licensed. Knowledge can shape a hypothesis but cannot replace current customer, cost, or outcome evidence.

### 不得做的事

- 不伪造公司价格、指标、发布日期、历史事件、作者观点或来源；
- 不把相关性、表面相似或幸存案例当成因果；
- 不复制对标方的品牌、受保护表达、界面或规避平台规则的做法；
- 不用单一案例宣称“历史反复证明”；
- 不把过期证据渲染为当前事实，也不自动访问网页或实施迁移。

## 6. Product / PRD：产品经理工作流

### Trigger

- 用户要求定义或评审产品、PRD、MVP、优先级、指标树、实验 backlog 或验收标准；
- 用户有客户问题但解决方案过大、功能堆积或团队对“完成”理解不一致；
- 若客户/JTBD 尚不存在，先 `clarify` 或发出 Customer 子模式，不虚构需求。

### Required slots

- `user`：主要用户及购买/批准角色；
- `problem`：具体场景、触发、当前行为和未满足结果；
- `scenario`：端到端任务起点、关键步骤和完成状态；
- `non_goals`：本版本明确不解决什么；
- 建议输入：证据、业务目标、约束、owner、基线、成功信号、依赖与发布日期。

### Evidence gate

- “做一个成功产品”“加 AI”“对标某产品”不构成 problem evidence；
- 至少一个 user/problem/scenario 组合可回到 CasePacket；否则 `clarify`；
- 没有真实用户证据时可交付 discovery PRD，但必须标记假设，不能进入 build-ready；
- 需要写仓库、创建工单、发布或改生产时，当前 Playbook 只预览；相应权限另行确认。

### 步骤

1. 写出产品决定、目标用户、问题/JTBD、使用场景、证据和验收对象。
2. 区分 outcome、solution 和 feature request；把未经证实的功能放入 assumptions。
3. 定义目标与 non-goals，列出范围边界、依赖、风险和不处理的异常场景。
4. 描述当前用户流程和最大摩擦，选择一个端到端 MVP thin slice。
5. 定义功能/行为要求，并为关键路径写可观察验收条件；避免“体验良好”等不可测语句。
6. 建立指标树：结果指标、领先信号、质量/风险 guardrail、基线和数据来源；缺基线则列 unknown。
7. 将 backlog 按是否服务当前问题、依赖关系、证据强度和失败成本排序；记录 rejected options。
8. 设计最小用户测试或 concierge 流程，明确样本、任务、观察项、通过/失败信号。
9. 输出发布前置条件和停止条件；不得把 PRD 完成等同产品成功。

### 输出契约

`artifacts` 至少包含 `prd`：

- context / decision / owner；
- user、payer/approver、problem/JTBD、scenario 和 evidence refs；
- goals、non-goals、assumptions、constraints、dependencies、risks；
- MVP scope、requirements、edge cases、acceptance criteria；
- metric tree、baseline/unknowns、experiment backlog；
- release gates、rejected options、next action 和 stop condition。

若证据不足，artifact 类型改为 `discovery_prd`，并在 `claims` 中把 solution fit 标记为 `unknown`。

### 最小实验

选择一个不依赖完整构建的端到端任务测试：纸面/静态流程、人工 concierge、已有工具组合或
受控原型均可。让目标用户完成一个真实任务，观察是否完成、在哪里失败、需要多少人工支持，
并记录结果；不以“喜欢这个想法”作为通过标准。Playbook 只设计实验，不虚构已执行工具。

### 停止/升级条件

- 缺 user、problem、scenario 或 non-goals，且会改变范围：`clarify`；
- 请求只有“让它成功”且用户拒绝定义验收：`blocked`；
- 无真实用户证据：停止 build-ready 结论，保持 discovery PRD；
- 涉及医疗、金融、法律、安全、儿童或敏感数据：`safe_stop`，并写入
  `requires_professional_escalation` blocker；
- 涉及本地写入、工单、发布、收费或生产变更：只生成 approval preview；
- 最小实验推翻 problem/solution 假设：停止扩建，发出 `needs_decision`。

### Optional public knowledge pack

Use only atoms whose pack is release-eligible, portable, and licensed. Knowledge can shape a hypothesis but cannot replace current customer, cost, or outcome evidence.

### 不得做的事

- 不把功能清单当 PRD，不把 PRD 当客户证据；
- 不虚构用户研究、基线、指标、工期、工程约束或验收结果；
- 不在没有 non-goals 和验收条件时宣布 build-ready；
- 不静默扩大 MVP、自动排期、创建工单、写代码、发布或改生产；
- 不承诺采用某功能就一定增长、留存或盈利。

## 7. 共用完成检查

在渲染最终答复前逐项检查：

1. CasePacket 已冻结，required slots 与 evidence gate 结果可定位；
2. 当前只运行一个 Playbook/子模式；
3. 所有现实判断回到 CasePacket evidence，atom 只作为受限分析镜头；
4. 输出包含一个当前决定、一个最小实验、一个 next action 和一个可观察 stop condition；
5. 未经授权没有读取范围外资料、写文件、联系客户、报价、收费、发布或改生产；
6. Handoff 通过 JSON Schema 与 `scripts/validate_contracts.py`；
7. 后续任务只发出 signal，不自动执行；长期记忆保持 `null`，直到用户明确确认。
