# 广工校园政策问答

基于本地 PDF、Markdown 资料的校园政策问答系统。使用 BM25 关键词与 BGE 中文向量混合检索，经 RRF 融合和 BGE reranker 重排序后，调用 DeepSeek 生成带来源的回答，提供网页和 Gradio 两种入口。

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

首次建库需要联网下载 `BAAI/bge-small-zh-v1.5` 模型；首次启动还需下载 `BAAI/bge-reranker-base` 重排序模型，之后复用本地缓存。两个模型均在 CPU 上运行，重排序会增加问答延迟。在线问答需要有效的 DeepSeek 密钥和网络连接。

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

项目使用 LangChain，分别提取 PDF 和 Markdown 内容，按文档结构分段后，再按 token 长度递归切块。

```text
建库：PDF / Markdown → 文本提取与切块 → BGE 向量化 → Chroma 入库
问答：用户问题 → 追问改写（有历史时）→ BM25 与向量双路召回 → RRF 融合去重 → reranker 重排序 → DeepSeek 回答
```

### 资料入库

1. `ingest.py` 统一读取本地 PDF 和 Markdown 资料。
2. PDF 按页提取，普通 Markdown 按标题章节提取，并按 token 长度切分文本。
3. 使用 `BAAI/bge-small-zh-v1.5` 中文向量模型在 CPU 上生成归一化向量。
4. 将向量和来源信息写入 Chroma 的 `campus_policy` 集合。

本地索引保存在 `gdut/vectorstore/`，模型默认缓存于项目根目录的 `.model-cache/`。

应用启动时加载已有索引，不自动建库。建库会全量更新本项目集合，因此重建期间需要停止问答服务。没有有效文本时，保留旧索引并提示未更新。

指定版本的学生手册还支持专用章节解析和文档 ID 映射，相关实现位于 `ingest_md/`。

### 检索与回答

1. 用户通过网页或 Gradio 输入问题。
2. 有历史对话时，结合最近 3 轮完整对话，将追问改写为独立检索问题；指代不清时可请求澄清。
3. 使用 jieba 搜索模式分词，通过 BM25Plus 关键词检索和 BGE 向量检索分别召回候选片段。
4. 使用 RRF 融合两路排名并去重，再通过 BGE reranker 重排序，选出回答所需的片段。
5. 按照根目录 `prompt.md` 中的规则，将问题和相关资料交给 DeepSeek 生成回答。
6. 页面展示答案及来源，包括文件名、PDF 页码或 Markdown 章节和原文片段。

默认检索参数如下：

| 环节 | 模型或方法 | 参数 |
|---|---|---|
| 关键词召回 | jieba 搜索模式 + BM25Plus | 最多 20 个片段 |
| 向量召回 | `BAAI/bge-small-zh-v1.5` | 最多 20 个片段 |
| 排名融合 | RRF | 常数为 60，保留最多 20 个候选 |
| 重排序 | `BAAI/bge-reranker-base` | 按重排序分数选取前 4 个片段 |

去重以片段文本及元数据为依据：两路检索命中的同一片段只保留一份，同一条款下内容不同的片段仍分别保留，不会仅因条款 ID 相同而合并。

网页和 Gradio 共用问答逻辑，对话仅保存在当前会话，不提供登录和历史持久化。检索命中不代表片段一定支持答案，关键条款应核对原文。

BM25 索引在启动时从 Chroma 已有文本构建于内存，无需重新计算向量；资料更新后仍需重新建库并重启服务。模型与检索数量集中定义于 `gdut/app/config.py`。重排序失败会报告问答不可用，不会静默跳过。

来源中的 `similarity` 保留向量相关性分数，仅关键词命中的片段为 `null`；`rerank_score` 为独立的重排序分数，不表示正确率。最终来源按重排序结果排列。

在项目根目录激活 `gdut` 环境后运行回归测试（不下载模型、不调用 DeepSeek）：

```powershell
cd gdut
python -m unittest discover -s tests -p "test_*.py"
```

无法激活时，可在 `gdut` 目录使用 `conda run -n gdut python -m unittest discover -s tests -p "test_*.py"`。

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
    │   ├── retrieval.py       # BM25、向量融合与本地重排序
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
