# 项目当前状态

更新时间：2026-10-16，Asia/Shanghai。

**P0接手规划完成；P1离线工程基线已实现并通过本地验证；P2数据字典与正式评测未开始。**

GitHub：[soso23412/metroinsight-agent](https://github.com/soso23412/metroinsight-agent)。用户已授权持续同步，提交前继续执行公开文件检查。代码提交03c07c1的[CI运行](https://github.com/soso23412/metroinsight-agent/actions/runs/38869187149)已成功，四组Windows/Linux与Python矩阵均通过。

## 已交付

- Python/uv/src工程、依赖锁定与CLI；旧`platform`归档到本地`legacy/platform`，消除标准库冲突。
- Pydantic schema、相关性/情绪/多维度/事件独立字段、原文证据偏移验证。
- 流式小红书JSONL和微博CSV导入、来源哈希与行号、坏行对账、版本化数据集。
- 数据集/平台/原ID隔离、事务、显式失败、标注版本缓存与失败项重跑。
- 12条合成数据的LangGraph固定工作流，SQL统计及离线HTML/JSON报告。
- 30项本地测试通过；lint与格式检查通过；wheel和sdist构建、内容检查通过。
- 根Git与GitHub公开仓库，四组CI成功；从GitHub清洁克隆、新环境安装、30项测试与离线演示成功。安装包可在仓库外工作目录运行；无私有数据或密钥上传。

当前入口：`uv sync --locked`，然后`uv run --frozen --offline metro-agent demo --offline --output artifacts/demo`。

## 核验过的私有历史资产

80条小红书内容、571条评论已导入新库并对账；其中14条图片评论、1条空评论有显式状态，旧库内容未改变。旧微博CSV和人工标注表仍只在本地保存，详见P0审查。

## 尚未实现或验证

1. 真实模型接入与独立效果评测；当前演示是合成规则，不是LLM。
2. Agent工具调用循环、RAG、向量检索、任务checkpoint和API界面。
3. 人工黄金集、旧C1-C9/0标签解释与新标签映射；旧75%或90%+不用于新版简历。
4. 采集、OCR、付费批处理和跨平台泛化；这些能力不能通过现有测试推定。

## 下一项具体任务

按[执行计划](plans/2026-10-16-metro-agent-implementation.md)开始T04：数据字典、标注规范、近重复/同事件分组、开发/测试切分与数据卡。过去80条小红书样本只作开发诊断，不计入盲测。无需等待付费API即可推进这些工作。

## 继续工作前读取

`AGENTS.md` → 本文件 → [P1日志](logs/2026-10-16-p1-foundation.md) → 当前阶段计划。原始P0日志保留为历史，不代表当前实现状态。
