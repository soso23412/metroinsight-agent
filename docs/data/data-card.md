# 数据卡 v1

## 可公开复现的数据

`src/metro_agent/resources/demo.json` 包含 12 条人工构造的合成帖子，城市、线路和事件均为虚构，无真实账号或乘客。MIT 范围内可复现。`contracts.json` 是公开已知的合成工程题，不是盲测集。DemoAnnotator 标签是规则产物，不能作为真实业务金标。

## 本地历史数据

80 条小红书内容及 571 条关联评论已完成 P1 导入对账，556 条文本评论、14 条图片评论、1 条空评论。所有历史小红书数据都属于已用于开发的诊断数据，禁止进入新版盲测。旧微博与 Excel 仍为私有只读资产；旧预测、0、空标签和 C1–C9 含义必须复核，不能自动转为 human。

历史语料包含平台偏差、定向问题关键词和时间偏差，无法代表全体乘客。原帖可能有个人信息，移除作者字段不等于文本已经匿名化，因此原文、复核包、数据库、索引和任务 checkpoint 均留在本地忽略目录，不提交 GitHub。

## 字段与粒度

| 字段 | 约定 |
| --- | --- |
| dataset_id | 来源文件/导入器版本决定的版本标识，任务还记录实际内容与标注快照哈希 |
| platform + content_id | 原 ID 始终为字符串，跨平台不合并 |
| text / text_sha256 | 原文和哈希，引用以 Unicode 字符偏移核对 |
| source | 来源文件哈希、文件名、行号，不含完整本机路径 |
| published_at / collected_at | 明确时区，未知保留 null；叙述事件时间尚不抽取 |
| city / line | 原始字段或授权输入；未提供时不凭模型猜测补齐 |
| like_count / comment_count | 非负整数或 null；非法值有 warning |
| relevance | relevant / irrelevant / uncertain |
| sentiment | positive / neutral / negative / mixed / unknown |
| aspects | 十个服务维度，可多选，组内计数不应相加为分母 |
| event_candidate | 候选，默认未证实，不等同热点或事实 |
| label_source | synthetic_rule / model / human / legacy_prediction，互不等价 |
| annotator_version | 模型/策略、提示词、schema 版本共同决定 |
| comments | 独立记录，关联帖子，暂不计入 Agent 统计分母 |

## 复核与切分

`prepare-review` 输出待复核 JSON：NFKC/去标点归一化、字符二元组 Jaccard ≥0.85 及显式事件组做连通分组，组哈希 60/20/20 分 train/dev/test。含历史 XHS 的整个组进入 historical_dev。事件组需要人工提供；当前算法不宣称自动识别同事件，也不宣称已完成时间外推验证。导出上限 2000，超出显式拒绝，不静默截断。

复核包默认 pending。只有逐条人工确认、reviewer、原文哈希和合法 human 标签齐全才可进入 baseline 评测；软件只能检查声明完整性，不能证明填表者真的是人。必须在对提示词调优前冻结测试集及哈希。

正式目标仍为 200–400 条人工复核数据、40 任务与独立检索查询集；当前未达到，不将 12 条合成集成绩替代这些目标。
