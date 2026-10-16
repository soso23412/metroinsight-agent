# v0.2.0 Agent工程交付日志

## 目标与授权

用户要求持续完善为完整Agent项目，并沿用此前GitHub同步授权。用户明确选择“先完成全部工程与离线验收，暂不产生模型费用”。本轮实现模型接口但不做真实调用，不读取历史密钥，不扩大抓取。

## 实现

新增 agent/contracts、tools、journal、graph、service；retrieval/index；models/chat与offline；annotation/live；reporting/agent_report；evaluation/review、metrics、baselines、runner；api及本地Web。CLI增加analyze、resume、serve、evaluate、prepare-review、apply-review、annotate。版本升级0.2.0，锁定FastAPI/HTTPX/Uvicorn依赖。

原始数据与历史库保留；新版输出在忽略的artifacts下。复核包也是私有资料，不提交。公开内容只有第一方代码、合成资源、文档与合成界面截图。

## 已执行验证

- P1原有30项测试保留。新增工具循环、精确分母、中文检索、模型HTTP协议、证据伪造、预算、恢复、API/SSE、基线和复核回写测试。
- 第一轮核心测试66项通过；加入API与评测后72项测试中暴露时间边界失败，修复请求前的二次截止检查，改为用已耗尽的checkpoint时间做确定性测试，随后72项全部通过。
- 新增模型标注和人工回写后，43项相关测试通过。最终完整测试结果见下方收尾记录，不将阶段性计数冒充最终计数。
- `metro-agent evaluate --output artifacts/evaluation-v02`：12/12公开合成任务通过，12条合成检索查询，11条有证据查询Recall@5均值1.0，另1条无证据查询正确为空。子串基线在这批简单查询同样可召回，不能据此宣称FTS或Agent优于基线。
- 浏览器验证线路反馈（分母5，negative3/neutral2）和不存在的线路（insufficient_evidence，分母0）；页面有合成/离线标记，截图保存在docs/assets。
- HTTP模拟测试不产生模型费用；在线真实效果、人工语义支持和真实账单均未验证。

## 环境与修复

uv在沙箱内访问网络被阻止，使用授权的官方PyPI安装依赖，生成52包锁文件。Windows FastAPI TestClient需要本机socketpair，沙箱内卡在异步事件循环创建；在允许本机回环的执行环境重跑通过。一次自动权限审查超时，按提示重试成功，并非应用测试失败。

费用按发送前保守预留处理，provider usage未知保留null；不承诺token估算等于账单。模型请求不确定状态不自动重发。标签缓存未知请求也先保存review标记。真实效果验收和人工复核没有被合成测试替代。

## 文档与后续

README、STATUS、AGENTS、运行手册、数据卡、标注规范、旧标签未解决映射、故障目录、验收报告、演示脚本、简历证据与面试自查同步更新。最初计划保留差异和未完成门槛，避免把工程交付说成正式效果验证全部完成。

收尾将追加完整测试、安装包检查、GitHub提交和CI的实际结果。

打包检查首次阻止了一个第三方`MediaCrawler/.env.example`示例文件：原先未锚定的include匹配了嵌套同名文件。现将发行白名单全部锚定到根目录，并显式排除历史、第三方、缓存和私有产物；重建后wheel 50项、sdist 98项，公开文件类型和必需Web/合成资源均检查通过。未发布此前的安装包。另将忽略规则`data/`改为根目录`/data/`，使文档`docs/data/`正常入Git，而私有数据目录仍忽略。

最终本地验收：Python3.12.13下76项测试全部通过（12.63秒）；Ruff lint与80个文件格式检查通过，Git diff空白检查通过，Markdown本地链接无缺失。合成12/12任务与11个有证据查询Recall@5=1.0、1个空证据查询再次通过，真实模型调用0次。旧库SHA-256仍为`ee96ff059bc0edd5a702e6b83515b6d4003f5c7655a3b9acdd5fe1555b1cab44`。

## GitHub与独立复现收尾

代码提交`0b8cfdc597c4f962b645ca4f2b6128b50acf7160`已推送。[GitHub Actions 38883263236](https://github.com/soso23412/metroinsight-agent/actions/runs/38883263236)已完成且success，Windows/Linux × Python3.12/3.13四组均成功，包括76项测试、合成任务/检索合同、构建与公开包检查。

从GitHub重新克隆到独立目录，用新venv、锁文件与共享的包下载缓存完成安装；76项测试再次全部通过（24.82秒）。缓存只复用公开依赖payload，不复用原虚拟环境、原始社媒数据或旧代码。

将v0.2.0 wheel安装到该锁定环境，在仓库外工作目录导入，确认来自site-packages，HTML/JS与合成资源存在，12/12任务通过、模型调用0。首次wheel安装因Windows全局临时PE资源权限失败，改用项目内TMP/TEMP后成功；不声称任意空缓存环境能断网首次安装。

结构化收尾证据见[v02-verification.json](../evaluation/v02-verification.json)。随后提交仅补充文档和运行证据；远程结果对应上述明确代码提交。

使用既有只读规范库导出两份各40条的本地人工复核候选包：`artifacts/review/xhs-development-pilot-40.json`与`xhs-development-followup-40.json`，CLI明确human_gold=false，Git确认两份均被忽略。它们用于历史开发数据的规范试点，不进入新版盲测；未复制原文到公开文档。
