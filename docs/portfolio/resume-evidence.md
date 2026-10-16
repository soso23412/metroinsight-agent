# 简历条目与证据边界

可使用的工程表述（请按既有简历版式编辑，尚未替用户改写原Word）：

> **MetroInsight：面向公共交通反馈的证据型 Agent 应用**。在历史团队项目基础上，使用 Python、LangGraph、FastAPI、SQLite 构建数据规范化、工具调用、中文词法检索与证据报告链路；实现参数校验、版本隔离、任务恢复、幂等提交与资源限额，并提供无密钥离线演示、锁定依赖及跨平台 CI。开发使用 AI 辅助。

| 句子/指标 | 证据 | 边界 |
| --- | --- | --- |
| 工具调用 Agent | agent/graph.py、models/chat.py | 真实供应商协议用 mock 验证，在线效果未测 |
| 中文词法 RAG | retrieval/index.py、agent/tools.py | 不是向量检索；不能声称优于 embedding |
| 数字与引用校验 | reporting/agent_report.py、test_agent.py | 不等于事实已证实或语义支持率100% |
| 断点恢复/幂等 | agent/journal.py、恢复测试 | 外部模型请求不保证 exactly-once 计费 |
| 合成任务通过数 | evaluate 输出、合成 contracts 哈希 | 只能写“合成工程验收”，不能写“真实任务成功率” |
| 测试/CI | GitHub Actions 与工作日志 | 对应明确代码提交；不等同生产压测 |

禁止现阶段使用：90%+准确率、真实乘客满意率提升、生产级实时预警、百万级高并发检索、自研大模型、独立原创全套框架、真实成本降低X%、40题盲测成功率≥80%。这些需要各自的真实证据。
