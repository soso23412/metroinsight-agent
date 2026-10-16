# ADR：完整 Agent 工程的交付边界

用户要求持续建设至完整项目，沿用已审阅的 Python 单体与 LangGraph 方案，自主完成工程、评测工具及交互交付。人工金标和在线效果不能由编程工作替代，作为独立验收项保留，不阻塞可独立完成的工程。

## 决策

- LangGraph 使用 model → tools → model 的条件循环；结束由结构化 `finish_report` 工具触发，数字只引用确定性工具结果，引用只来自当前任务检索过的证据。
- SQLite 保存任务 checkpoint、工具缓存和脱敏事件；恢复从已提交步骤继续。模型请求发出前持久化保守费用预留，网络超时/进程中断的不确定请求不自动重发，避免声称 exactly-once 计费。
- 检索采用 FTS5 + 中文二元字符切分和短词回退，零模型下载。与子串基线对照；向量模型仍是有收益再加入的实验，不把词法 RAG 称为向量检索。
- 所有工具绑定不可变数据集/标注版本，无任意 SQL、Python、shell、路径或网页访问。API 默认离线、仅供本机，实时服务需要运维者明确启用，前端无密钥输入框。
- 真实模型通过 HTTPS Chat Completions function-calling 协议适配，服务地址由运维者环境配置而非用户/模型参数；不读取历史密钥。模型输出严格校验，不依赖模型自报成功。
- UI 为交通运行观察台：米白/深青与橙色状态，问题、范围、执行记录和原文并列，所有合成样例显著标识。

## 取舍与非目标

相比自由文本回答，结构化报告限制叙事自由，换取数字与引用可验证；建议明确为未验证建议。相比全套向量数据库/多 Agent/分布式队列，单机实现更容易复现和面试解释。本轮不扩大抓取、不自动造人类真值、不进行未经授权的付费调用。

## 接口核对来源（2026-10-16）

- [LangGraph graph API](https://docs.langchain.com/oss/python/langgraph/graph-api)：StateGraph、条件边与循环。
- [DeepSeek tool calls](https://api-docs.deepseek.com/guides/tool_calls/) 与 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)：function 名称、JSON 参数、tool_call_id；不依赖 beta strict 或 thinking 模式。
- [SQLite FTS5](https://www.sqlite.org/fts5.html)：MATCH 与 BM25。
- [FastAPI](https://fastapi.tiangolo.com/tutorial/) 与 [HTTPX timeouts](https://www.python-httpx.org/advanced/timeouts/)：本机 API、测试与网络截止。

## 验证

工具精确统计与隔离、中文检索对照、状态恢复、坏模型输出、引用伪造、费用/步骤/时间终止、API 幂等与 SSE、无网络端到端、打包和 GitHub CI。合成合同集与真实模型/人工盲测结果分开记录。
