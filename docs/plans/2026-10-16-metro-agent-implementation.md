# MetroInsight Agent Implementation Plan

> 执行要求：以根 `AGENTS.md` 为准，按任务逐项实施、验证、记录。用户已授权接手与规划，不需要就常规本地实施反复确认。本文是未来执行计划，不是已完成清单。

**Goal:** 将历史地铁社媒分析升级为可复现、可评测、具备工具调用与证据报告能力的AI Agent作品集。

**Architecture:** Python单体应用，LangGraph编排受控任务循环，结构化工具操作SQLite，检索返回可追溯证据，校验节点约束报告。批量数据加工与按需分析分离，历史文件只读，离线合成模式独立可运行。

**Tech Stack:** Python 3.12初始目标、uv、Pydantic、LangGraph、SQLite/FTS5、FastAPI、pytest、Ruff、简单Web页；embedding索引、Langfuse、Ragas、Docker按阶段验证加入。版本在首次安装时核对并写入锁文件，不使用本计划猜测的版本号。

---

## 1 状态、时间与实施顺序

| 阶段 | 目的 | 状态 | 交付 |
| --- | --- | --- | --- |
| P0 | 接手、调查、确定建设边界 | **本轮完成** | 审查/调研/设计/本计划/AGENTS/日志 |
| P1 | 工程基线与数据可重放 | 未开始 | 新包、依赖锁定、离线CLI、导入及存储校验 |
| P2 | 数据字典、黄金集与基线 | 未开始 | 版本化数据集、标注规范、独立评测脚本 |
| P3 | 工具循环与证据检索 | 未开始 | 业务工具、LangGraph任务循环、可追溯报告 |
| P4 | 可靠性与可观测性 | 未开始 | 重试、幂等、checkpoint、成本、故障记录 |
| P5 | 交互交付、实验与求职材料 | 未开始 | API/Web、对照实验、复现指南、演示和简历证据 |
| P6 | 有收益再做的扩展 | 可选 | OCR增益、MCP、多Agent或其他扩展 |

建议按6–8周、每周12–18小时安排，约80–120小时，含学习和标注复核；这是初始工作量估算，不是交付保证。没有硬截止日期，按验收推进。预计人工金标复核是关键依赖；其准备期间可以继续工程和检索任务。

## 2 目标目录

```text
社交媒体/
├── pyproject.toml / uv.lock / .python-version
├── .env.example
├── src/metro_agent/
│   ├── cli.py / config.py
│   ├── domain/schemas.py / labels.py
│   ├── ingestion/xhs.py / weibo.py / manifest.py
│   ├── storage/db.py / migrations.py
│   ├── models/client.py / fake.py
│   ├── annotation/pipeline.py
│   ├── retrieval/index.py / search.py
│   ├── tools/dataset.py / aggregate.py / evidence.py / timeline.py
│   ├── agent/state.py / graph.py / policy.py
│   ├── reporting/schema.py / verify.py / render.py
│   ├── observability/traces.py / usage.py
│   └── api/app.py / web/
├── examples/synthetic/       可提交的人工构造样例，明确标synthetic
├── tests/                   第一方功能/集成/恢复测试
├── evals/                   数据集manifest、任务rubric、运行与评分脚本
├── configs/labels/           有版本的标签与映射
├── data/                    忽略，私有清洗数据与索引
├── artifacts/               忽略，运行输出
├── docs/                    设计、数据卡、评测、日志、面试材料
└── 既有历史目录              验证迁移完成前继续保留
```

所有文件列表均为计划新增路径；本轮未创建`src/`、`pyproject.toml`或`uv.lock`。下文中 `uv run metro-agent ...` 的接口是**待实现约定**，不能当作现在已可运行的命令。

## 3 P1 先恢复可复现工程

### T01 建立工程骨架并解决标准库冲突

新增：`pyproject.toml`、`.python-version`、`src/metro_agent/__init__.py`、`cli.py`、`config.py`、`.env.example`、`tests/test_imports.py`。修改：README复现段落。

步骤：

1. 核对Python/uv可执行文件、运行架构、网络与包索引；如缺uv，按官方安装方式准备，禁止复用混装wheel环境。
2. 建立src包与CLI，声明必要依赖和开发依赖，安装成功后生成锁文件，保留旧`platform/.venv`不动。
3. 新入口必须从项目根和临时工作目录都能导入。保留历史目录时，使用隔离启动方式或显式移除其导入影响；在实际验证前不能宣称包名问题已解决。
4. 设计最终历史归档路径及回滚清单。只有确认不会丢数据、且新入口不再依赖旧路径后，才迁移/归档旧`platform`；不能只新增src包而忽略根目录仍遮蔽标准库的问题。
5. 验证`platform.system()`来自标准库，pytest与关键第三方库正常导入，`metro-agent --help`可用；记录实际命令与版本。

验收：在清洁环境使用锁文件安装成功；无秘钥、无原始数据也能打开CLI；根目录旧包名不会再次破坏依赖导入。根Git初始化可在忽略规则审核后本地完成，不能无筛选`git add .`，不触发上传。

### T02 统一schema、导入与存储

新增：`domain/schemas.py`、`domain/labels.py`、`ingestion/xhs.py`、`weibo.py`、`manifest.py`、`storage/db.py`、`migrations.py`；测试`test_ingestion.py`、`test_storage.py`。参考：历史`schema.py`、`xhs_loader.py`、`storage/db.py`。

步骤：

1. 写最小合成fixture，涵盖多平台同ID、缺字段、坏JSON、未知时间、重复行和独立评论。
2. 先写边界测试：不同平台同ID不能覆盖；缺ID不可作为成功记录；非法标签进入失败/待复核状态；坏行计数可见。
3. 使用Pydantic区分原文、OCR、标注、证据、时间与来源。ID始终用字符串；旧Excel数值ID可能失真，先核对，不能把文本哈希悄悄当原ID。
4. 新建版本化库文件导入，不覆盖旧DB；对大CSV使用迭代器/批处理，避免一次读入全部。每条导入记录可回到来源文件与行号。
5. 对已有80条内容、571条评论做只读对照，核对去重、字段和时间；对旧微博先小样本，不立即全量跑LLM。

验收：合成边界测试通过；实际导入有输入/成功/跳过/失败计数，和原始文件对账；数据版本、来源哈希可查询。原始数据库哈希保持不变。

### T03 无密钥端到端演示

新增：`models/client.py`、`models/fake.py`、`annotation/pipeline.py`、`examples/synthetic/`、`tests/test_offline_demo.py`。参考：历史LLM客户端、分类和抽取逻辑。

步骤：

1. 定义模型适配协议，输出包含结果、模型版本、usage、错误；fake实现仅用于明确标注的工程演示。
2. 迁移清洗/标注流程，严格校验输出，原文和图片文字分开保存；去重先于模型调用。
3. 用少量合成数据完成“导入→分析→写新库→统计→报告”，不读取真实密钥、不发网络请求。
4. 测试一次部分失败后仍有可检查状态；失败项不能processed=True。
5. 写明离线模式的含义，并让输出页面、日志和报告都标注synthetic。

计划验证命令：`uv sync --frozen`、`uv run ruff check .`、`uv run pytest tests/test_imports.py tests/test_ingestion.py tests/test_storage.py tests/test_offline_demo.py`、`uv run metro-agent demo --offline --output artifacts/demo`。

P1退出门槛：上述命令按实际实现修订并执行通过；README从零可复现；不宣称真实模型效果。

## 4 P2 建立数据字典与可信评测

### T04 数据分层、标签与标注说明

新增：`configs/labels/v1.yaml`、`legacy_c1_c9_map.yaml`、`docs/data/data-card.md`、`docs/data/annotation-guide.md`、`evals/build_dataset.py`、`evals/dataset_manifest.json`、`tests/test_splits.py`。

步骤：

1. 逐项核对C1-C9、0、空值、` C5`、`c9`和机器预测来源；词表、映射和丢失状态写入数据字典，不能自动把0当无关金标。
2. 对ID、文本归一化哈希、近重复、同事件建立group，保留原始记录与清洗后的关联。
3. 建立人工标注示例，覆盖无关、正负中混合情绪、多维度、事件候选、缺时间、反讽和信息冲突；对边界给可执行规则。
4. 先做40条标注试点，记录分歧和修订。AI可提出预标注，但未经人复核的只能是银标，不能直接称黄金集。
5. 冻结开发/测试分组和哈希，任何few-shot只从开发部分抽取，测试集不能反哺提示词。

样本目标：先获得200条独立人工复核数据，再扩到约400条；按可用来源与任务类型分层。过去80条小红书笔记已参与多次prompt调优，全部进入历史开发诊断集，**不计入新版盲测**。若盲测只有旧微博，就明确报告只验证该来源，不能声称跨平台泛化。

用户参与点：在已有40条规范与分歧表准备好后安排一次具体复核，尽量每次只需核对少量争议案例。用户未复核时继续工程与银标实验，并明确标记质量状态。

### T05 传统与固定流程基线

新增：`evals/run_baselines.py`、`evals/metrics.py`、`docs/evaluation/baselines.md`、`tests/test_metrics.py`；保存输出到`artifacts/evals/<run_id>/`。

步骤：

1. 先建立标签多数类/关键词与TF-IDF+LinearSVC基线，训练与测试任务定义一致；不直接沿用旧SVM脚本的历史分数。
2. 所有分词、特征和重采样只在训练折内拟合；首选类别权重，若用SMOTE必须位于正确交叉验证Pipeline中。
3. 对同一开发/测试切分运行单次LLM分类/固定workflow，真实调用前先锁定模型、prompt和调用额度。
4. 报告相关性、情感、维度和事件候选各自指标，不把不同任务的F1相互比较；列逐类样本数和混淆案例。
5. 附数据/脚本/配置哈希、失败项与指标分母；首次结果不好也保留。

计划命令：`uv run python evals/build_dataset.py --config configs/labels/v1.yaml`、`uv run python evals/run_baselines.py --manifest evals/dataset_manifest.json --mode offline`。真实模型实验使用独立`--mode live`并核验预算，不与offline分数混合。

P2退出门槛：数据字典和切分可审查；基础指标脚本通过人工可算的小例子；有正式基线或明确标注的银标暂定结果。最终简历效果指标仍等待正式金标盲测。

## 5 P3 建设Agent与证据检索

### T06 业务工具先独立实现

新增：`tools/dataset.py`、`aggregate.py`、`evidence.py`、`timeline.py`；测试`test_tools.py`、`test_tool_boundaries.py`。

步骤：

1. 每个工具写schema、允许的筛选项、边界与错误输出，使用设计文档中的接口清单。
2. 用小型可手算fixture验证维度重叠、评论粒度、有效分母、时间窗边界及缺失值。
3. 实现参数化SQL、结果行数上限、run可见数据范围和固定输出路径；拒绝任意SQL/shell/文件路径。
4. `retrieve_evidence`先返回带ID和出处的关键词结果，工具可直接通过Python/CLI调用，不依赖LLM。
5. 每次工具运行保存输入摘要、结果引用和错误；对越界请求写拒绝回归用例。

验收：同一参数、同一数据版本得到相同统计；测试证明跨run/数据集不能取到不允许的证据；不用prompt代替权限检查。

### T07 中文检索与对照查询集

新增：`retrieval/index.py`、`search.py`、`evals/retrieval_queries.json`、`evals/run_retrieval.py`、`tests/test_retrieval.py`。

步骤：

1. 建立约60个查询的目标清单，先20开发、40独立测试；每题人工标注相关证据集合，不能仅靠生成模型自评。
2. 实现结构化过滤+中文分词FTS/关键词基线，验证中文站名、线路数字、别称和时间表达。
3. 选择一个本地可运行的中文embedding方案，先核对模型/库许可、安装和下载大小，再锁定版本。
4. 比较关键词、向量和混合检索；记录Recall@5/10、无证据请求、延迟、索引体积与失败。
5. 只有收益明确才加入rerank，索引key包含数据版本、分块规则和embedding版本，防止用旧索引给新数据作答。

验收：检索结果可追溯、过滤无越界；有同查询集对照，未显著改善的复杂检索不强行保留。

### T08 有界工具循环与报告校验

新增：`agent/state.py`、`graph.py`、`policy.py`、`reporting/schema.py`、`verify.py`、`render.py`；测试`test_agent_flow.py`、`test_report_evidence.py`、`test_budget_limits.py`。

步骤：

1. 用脚本化假模型固定工具选择轨迹，先验证范围解析→工具→观察→结束的循环与状态更新。
2. 明确步骤/时间/费用预算和停止原因，实现工具调用协议、参数验证与错误回传；未知工具不隐式执行默认操作。
3. 请求数值时由aggregate工具提供结果；报告schema保存数字引用与证据ID，保留不确定和冲突。
4. 校验数字与工具结果一致、引用ID存在且属于本run，支持关系经人工抽查；没有证据的事实降为未证实或删除。
5. 对反讽、重复证据、未知线路、旧事件、提示注入、无证据和预算耗尽写专项用例；“忽略系统指令”的原帖不能更改工具权限。
6. 小预算真实模型运行验证协议及效果，不能用fake轨迹分数代表真实决策成功率。

计划命令：`uv run metro-agent analyze --dataset <version> --question-file examples/synthetic/question.txt --mode offline`、`uv run pytest tests/test_agent_flow.py tests/test_report_evidence.py tests/test_budget_limits.py`。

P3退出门槛：3个演示任务能显示工具执行、可追溯证据、准确数字与明确限制；不存在无限循环、任意执行或伪造引用。

## 6 P4 可靠性与运行证据

### T09 持久执行、幂等与成本

新增：`observability/traces.py`、`usage.py`、运行存储迁移；修改`agent/graph.py`和模型适配器；测试`test_resume.py`、`test_idempotency.py`、`test_usage.py`。

步骤：

1. 为run/tool/model调用生成稳定ID，存任务状态、节点版本与checkpoint，确认恢复的运行不会读错数据版本。
2. 对超时、限流和短暂网络失败有限退避重试；schema错误不无限重试。实现整体截止时间优先级。
3. 内容标注缓存以内容哈希+模型+prompt+标签版本为key；重复任务使用幂等key，避免重复处理和重复产物。
4. 记录真实token、模型返回usage和价格快照；未知usage标记unknown。模拟费用不可显示成实际账单。
5. 故障注入覆盖进程中断、失败后重试、过期图片、坏输出、重复请求、DB写入失败；先列出30个具体故障案例再运行。
6. 报告修复前后的恢复率与代价，检查日志不泄密；Langfuse接入为可选，不影响本地验证。

验收：重启后能明确继续或结束中断任务；无重复数据库副作用；失败可定位到工具/模型阶段；预算不足会停止。网络请求结果不确定时不能保证模型提供商未计费，应在记录中承认这类不确定性。

## 7 P5 交互、实验与求职交付

### T10 API与可检查的界面

新增：`api/app.py`、`api/web/`、`tests/test_api.py`、Dockerfile、`.dockerignore`（Docker为可选打包）。

步骤：

1. 做一页界面草图，呈现数据范围、问题输入、执行状态、证据和报告；沿用交通导视风格，但先保证信息清楚。
2. 实现`POST /runs`、`GET /runs/{id}`、`GET /runs/{id}/events`、`GET /reports/{id}`，请求有schema和状态码。
3. 单进程后台任务即可起步，状态落库，SSE断线可重连并读取当前状态；进程重启对中断任务给恢复选项。
4. 验证空库、无模型密钥、部分失败、任务超限、无证据、重复点击和HTML转义。服务默认只绑定本机，不默认公网暴露。
5. 写Windows本地启动和Docker离线演示说明；测试公开包内不含原始数据、浏览器profile或真实密钥。

验收：用户能在5分钟演示中完成一个真实支持的任务，并检查工具执行和原文；离线模式清晰标记，不要求登录社交平台。

### T11 正式对照实验与误差分析

新增：`evals/tasks.json`、`run_tasks.py`、`score_tasks.py`、`docs/evaluation/final-report.md`、消融与错误案例表。

步骤：

1. 建立约60个业务任务，20开发、40盲测；包括数字统计、维度比较、证据定位、事件时间线、证据不足与冲突。
2. 为每题写参考数字、允许证据、必要限制与任务rubric。可用程序判定部分先程序判，主观部分人工盲评；模型裁判只辅助。
3. 对比固定workflow/单次LLM/Agent/Agent+检索/Agent+检索+校验，任务、数据、模型版本和预算一致。
4. 对随机性明显的策略每题至少重复3次，保存每次失败；报告均值、波动和样本数，不挑最好的一次。
5. 记录任务成功率、引用支持、数字一致、成本、延迟和恢复；消融重点是“检索”“校验”“缓存/按需OCR”各自的作用。
6. 对表现差的维度、反讽、事件混淆和无证据请求写错误分类；固定测试集上只做最终评估，持续调优使用开发集。

### T12 复现与求职作品集

新增：`docs/portfolio/project-story.md`、`interview-notes.md`、`resume-evidence.md`；更新README，录制2–3分钟演示，补架构图、许可说明和复现步骤。

步骤：

1. README按问题→演示→架构→复现→评测→限制组织，清楚标旧团队基础、新版贡献和AI辅助开发。
2. 做一张“简历句子→代码→实验run_id→数据版本”的证据表，没有完成的词条标为不允许使用。
3. 准备两个具体案例：一次失败恢复/成本优化、一次有证据的分析纠错；能解释取舍与负结果。
4. 面试准备覆盖工具调用、RAG、checkpoint、幂等、schema、数据库、HTTP/SSE、数据泄漏、采样偏差和错误归因。
5. 本地完成发布清单与拟上传文件；获得明确对外发布授权后再上传GitHub、部署或发布演示。提交简历给招聘者另需用户指令。

P5退出门槛：全新环境可复现，演示与正式评测一致，用户能讲清主要代码和指标来源。项目不能保证实习录用。

## 8 指标、分母与初始验收目标

以下均是**拟定的发布质量门槛，当前没有实测值**。先跑基线并保留口径；如目标确需调整，记录原因和版本，不在测试失败后悄悄改低。

| 指标 | 定义/分母 | 初始目标 |
| --- | --- | --- |
| 数据导入对账 | 成功+拒绝+重复+失败=输入记录，记录原因 | 100%可解释，不静默丢行 |
| 相关性/情绪分类 | 分别计算Macro-F1，另列逐类样本数、混淆矩阵 | 正式金标上各自争取≥0.80；必须对比基线 |
| 多标签服务维度 | 逐维度F1与Micro/Macro-F1，按同一金标计算 | 先报告基线；稀有类明确支持数，不只报总准确率 |
| 检索Recall@5/10 | 每题召回的相关证据数/该题标注相关证据总数，再按题平均 | Recall@10争取≥0.85，同时报告@5 |
| 任务成功率 | 盲测题必须同时满足范围、数字、证据、格式与必要限制才算成功 | 40题及重复运行中争取≥0.80，给出样本数与波动 |
| 引用支持率 | 引用存在且实际支持的可核查事实数/需要证据的事实数，人工抽检 | ≥0.95；伪造引用ID为0 |
| 数字一致性 | 与确定性工具输出匹配的报告数字/应校验数字；缺报按失败 | 测试集100%，有统计结论必须附分母 |
| 无证据处理 | 正确限制/拒答的无证据题/无证据题总数，同时检查过度拒答 | 所有明确无证据fixture通过；真实模型另测 |
| 故障恢复 | 成功恢复且无重复副作用的可恢复故障/预定义可恢复故障 | 30例故障集整体完整报告，恢复子集争取≥0.90 |
| 资源边界 | 超步数/时间/费用任务正确终止，记录停止原因 | 确定性边界fixture全部通过 |
| 成本与延迟 | 每任务真实usage/估算分开，冷/热缓存分开，给中位数与P95及样本数 | 先测量，不预填“降低X%”或虚构价格 |

LLM自报confidence只能当辅助字段，不是概率校准或准确率。类不平衡时多数类准确率很高也不代表服务问题识别有效。

## 9 P6 可选扩展的进入条件

| 扩展 | 进入条件 | 必须给出的验证 |
| --- | --- | --- |
| 按需图片理解 | 文本无法支撑部分关键任务；有可用授权图片与明确预算 | 同一内容文本/文本+图片对照，成功率、额外费用与失败率 |
| MCP适配 | 有实际外部客户端要复用已经稳定的工具 | 现有工具与MCP调用结果一致、权限边界相同 |
| 多Agent | 单Agent在可解释任务上存在明确瓶颈 | 相同任务预算下比较成功率、成本、延迟与失败归因 |
| 微调 | 有足够干净标注、提示与检索仍不能解决可定位问题 | 独立盲测、训练资源与数据来源完整记录 |
| 第二社媒平台/视频 | 核心分析链路和演示已完成，能取得授权样本 | 新适配器合同测试与真正未见数据上的效果 |

## 10 日志模板与下一步

每次更新`docs/logs/YYYY-MM-DD-主题.md`，至少写：本轮目标、改动路径、实际命令、验证结果、没有验证的部分、成本/原始数据影响、状态变更、下一项具体任务。同步`docs/STATUS.md`。

下一轮从T01开始。完成P1之前不优先改页面样式、扩社媒平台或批量调用LLM；当前五项接手要求的完成证据见[本轮日志](../logs/2026-10-16-takeover.md)。
