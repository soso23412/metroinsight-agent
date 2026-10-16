# 2026-10-16 P1工程基线与GitHub同步

当前阶段：P1核心实现、本地验证、GitHub同步及独立复现完成。持续推送已获用户明确授权，完整Agent功能仍按后续阶段推进。

## 已交付

- 建立根Git仓库，使用GitHub隐私邮箱。新建公开仓库`soso23412/metroinsight-agent`；P0提交`16ccf2e`已推送。
- 旧`platform/`原样归档到本地`legacy/platform/`，新包采用`src/metro_agent/`，标准库`platform.system()`正常。
- Python 3.12项目环境、uv锁文件、Pydantic schema、复合主键SQLite、流式小红书/微博导入、标注接口及LangGraph固定工作流。
- 12条合成反馈的无密钥离线演示，输出HTML、JSON和独立SQLite；重复执行复用成功标注。
- 非法输出与证据不一致可见，失败项可以重跑；模型/prompt/schema变化后不误用缓存。
- 公开文件检查、MIT与NOTICE、Windows/Linux和Python 3.12/3.13的CI配置。

当前没有真实LLM适配、工具调用循环、RAG、持久Agent checkpoint或任务API。演示规则不对私有真实数据开放，不能用合成测试宣称模型准确率。

## 实际验证

项目使用uv 0.12.3、Python 3.12.13、LangGraph 1.2.15、Pydantic 2.14.1；精确依赖与哈希以锁文件为准，包源为pypi.org，未嵌入认证信息。

实际命令采用已安装uv的完整路径，公开README使用等价的`uv`命令：

```powershell
uv sync --locked
uv run --frozen --offline pytest
uv run --frozen --offline ruff check .
uv run --frozen --offline ruff format --check .
uv run --frozen --offline metro-agent demo --offline --output artifacts/demo
uv build --offline
```

本地30项测试通过。测试覆盖禁网离线演示、无密钥、跨工作目录启动、坏行计数、非法枚举、证据偏移、事务回滚、跨平台/数据集隔离、缓存版本、部分失败重跑、图片/空评论和HTML转义。Ruff lint和格式检查通过。它们是工程行为验证，不是人工金标或真实模型评测。

真实旧数据导入到新的忽略数据库，80条内容与571条评论全部对账。评论中556条有文本、14条仅图片、1条为空。首次严格文本约束暴露了空评论问题，现改为显式text_status与warning保留；没有为得到零错误而把空内容伪造成文本。

旧数据库内容哈希与接手快照一致，原始文件没有被覆写。未调用模型、抓取、读取密钥值或上传私有数据。

## 安装包检查

wheel和sdist成功构建；wheel包含随包合成数据，两个包中均没有legacy、MediaCrawler、缓存、虚拟环境或数据库文件。sdist显式白名单避免工作区的大体量历史材料混入。

初次发行包检查使用的是配置调整前的旧输出，发现一个不应包含的文件；更新sdist白名单并重新构建后为0。未分发此前的安装包。

## Windows环境问题与处理

uv读取用户缓存及创建构建临时PE资源时受到本机沙箱权限限制；改用项目`.cache/uv`和`.cache/build-tmp`，不改变安全设置。必要时本地命令前设置：

```powershell
$env:TMP = Join-Path (Get-Location) '.cache\build-tmp'
$env:TEMP = $env:TMP
New-Item -ItemType Directory -Path $env:TMP -Force | Out-Null
```

pytest的默认全局临时目录在此机器也可能不可用，测试配置将临时目录放在`.cache/test-runs/`并为每次运行生成唯一目录。最初一次测试有10项因临时目录未创建而报错，修复测试环境后全部通过，未放宽功能断言。

离线HTML经本机浏览器检查，能显示12条内容、10条有效反馈、1个未证实事件候选及0失败，原文与统计可读。首次沙箱HTTP预览不可达，改为仅绑定本机的临时预览服务；这不是公网部署。

## 计划调整与下一步

`.env.example`和真实模型配置暂缓到实际接入时，避免假配置。固定workflow是未来工具化的基础，不提前称为自主Agent。具体取舍见[实施决策](../decisions/2026-10-16-p1-foundation.md)。

下一步：T04数据字典、旧标签映射、人工复核指南与分组切分。可先完成候选数据卡和争议案例表；人工金标尚未建立。工具循环、证据检索与真实模型预算在后续阶段实施。

## 远程与独立复现结果

代码提交`03c07c155ec54931ada9def3997fa0319706d248`已推送。GitHub Actions[运行38869187149](https://github.com/soso23412/metroinsight-agent/actions/runs/38869187149)完成，Windows/Linux × Python 3.12/3.13四组均成功，包括依赖安装、30项测试、lint、格式、离线演示和打包。

从公开仓库重新克隆到独立目录，使用新的虚拟环境安装锁定依赖；30项测试与12条离线演示再次通过，不依赖旧platform、私有数据或原项目虚拟环境。

另外将wheel安装到已完成依赖安装的独立环境，在仓库之外的工作目录导入，确认模块来自site-packages、内置合成资源可读取，并成功生成报告。wheel离线自动解析依赖的一次尝试遇到缓存缺项，因此wheel验证明确使用锁定环境，不声称任意空缓存环境可断网安装。

结构化证据见[p1-engineering.json](../evaluation/p1-engineering.json)。此记录对应代码提交03c07c1；随后仅补充文档，不能混淆代码测试范围。
