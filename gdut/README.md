# 广工校园政策问答 MVP

保留 `design/campus-policy-v1.html` 的暗色界面，接入本地 PDF、Markdown 统一检索和 DeepSeek 问答。
首页为现有前端，`/gradio` 提供需求指定的 `gr.ChatInterface`，两者共用问答逻辑。
对话只保存在当前会话；不提供登录、爬虫、OCR 或历史持久化。

## Docker 本机部署

先启动 Docker Desktop 并使用 Linux containers，以下命令都在项目根目录（`D:\gdut_agent`）运行。

确认 `gdut/.env` 已填写有效的 `DEEPSEEK_API_KEY`，政策资料位于 `gdut/docs/pdf` 或 `gdut/docs/md`，并关闭占用本机 7860 端口的旧服务。

按顺序执行，每一步成功后再继续：

```powershell
docker compose build
docker compose run --rm web python ingest.py
docker compose up -d
docker compose ps
docker compose logs --tail 100 web
```

访问 http://127.0.0.1:7860 和 http://127.0.0.1:7860/gradio，健康检查地址为 http://127.0.0.1:7860/api/health，预期返回 `{"status":"ready"}`。

镜像使用 Python 3.11 的 `gdut` Conda 环境，建库和启动命令均自动在该环境执行，首次建库需要联网下载 BGE 模型，问答需要访问 DeepSeek。

服务启动默认以 `HF_HUB_OFFLINE=1` 加载建库时缓存的模型，避免启动时再次访问 Hugging Face，此设置不会阻止 DeepSeek 问答联网。

如果 Hugging Face 无法连接、但本机已有完整 BGE 缓存，可先复制该模型缓存到 Docker 卷，再离线建库，成功后执行 `docker compose up -d`：

```powershell
docker compose run --rm -v './.model-cache/hub/models--BAAI--bge-small-zh-v1.5:/seed:ro' web python -c "import shutil; shutil.copytree('/seed', '/app/.model-cache/hub/models--BAAI--bge-small-zh-v1.5', dirs_exist_ok=True)"
docker compose run --rm -e HF_HUB_OFFLINE=1 web python ingest.py
```

容器只读挂载本机政策目录，索引和模型缓存分别保存在 `vectorstore`、`model-cache` 命名卷中，不读取或修改本机 `gdut/vectorstore`，密钥仅由 Compose 在运行时注入。

更新资料后先停止服务，再重新建库，只有建库成功才重新启动：

```powershell
docker compose stop web
docker compose run --rm web python ingest.py
docker compose up -d
```

日常停止使用 `docker compose down`，它会保留命名卷；`docker compose down -v` 会删除索引和模型缓存，需要重新建库和下载模型。

代码更新后重新执行 `docker compose build` 和 `docker compose up -d`，现有命名卷继续复用，缺少索引或密钥时请查看容器日志。

依赖与现有测试可在镜像中验证：

```powershell
docker compose run --rm web python -m pip check
docker compose run --rm web python -m unittest discover -s tests -v
```

默认只允许本机访问，`/api/health` 只表示本地组件已加载，真实问答仍需单独验证外部模型服务。

2026-09-21 本机 Docker 验证通过：镜像构建及 `pip check` 成功，Windows 和 Linux 容器中各 20 项测试通过，复用已有 BGE 缓存建成 1151 个片段，首页、脚本、Gradio 和健康接口均返回 200，真实问答正确引用宿舍管理第十四条，强制重建服务容器后仍可正常检索和回答。

## 准备与启动

Python 3.10+；本次验证使用 Windows / Python 3.11。以下在 `D:\gdut_agent\gdut` 运行：

```powershell
python -m venv ../.venv
../.venv/Scripts/Activate.ps1
pip install -r requirements.txt
# 已有 .env 时不要覆盖；仅首次创建：
Copy-Item .env.example .env
```

在本地 `.env` 填写 `DEEPSEEK_API_KEY`。LangSmith 默认关闭；需要追踪时才填写其密钥并将 `LANGSMITH_TRACING` 设为 `true`，追踪会向 LangSmith 发送问答运行数据。
将真实政策 PDF 放入 `docs/pdf/`，Markdown 放入 `docs/md/`。PDF 必须有可提取文本；扫描件需要自行先转换，复杂表格不保证准确。Markdown 使用 UTF-8 编码（支持 BOM）。
答案提示词使用上一级目录已有的 `prompt.md`，避免出现两份不同规则。

### 隐私与上传范围

`.env` 只用于本地配置，禁止提交；提交前请确认暂存区中没有它或任何其他密钥。`.env.example` 仅包含空的配置模板。`docs/` 中的 PDF、Markdown 和 `vectorstore/` 都是本地知识库或生成数据，默认不会随源码上传；公开仓库只应提交代码、测试、说明文档和 `.gitkeep` 占位文件。

问答请求会将当前问题、最近对话以及检索到的政策片段发送给 DeepSeek 生成回答。LangSmith 追踪默认关闭；只有主动配置密钥并开启 `LANGSMITH_TRACING=true` 时，运行数据才会发送到 LangSmith。请勿将个人信息或不应外传的内容放入问题和政策资料。

```powershell
# 首次需下载 BAAI/bge-small-zh-v1.5；国内网络需要时设置：
$env:HF_ENDPOINT = "https://hf-mirror.com"
python ingest.py
python app.py
```

打开 http://127.0.0.1:7860 ，Gradio 入口为 http://127.0.0.1:7860/gradio 。
本工作区已经创建独立环境时，也可直接用 `../.venv/Scripts/python.exe ingest.py` 和 `../.venv/Scripts/python.exe app.py`。

## 工作方式

推荐目录结构：

```text
gdut/
├── ingest.py               # 唯一建库入口，合并两类资料后全量更新
├── ingest_pdf/
│   ├── __init__.py
│   └── ingest.py           # PDF 按页提取模块
├── ingest_md/
│   ├── __init__.py
│   └── ingest.py           # Markdown 按章节提取模块
└── docs/
    ├── pdf/                # 可提取文字的 PDF
    └── md/                 # UTF-8 Markdown
```

兼容 `docs/` 根目录原有的 `.pdf`、`.md` 文件；推荐将文件移动到对应子目录，不要同时保留两份副本。只读取根目录及对应类型子目录的直接子文件，不递归扫描更深目录；扩展名不区分大小写。若根目录与子目录有同名文件，引用以相对路径区分（如 `md/政策.md`）。
两个提取模块不单独写入索引，请始终运行 `python ingest.py`，避免一种类型覆盖另一种类型。

- BGE 在 CPU 上生成归一化向量，Chroma 集合 `campus_policy` 使用余弦距离，保存到 `gdut/vectorstore/`。
- PDF 按页提取，引用保留原始 PDF 页序（从 1 开始）。Markdown 按 `#`、`##`、`###` 标题分节，保留原始正文、列表、表格和代码文本，章节路径为 `一级标题 > 二级标题 > 三级标题`。无标题正文及首个标题前的内容使用“正文”；代码围栏中的标题不分节，四级及更深标题作为正文保留。
- 两类文档共用 BGE tokenizer，块最多 400 token、目标重叠 60 token，不跨 PDF 页或 Markdown 章节合并。来源详情展示命中的原文片段；长章节切块后展示该章节的命中部分。
- 每次建库全量替换本项目集合，不影响其他集合。先完成提取、切块和向量计算；无有效文字时保留旧索引并明确提示未更新。写入异常时尝试恢复旧集合。重建期间必须停止服务；进程被强制终止或磁盘损坏时需要重新建库。
- 无历史时直接检索；有历史时取最近 3 轮完整对话改写检索问题，再检索最多 4 块。生成答案仍保留原始问题与消息角色。缺少明确指代时可请求澄清。
- 模型按需求固定为 `deepseek-v4-flash`，显式关闭思考模式。未覆盖、部分覆盖和冲突情况按 `prompt.md` 处理。未使用未经验证的相似度阈值，不能保证任意问题零幻觉。
- 来源详情展示本轮检索片段，检索命中本身不代表片段支持答案。页面按纯文本呈现模型内容，避免执行模型返回的 HTML。

新增、修改或删除 PDF 或 Markdown 后，先停止服务，再重新运行建库和启动命令。应用启动只加载索引，不重新嵌入文档。旧 PDF 索引无需迁移即可读取；新增 Markdown 后需全量重建。
一种格式没有有效内容时，仍可用另一种格式建库。两种格式都没有有效内容时保留旧知识库并提示未更新；损坏 PDF、读取失败或 Markdown 编码错误也会终止建库，不会静默丢弃该文件后覆盖旧索引。

## 接口

`POST /api/chat`：

```json
{"message":"那大二呢？","history":[{"role":"user","content":"大一奖学金的条件？"},{"role":"assistant","content":"上一轮回答"}]}
```

返回示例：

```json
{"answer":"回答文本","sources":[
  {"filename":"政策.pdf","file_type":"pdf","page":2,"label":"政策.pdf，第 2 页","text":"检索原文"},
  {"filename":"政策.md","file_type":"md","section":"奖学金 > 申请条件","label":"政策.md，章节：奖学金 > 申请条件","text":"Markdown 原文片段"}
]}
```

PDF 保留原有 `page` 字段；Markdown 使用 `section`，不包含 `page`。`label` 是回答与页面共同使用的来源标签；前端按纯文本展示 Markdown 原文。
历史最多 6 条，仅允许 user/assistant；问题最多 2000 字符。
`GET /api/health` 返回 `{"status":"ready"}`，表示本地组件已加载，不代表外部 API 当前可用。
接口失败返回通用提示，不向浏览器发送异常堆栈或密钥。

## 验证与限制

```powershell
python -m unittest discover -s tests -v
pip check
```

自动检查覆盖最近 3 轮完整历史、追问改写、原始问题保留、来源页码、空检索、澄清、无效提示词、接口校验和脱敏、Gradio 页面、跳过空白页、重复建库、删除文档后的来源及无关集合保留。
测试模型使用可控替身，测试 PDF 为临时合成资料，不是学校政策；这些测试不能替代真实模型的答案质量验收。

2026-09-16 本地验证：独立 Python 3.11 环境安装完成，`pip check` 通过，8 项自动测试通过，前端 JavaScript 语法检查通过。真实 BGE 模型验证通过：4 个片段均不超过 400 token、向量已归一化、临时索引持久化后可重新检索并保留页码。空目录与缺少密钥时启动提示符合预期。未完成浏览器交互自动化和真实 DeepSeek 调用；当前缺少有效 API 密钥及政策 PDF。

2026-09-17 Markdown 扩展验证：15 项自动测试通过，覆盖 UTF-8、标题层级、代码围栏、无标题和空白内容、根目录兼容、混合建库、删除重建、旧索引保留以及混合来源的追问接口。`pip check` 与 JavaScript 语法检查通过；使用缓存的真实 BGE 模型离线验证了 6 个混合片段的 token 上限、归一化向量及持久化检索。测试只使用临时资料和索引，没有修改正式知识库，未调用真实 DeepSeek API。

真实验收时使用已知条款的 PDF，分别提问大一条件和“那大二呢？”，逐条核对引用；还需检查未覆盖问题、部分覆盖和互相冲突的条款。当前 `docs/` 为空，不能声称已完成真实学校政策端到端验收。

常见问题：

- 缺少密钥：在 `.env` 填写有效 DeepSeek 密钥；在线问答需要网络和账户额度。
- 缺少或空索引：先放入 PDF 或 Markdown，再运行 `ingest.py`。
- 空目录、只有空白文件或扫描件：无任何有效文本时建库退出并保留旧索引，提示未更新。
- 提示词缺失、空白或占位符错误：恢复根目录 `prompt.md`，确保仅含一个 `{context}`。
- 模型首次下载失败：检查网络或设置镜像；缓存后向量计算可离线，DeepSeek 问答仍需联网。
- 模型默认缓存到工作区 `.model-cache/`，可通过 `HF_HOME` 指定其他位置。可选真实向量验证：在 `gdut/` 下设置 `$env:PYTHONPATH = (Get-Location).Path` 后运行 `python tests/smoke_embeddings.py`，使用临时索引，不修改正式知识库。
- 端口被占用：关闭原服务再启动。
- 服务异常：检查网络、账户余额、模型可用性和索引，不要把密钥粘贴到日志或问题中。
