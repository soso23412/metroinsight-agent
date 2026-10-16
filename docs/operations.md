# 运行、恢复与资源边界

首次安装需要网络：`uv sync --locked`。之后离线 CLI、合成演示、Web、合成评测无需网络。公开仓库没有历史原帖、登录态或模型密钥。Python 3.12/3.13 为 CI 验证目标；不要求 GPU。

## 本地 Web

`uv run --frozen --offline metro-agent serve`，打开 `http://127.0.0.1:8000`。默认合成数据、离线策略；界面有明确来源标记。端口冲突可用 `--port 8001`。`--db` 只能由本机启动者提供新版本规范库，API/模型不接受路径。

API 是单进程本机工作台，不是公开多租户服务。默认仅绑定 loopback，检查 Host/Origin、禁用跨站写入、只允许一个后台任务，不在页面收集密钥。不要用反向代理直接暴露；如需公网部署，须另做身份认证、每用户隔离、任务队列和限额。

| 接口 | 说明 |
| --- | --- |
| GET /health、/datasets | 状态、数据集/标注版本，不返回作者资料 |
| POST /runs | question、dataset_id、annotator_version、mode、limits；Idempotency-Key 防重复任务 |
| GET /runs/{id} | 当前状态、脱敏事件、校验后的报告，不返回模型消息和完整 checkpoint |
| GET /runs/{id}/events | SSE 已保存事件重放，Last-Event-ID 或 after 断点；只读、不重跑任务 |
| POST /runs/{id}/resume | 离线恢复；在线待复核任务只能由 CLI 明确处理 |
| GET /reports/{id} | 报告未生成返回 409，不伪装成功 |

UI 用状态轮询，SSE 是可复用的事件重放接口。进程退出后已保存的任务可查询/恢复，不依赖浏览器 session。CLI 的 `--output` 与 Web 的运行目录需保持一致才能访问同一任务库。

## CLI 与恢复

```sh
uv run metro-agent analyze --question "分析示例1号线的服务反馈" --output artifacts/agent
uv run metro-agent analyze --question "分析示例1号线的服务反馈" --output artifacts/recovery --pause-after 2
uv run metro-agent resume --run-id <上一步run_id> --db artifacts/recovery/datasets.sqlite3 --output artifacts/recovery
```

任务保存状态、模型/工具 schema 身份、提示词版本、实际数据/标注快照哈希、每个已完成工具结果、下一待执行调用和事件。快照变化拒绝恢复；相同幂等 key 与不同任务冲突。一个运行持有有期限的 SQLite lease，崩溃后需等原 lease 过期（最长原任务时间上限+10秒），不强抢仍运行的任务。

工具都是只读业务函数，没有外部副作用；每个工具结果与推进游标一起提交。模型请求发送前保存费用预留和 pending 标记。若请求结果不确定，状态 needs_review，不自动重发；只有用户明确接受可能重复计费时才用 `resume --acknowledge-uncertain`。已明确拒绝的请求可手动恢复，但总步骤与费用预留继续累计。采用保守暂停而非网络层自动重试，这是为避免不确定计费的有意取舍。

终态 completed / insufficient_evidence / stopped 不继续；失败或预算不足创建新任务而不是修改旧记录。CLI 返回 0=正常完成（含无证据），2=暂停/资源终止/部分失败，1=配置或操作错误。

## 真实模型（本轮未执行）

人工复核后的标签可零费用回写：`uv run metro-agent apply-review --db <新库> --review artifacts/review/reviewed.json`。它逐条验证来源/哈希/人工声明并在同一事务写入新 human 标注版本，返回可用于后续分析的 annotator_version；不会覆盖其他标注版本。导入到真实数据集后仍需明确开启真实模型才能用自然语言执行器分析，离线脚本策略只允许合成数据。

当前用户明确要求零模型费用。适配器使用 HTTPS Chat Completions function-calling；已用 HTTP mock 测协议，未认证任何供应商/模型的在线表现。未来调用前另行明确预算及允许发送的数据。

配置 `.env.example` 所列环境变量，文件不会自动读取：服务地址（如提供商文档中的 `/v1`）、支持工具的模型名、密钥、当期输入/输出价格（USD/百万 token）。价格必须大于0；不自动选模型、不猜价格。CLI 显式选择 `--mode live` 才读取密钥；Web 还需启动者 `--allow-live`。默认网络不使用环境代理、不重定向，连接地址只能来自本机运维配置。

先 ingest 授权文件，再 `annotate --db <新库> --dataset <id> --limit 5 --max-cost-usd <上限>`，生成版本化 model 银标；随后 `analyze --mode live --db <新库> --dataset <id> --annotator-version <返回版本> --question <问题> --max-cost-usd <上限>`。这些命令会消费额度，**本轮没有运行**。

默认每任务 12 次模型决策、180秒、100000 token保守预留、0.1 USD保守预留；每次输出最多2048 token。输入按UTF-8字节+协议余量保守估算，不当作精确 tokenizer 或账单保证。实际 provider usage 单独记录，缺失为 null。未知账单不填零；预留不退款，宁可提前终止。供应商价格、计费协议或隐藏 token 规则仍需在线验收核对。

标注适配器也先预留、缓存成功项，失败/崩溃写 `provider_attempt_requires_review`，后续不会自动重复该条。人工检查后可选一个有记录的新标注版本重跑；不通过清除状态假装原调用没发生。

## 私有文件与规模

`artifacts/`、`data/`、`.cache/`、`legacy/`、`.env` 均忽略。checkpoint 保存模型上下文和原文，只留本机，不上传 GitHub；可移植 trace 仅记录输入哈希、工具名、状态、结果引用与耗时。报告仍包含原文，分享前必须人工脱敏。

导入为流式；当前检索索引/筛选候选在内存构建，面向经过筛选的本地研究数据集，尚未验证百万条检索、并发吞吐或长期在线运行。向量检索、OCR、MCP、分布式队列和 Docker 不属于当前已验证能力。
