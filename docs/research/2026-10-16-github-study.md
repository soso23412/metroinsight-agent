# 高星 GitHub 项目核验与学习清单

核验日期：2026-10-16。Star来自GitHub REST仓库元数据快照，随时变化，只用于筛选学习对象，不作为代码质量证明。结构化记录见[source-snapshot.json](2026-10-16-source-snapshot.json)。

## 1 选择结果

| 仓库 | Star快照 | 维护/许可核验 | 本项目用途 |
| --- | ---: | --- | --- |
| [BettaFish](https://github.com/666ghj/BettaFish) | 42,417 | 未归档；API识别GPL-2.0 | 最贴近舆情业务，学习搜索、分析和报告衔接 |
| [LangGraph](https://github.com/langchain-ai/langgraph) | 43,341 | 未归档；MIT | 继续使用的编排底座，补齐工具与持久状态 |
| [Deep Agents](https://github.com/langchain-ai/deepagents) | 30,322 | 未归档；MIT | 学习上下文、工具边界和中间件分层，不直接替换现有底座 |
| [Langfuse](https://github.com/langfuse/langfuse) | 35,889 | 未归档；LICENSE区分MIT部分与ee目录 | 学习trace、用量、评测关联；接入作为可选项 |
| [Ragas](https://github.com/vibrantlabsai/ragas) | 16,039 | 未归档；Apache-2.0；旧owner链接发生重定向 | 检索与生成评测方法参考 |
| [Dify](https://github.com/langgenius/dify) | 158,611 | 未归档；带额外条件的Apache 2.0修改许可 | 了解应用产品形态、模型配置与工作流体验 |
| [MediaCrawler](https://github.com/NanmiCoder/MediaCrawler) | 66,956 | 未归档；本地LICENSE为非商业学习使用许可证1.1 | 已有外部采集适配器，不当作自研贡献 |
| [Open Deep Research](https://github.com/langchain-ai/open_deep_research) | 12,680 | **已归档**；MIT | 历史流程参考，不作为新项目主依赖 |

Langfuse、Dify、MediaCrawler的API许可字段为`NOASSERTION`，因此另读实际LICENSE，而非把它们笼统归为MIT。BettaFish若要复制代码，需要先检查复制范围的实际许可并保留相应声明；本轮只学习，没有复制第三方实现。

## 2 具体读哪里，以及读完要做什么

### BettaFish：学习完整任务链路

已读：[README架构说明](https://github.com/666ghj/BettaFish/blob/main/README.md)及[QueryEngine/agent.py](https://github.com/666ghj/BettaFish/blob/main/QueryEngine/agent.py)的初始化、工具分发、研究入口、搜索结果处理和有界反思循环。

源码把搜索结果保留为URL、内容、分数与发布时间，并写入段落研究状态；这比只把LLM回答落库更适合可核查报告。借鉴其证据对象、报告阶段划分和有限补查。不要照搬通用舆情的庞大引擎、论坛辩论、平台覆盖宣传或趋势预测承诺。

落地产物：`Evidence` schema、`retrieve_evidence`工具、最多有限轮的补查和报告引用校验；证明本项目自己的垂直分析约束与实验收益。

### LangGraph：补齐运行时能力

已读：[README](https://github.com/langchain-ai/langgraph/blob/main/README.md)与[tool_node.py](https://github.com/langchain-ai/langgraph/blob/main/libs/prebuilt/langgraph/prebuilt/tool_node.py)开头的工具执行设计、类型与错误模板。

学习工具节点、条件路由、state/context注入及错误处理；持久执行与checkpoint还需在实施时按当前版本文档验证。项目已有`StateGraph`，继续在此基础上建设，避免同时迁移多个框架。

落地产物：planner/tool/verify循环、明确状态、checkpoint与恢复测试；固定分类节点本身不称为自主规划。

### Deep Agents：理解框架如何组织复杂能力

已读：[README](https://github.com/langchain-ai/deepagents/blob/main/README.md)和[graph.py](https://github.com/langchain-ai/deepagents/blob/main/libs/deepagents/deepagents/graph.py)的组成与公开配置文档片段。

学习工具、上下文压缩、状态存储、权限与中间件的分层。首版保留受控工具和简明任务状态，不启用通用shell、任意文件写入或默认委派能力，也不把框架自带能力写成个人实现。

落地产物：工具白名单、结果裁剪、证据外置、跨任务隔离；到较长任务确有上下文压力后，再评估压缩策略。

### Langfuse：让效果与失败可诊断

已读：[README](https://github.com/langfuse/langfuse/blob/main/README.md)的集成与部署说明、[LICENSE](https://github.com/langfuse/langfuse/blob/main/LICENSE)。

学习把run、工具、模型调用和评价结果串联。首版以本地结构化trace为必选，Langfuse SDK或自托管接入为可选；不为展示作品集先部署复杂基础设施。

落地产物：每任务资源和延迟记录、错误阶段、prompt/model/data版本，以及一次故障定位示例。外发trace前做脱敏与传输范围检查。

### Ragas：学习评测定义

已读：[README](https://github.com/vibrantlabsai/ragas/blob/main/README.md)的指标、数据集与quickstart说明。旧地址`explodinggradients/ragas`被重定向，当前核验地址为`vibrantlabsai/ragas`。

学习检索与生成分别评测，并保留参考证据。先用确定性脚本和人工标注建立可信分母；LLM-as-judge仅辅助抽查，记录judge版本与人工一致性，不能把同一模型自评当唯一真值。

落地产物：固定查询集、Recall@k、引用支持率、数字一致性和错误分析；README中“即将推出”的模板不当成已经可用。

### Dify、MediaCrawler与归档项目

Dify用于交互与产品化对照，不作为首版另一个运行时；具体模块源码尚未深读，后续按界面需求再读。[Dify LICENSE](https://github.com/langgenius/dify/blob/main/LICENSE)

MediaCrawler已在本地存在。首版读取它导出的JSONL即可；采集故障不阻断分析演示。保留当前本地许可证和外部来源记录，后续需要公开复制代码时再核验对应版本。[MediaCrawler](https://github.com/NanmiCoder/MediaCrawler)

Open Deep Research保留在学习地图中，已归档的事实直接影响新依赖选择；本轮没有宣称读完其全部源码。[仓库](https://github.com/langchain-ai/open_deep_research)

## 3 学习顺序与产出

| 顺序 | 阅读任务 | 必须产出 |
| --- | --- | --- |
| 1 | 对照本地graph与LangGraph工具节点 | 手画state、工具输入输出、失败边界；做离线小例子 |
| 2 | BettaFish搜索与证据状态 | 设计本项目Evidence结构和引用关系 |
| 3 | Ragas评测定义 | 写出独立黄金集、指标分母及泄漏防护 |
| 4 | Deep Agents中间件组织 | 解释哪些能力首版需要、哪些暂缓 |
| 5 | Langfuse的trace与评价关联 | 用一条失败执行记录定位问题 |
| 6 | Dify产品形态对照 | 用一页交互稿确认“提问→进度→证据→报告” |

不建议一次克隆这8个仓库或从高Star项目拼贴功能。首版应形成“一个编排底座、一套业务工具、一套数据与评测、一条可运行交付链路”。

## 4 与参考项目的区别

本项目的价值将来自公共交通场景里的明确约束：多服务维度与混合情绪、线路/站点/事件时间分离、定向采样偏差、评论和原帖粒度、可追溯统计以及证据不足时的限制表达。这些差异需要通过数据和评测证明，不能仅凭选题垂直就声称技术创新。
