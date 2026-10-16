# 故障与边界验收目录

这是工程故障合同，不是模型质量评测。测试引用均位于 `tests/`，执行 `uv run --frozen --offline pytest`。30个具体场景按风险列出，不能把它们当成30个独立真实线上事故。

| # | 场景 | 验证入口 | 预期 |
| --- | --- | --- | --- |
| 01 | 工具要求执行 shell | test_agent::test_unknown_tool_cannot_execute_and_loop_is_bounded | 拒绝并有限终止 |
| 02 | 伪造证据 ID | test_agent::test_forged_report_cannot_be_published | 无报告 |
| 03 | 伪造数字结果 ID | 同上 | 无报告 |
| 04 | 超决策步数 | test_agent::test_unknown_tool_cannot_execute_and_loop_is_bounded | step_limit |
| 05 | token 额度不足 | test_agent::test_resource_preflight_prevents_model_request | 请求前停止 |
| 06 | 费用额度为零 | 同上 | 请求前停止 |
| 07 | 时间预算耗尽 | 同上 | 请求前停止 |
| 08 | 网络请求结果不确定 | test_agent::test_uncertain_request_not_automatically_repeated | 不自动重发 |
| 09 | 更换模型后恢复 | test_agent::test_changed_data_or_model_cannot_resume | 拒绝 |
| 10 | 更改数据/标注后恢复 | 同上 | 拒绝 |
| 11 | 两个执行者同时恢复 | test_agent::test_lease_rejects_concurrent_execution | lease 拒绝 |
| 12 | 相同幂等 key 不同任务 | test_agent::test_idempotency_conflict_and_final_replay | 冲突 |
| 13 | 数据集越权参数 | test_tools::test_tool_schema_rejects_escalation | schema 拒绝 |
| 14 | 任意 SQL 参数 | 同上 | schema 拒绝 |
| 15 | 任意文件路径 | 同上 | schema 拒绝 |
| 16 | 非法聚合字段 | 同上 | 枚举拒绝 |
| 17 | 非法公历日期 | 同上 | 拒绝 |
| 18 | SQL 注入过滤值 | test_tools::test_counts_filters_dates_and_overlapping_aspects | 当作字面值，无匹配 |
| 19 | FTS MATCH 注入符号 | test_tools::test_chinese_retrieval_filters_before_topk | 安全分词，无结果 |
| 20 | 读取未观察证据 | test_tools::test_cannot_read_unobserved_or_other_dataset_evidence | 拒绝 |
| 21 | HTTP 429 | test_chat::test_http_failures_redacted_no_hidden_retry | 固定错误、无隐式重试 |
| 22 | HTTP 401 | 同上 | 不输出响应正文 |
| 23 | HTTP 302 | 同上 | 不跟随重定向 |
| 24 | HTTP 503 | 同上 | 标记计费不确定 |
| 25 | 响应空 choices/缺字段 | test_chat::test_invalid_provider_output_fails_closed | 拒绝 |
| 26 | 非工具调用回答 | 同上 | 拒绝 |
| 27 | 非法 JSON/参数数组 | 同上 | 拒绝 |
| 28 | 网络超时/超大响应 | test_chat::test_timeout_and_oversize | 脱敏失败，不重试 |
| 29 | 跨站写入/Host 重绑定 | test_api::test_api_invalid_live_disabled_cross_origin_and_missing | HTTP 403 |
| 30 | 标注请求崩溃/超时后重跑 | test_live_annotation::test_uncertain_annotation_not_repeated_and_budget_prevents_call | 前置失败标记阻止重发 |

另有完整进程重建后的 checkpoint 恢复、SSE cursor 重放、重复提交、无证据、HTML 转义、旧库保护、导入事务回滚和训练/测试组泄漏检查。可恢复与不可恢复场景分开，不把安全拒绝错误计成“恢复率100%”。
