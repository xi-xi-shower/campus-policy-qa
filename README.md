# 广工校园政策问答

基于本地 PDF、Markdown 资料的校园政策问答系统。使用 BGE 中文向量模型检索资料，调用 DeepSeek 生成带来源的回答，提供网页和 Gradio 两种入口。

## 快速启动

### 1. 准备环境

安装 Python 3.10 或以上版本，推荐 Python 3.11。下载项目后，在项目根目录打开终端。

创建虚拟环境：

```bash
python -m venv .venv
```

激活环境：

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
source .venv/bin/activate
```

部分系统需要使用 `python3` 创建虚拟环境。

### 2. 安装依赖

```bash
cd gdut
python -m pip install -r requirements.txt
```

### 3. 配置密钥与资料

将 `gdut/.env.example` 复制为同目录下的 `.env`，填写自己的 `DEEPSEEK_API_KEY`。已有 `.env` 时不要覆盖。

将政策资料放入对应目录：

- PDF：`gdut/docs/pdf/`
- Markdown：`gdut/docs/md/`

PDF 需要包含可提取的文字，项目不提供 OCR；Markdown 使用 UTF-8 编码。

### 4. 建库并启动

在已激活虚拟环境的终端中，确保当前位于 `gdut` 目录，依次执行：

```bash
python ingest.py
python app.py
```

首次建库需要联网下载 `BAAI/bge-small-zh-v1.5` 模型；在线问答需要有效的 DeepSeek 密钥和网络连接。

启动后访问：

- 首页：http://127.0.0.1:7860
- Gradio：http://127.0.0.1:7860/gradio
- 健康检查：http://127.0.0.1:7860/api/health

按 `Ctrl+C` 停止服务。健康检查返回 `{"status":"ready"}` 表示本地组件已加载，不代表外部模型服务可用。

### 日常启动与资料更新

后续启动时，激活虚拟环境，进入 `gdut` 目录后执行：

```bash
python app.py
```

已有索引且资料未变化时，无需重复建库。

新增、修改或删除资料后，先停止服务，再执行：

```bash
python ingest.py
python app.py
```

仅在建库成功后启动应用。

## 工作方式

对于markdown文本和pdf文档分别进行处理再整合

使用langchain框架

切分 - embedding - 入库 - 问答 - 索引

切分采用 先按文档结构分段，再按 token 长度递归切块

项目使用 BAAI/bge-small-zh-v1.5 做 embedding

索引返回逻辑按问题向量与文档块向量的余弦相似程度排名

### 资料入库

1. `ingest.py` 统一读取本地 PDF 和 Markdown 资料。
2. PDF 按页提取，普通 Markdown 按标题章节提取，并按 token 长度切分文本。
3. 使用 BGE 中文向量模型在 CPU 上生成归一化向量。
4. 将向量和来源信息写入 Chroma 的 `campus_policy` 集合。

本地索引保存在 `gdut/vectorstore/`，模型默认缓存于项目根目录的 `.model-cache/`。

应用启动时加载已有索引，不自动建库。建库会全量更新本项目集合，因此重建期间需要停止问答服务。没有有效文本时，保留旧索引并提示未更新。

指定版本的学生手册还支持专用章节解析和文档 ID 映射，相关实现位于 `ingest_md/`。

### 检索与回答

1. 用户通过网页或 Gradio 输入问题。
2. 有历史对话时，结合最近 3 轮完整对话，将追问改写为独立检索问题；指代不清时可请求澄清。
3. 从知识库检索最多 4 个相关片段。
4. 按照根目录 `prompt.md` 中的规则，将问题和相关资料交给 DeepSeek 生成回答。
5. 页面展示答案及来源，包括文件名、PDF 页码或 Markdown 章节和原文片段。

网页和 Gradio 共用问答逻辑，对话仅保存在当前会话，不提供登录和历史持久化。检索命中不代表片段一定支持答案，关键条款应核对原文。

问答会将问题、相关对话及检索片段发送给 DeepSeek。LangSmith 追踪默认关闭。

## 项目结构

以下展示应用的主要文件与目录；虚拟环境、配置、缓存和索引可能需要在首次使用时创建。

```text
项目根目录/
├── README.md                  # 项目总览与启动说明
├── prompt.md                  # 问答提示词
├── .venv/                     # 本地 Python 虚拟环境
├── .model-cache/              # 本地模型缓存
├── design/                    # 页面设计参考
└── gdut/
    ├── app.py                 # 应用启动入口
    ├── ingest.py              # 统一建库入口
    ├── requirements.txt       # 应用依赖
    ├── .env.example           # 环境变量模板
    ├── .env                   # 本地配置，不提交
    ├── README.md              # 应用详细说明
    ├── app/
    │   ├── config.py          # 环境、模型与提示词配置
    │   ├── rag.py             # 检索、追问改写与回答生成
    │   ├── server.py          # HTTP 接口与 Gradio 集成
    │   └── static/            # 网页及前端脚本
    ├── ingest_pdf/            # PDF 提取模块
    ├── ingest_md/             # Markdown 提取及手册映射
    ├── docs/
    │   ├── pdf/               # 本地 PDF 资料
    │   └── md/                # 本地 Markdown 资料
    ├── vectorstore/           # 本地 Chroma 索引
    └── tests/                 # 应用测试
```

`.env` 中的密钥、本地政策资料及生成的索引不应随源码提交。
