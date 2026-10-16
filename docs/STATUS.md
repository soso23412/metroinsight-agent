# 项目当前状态

更新时间：2026-10-16，Asia/Shanghai。

**v0.2.0：Agent 主链路工程已交付，离线验收通过；真实模型效果和人工盲测未验证。** 用户本轮明确要求零模型费用，未调用模型或读取历史密钥。

仓库：[soso23412/metroinsight-agent](https://github.com/soso23412/metroinsight-agent)。持续同步授权有效，仍在推送前检查公开文件。P1 的 CI 记录为历史；v0.2.0 的远程 CI 结果在本轮工作日志更新，不混用旧结果。

v0.2.0代码提交`0b8cfdc`的[四组CI](https://github.com/soso23412/metroinsight-agent/actions/runs/38883263236)均成功；76项本地与独立克隆测试全部通过，wheel在仓库外12/12合成任务通过。具体证据见[verification](evaluation/v02-verification.json)。

## 当前能力

- P1 流式导入、数据版本、严格 schema、评论关联、事务、标签缓存与离线报告。
- LangGraph model/tools 条件循环、六个受控工具、中文 FTS5/BM25 词法 RAG、事件候选时间线。
- finish_report 只能引用当前任务观察过的 SQL 结果和证据；数字不由模型自由填入。
- SQLite 私有 checkpoint、工具结果与游标提交、幂等 key、lease、数据/模型变化拒绝恢复。
- 步数/时间/token/费用预留，真实 usage 单独记录；模型不确定请求暂停并需明确复核。
- HTTPS Chat Completions 模型与结构化标注适配器，HTTP mock 验证；本轮未在线调用。
- FastAPI 本机 Web、后台任务、状态查询、SSE 重放、报告下载；在线入口默认关闭。
- 数据字典、待复核导出、近重复/显式事件分组、按组切分、人工标签回写、基线与指标脚本。
- 公开合成任务/检索合同、故障目录、复现指南、界面截图和面试/简历证据材料。

## 当前入口

```sh
uv sync --locked
uv run --frozen --offline metro-agent serve
uv run --frozen --offline metro-agent evaluate --output artifacts/evaluation
```

打开 http://127.0.0.1:8000 。CLI 与恢复说明见 [operations](operations.md)。

## 验收边界

12个公开合成任务与12个合成检索查询只验证工程合同；正式200–400条人工金标、40任务盲测、真实模型成功率/分类F1、引用支持率与消融尚未完成，不以合成通过率替代。C1–C9/0 映射仍未解决。向量检索、OCR、MCP、多Agent、Docker和公网服务未交付，不作为能力宣传。

历史原始资料留在本地忽略目录，未改写旧库。80条小红书/571条评论的既有导入对账仍有效，历史XHS不计入盲测。新的人工待复核包也属于私有资料。

## 下一项需要真实证据的工作

先由人复核规范与首批数据并冻结测试集；后续如获明确预算，再选择模型跑小样本在线验收及正式对照。工程可离线复现，不能在当前状态下填写真实业务效果指标。

已准备本地`artifacts/review/xhs-development-pilot-40.json`及followup-40待复核包，均为历史开发数据、human_gold=false、Git忽略；不能充当盲测集。

[本轮日志](logs/2026-10-16-agent-delivery.md) · [验收报告](evaluation/final-report.md) · [最初计划与差异](plans/2026-10-16-metro-agent-implementation.md)
