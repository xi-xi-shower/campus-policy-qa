# 校园政策问答系统 · 精简复现提示词

> 将本文档与 `prompt.md` 一起提供给 AI，作为从零实现该项目的完整需求。
> 可行性结论：适合小规模演示原型；目前仅完成方案检查，尚未经过安装和运行验证，不代表生产级可靠性。

---

你是一名资深 Python 工程师。请实现一个**校园政策问答系统（RAG）精简版**，要求在满足下述准备条件后，单次交付即可运行。有项目骨架时在现有文件上继续实现。业务代码不设 200 行硬上限，以精简、可读和可测试为准，不堆砌抽象、不扩展未要求的功能。

## 一、技术选型（硬性约束，不得替换）

| 组件 | 选型 |
|---|---|
| Tracing | LangSmith，默认关闭，按环境变量启用 |
| 语言 | Python 3.10+ |
| 编排 | LangChain（langchain + langchain-community） |
| LLM | DeepSeek API，模型 `deepseek-v4-flash`，显式设置 `extra_body={"thinking": {"type": "disabled"}}`；key 从 `.env` 的 `DEEPSEEK_API_KEY` 读取，禁止硬编码 |
| Embedding | 本地 `sentence-transformers` 加载 `BAAI/bge-small-zh-v1.5`，默认 CPU、向量归一化；首次需下载模型，缓存后可本地计算向量；国内环境可在模型加载前设置 `HF_ENDPOINT=https://hf-mirror.com` |
| 向量库 | Chroma，持久化到 `./vectorstore` 目录 |
| 界面 | Gradio `gr.ChatInterface` 网页聊天，支持多轮对话 |

依赖须包含 `langchain`、`langchain-community`、`langchain-deepseek`、`langchain-huggingface`、`langchain-chroma`、`langchain-text-splitters`、`chromadb`、`sentence-transformers`、`pypdf`、`gradio`、`python-dotenv` 和 `langsmith`。交付代码时在干净环境验证并固定兼容版本，不混用旧教程中的导入路径；LangChain 的相关集成通过独立包提供。[官方安装说明](https://docs.langchain.com/oss/python/langchain/install)

`.env` 中的 `LANGSMITH_TRACING` 默认设为 `false`；仅在需要追踪时填写 `LANGSMITH_API_KEY` 并设为 `true`。未配置追踪时核心问答仍须运行。加载环境变量后再初始化组件，不得打印密钥、环境变量全集或含认证信息的请求。

模型名称已更新：官方公告将旧名称 `deepseek-chat` 的停用日期定为 2026-07-24；V4 默认启用思考模式，因此本项目必须显式关闭。[官方变更记录](https://api-docs.deepseek.com/updates/)；[思考模式参数](https://api-docs.deepseek.com/guides/thinking_mode/)

## 二、功能需求

1. **文档加载**：读取用户放入 `docs/` 的政策 PDF，使用基于 pypdf 的 `PyPDFLoader` 按页加载。仅支持可提取文字的 PDF，不做 OCR；扫描件和复杂表格不保证可用。[pypdf 能力说明](https://pypdf.readthedocs.io/en/stable/user/extract-text.html)
2. **切块入库**：跳过空白页，保留文件名和原始页码；使用 `RecursiveCharacterTextSplitter`，以 BGE 自带 tokenizer 计算长度，每块最多 400 token、目标重叠 60 token（按分隔符切分时可能更少），优先按段落、换行和中文标点切分，不跨页合并。该模型输入上限为 512 token，不能把字符数直接当作 token 数。[模型配置](https://huggingface.co/BAAI/bge-small-zh-v1.5/blob/main/config.json)
   使用指定 BGE 模型在 CPU 上生成归一化向量，以余弦距离检索，保存至 `./vectorstore` 的固定集合 `campus_policy`；建库和查询使用相同模型与向量配置。每次运行 `ingest.py` 全量重建该集合，避免重复入库和残留旧政策；先确认成功提取并切分出有效文本，再重建，仅处理本项目集合。没有有效文本时提示原因并退出，保留已有索引，明确告知其未更新。来源统一显示为“文件名，第 N 页”，从 1 开始，指 PDF 文件页序。
3. **检索问答**：每次使用最近 3 轮完整对话；无历史时直接检索当前问题，有历史时先调用同一模型将追问改写成独立检索问题，只补全历史中明确的信息，不代答、不编造指代。随后检索最多 4 个片段，不足 4 个时使用实际数量；将带来源的片段填入答案提示词，保留历史消息的 user/assistant 角色和当前原始问题，调用 DeepSeek 生成回答。历史回答仅供理解追问，不作为政策依据。
4. **答案规范**：启动时以 UTF-8 读取 `prompt.md`，将其中唯一的 `{context}` 占位符替换为带来源的检索片段，作为回答阶段的系统提示词。没有片段时直接回答“暂无相关政策”；有片段也必须判断是否足以支持结论，不能将 top-4 命中等同于存在答案。不设置未经样本验证的相似度阈值，不承诺任意输入下零幻觉。提示词缺失或为空时提示配置问题，不使用空提示词启动。
5. **界面**：使用 `gr.ChatInterface`，聊天回调接收当前消息及会话历史，支持同一会话内追问，如“那大二呢？”。历史仅保留在会话中，不启用历史持久化；默认监听 `127.0.0.1:7860`。启动时加载已有索引，不重新嵌入 PDF；索引不存在或为空时提示先运行 `ingest.py`。

## 三、项目结构

```text
项目根目录/
├── docs/                 # 用户手动放入的政策 PDF
├── ingest.py             # 文档加载、切块、重建索引
├── app/                # 多轮检索、生成回答、Gradio 界面
├── prompt.md             # 答案规则，启动时读取
├── requirements.txt      # 交付时验证并固定的依赖版本
├── .env.example          # 环境变量模板，密钥留空
├── .env                  # 用户本地填写，不提交
├── .gitignore            # 忽略 .env、向量库及缓存
├── README.md             # 准备、运行与验收步骤
└── vectorstore/          # 建索引后自动生成
```

## 四、运行步骤（写入 README）

准备条件：安装 Python 3.10+，在项目根目录使用独立虚拟环境；将 `.env.example` 复制为 `.env`，在本地填写有效的 `DEEPSEEK_API_KEY`；创建 `docs/` 并放入至少一份可提取文字的政策 PDF，确保 `prompt.md` 非空。DeepSeek API 需要网络和可用账户额度；首次建库需要网络下载模型，后续缓存模型可用于本地向量计算，但在线问答仍需访问 DeepSeek。

`.env.example` 仅包含以下空密钥和默认值，不得填入真实密钥：

```dotenv
DEEPSEEK_API_KEY=
LANGSMITH_API_KEY=
LANGSMITH_TRACING=false
```

国内环境如需镜像，在启动 Python 前设置，例如 PowerShell 使用 `$env:HF_ENDPOINT = "https://hf-mirror.com"`。完成准备后运行：

```bash
pip install -r requirements.txt
python ingest.py      # 建索引
python app.py         # 启动网页，默认 http://127.0.0.1:7860
```

新增、修改或删除 PDF 后，先停止网页进程，再重新运行 `python ingest.py` 和 `python app.py`。若全部文件被删除或无法提取文字，重建会退出并保留旧索引，不能宣称政策已经更新。README 应说明空目录、扫描件、缺失密钥和缺失索引的处理方式，错误提示不得暴露认证信息。

## 五、明确排除项（保持精简，做了算超纲）

- 不做用户系统、登录、历史持久化，不引入 Chroma 之外的业务数据库；
- 不做官网爬取，政策文档由用户手动放入 `docs/`；
- 不引入 LangGraph、Agent、多路由，纯 RAG 链路；
- 除流式输出外不做其他交互增强。

## 六、验收标准

- 空仓库起步，完成准备条件并放入可提取文字的政策 PDF 后，按三条运行命令能跑通；重启应用直接加载持久化索引。
- 使用已知条款的测试文档提问，答案与条款一致，关键结论附“文件名，第 N 页”，且页码可在 PDF 中核对。
- 在包含不同年级规定的测试文档上，先问大一条件，再问“那大二呢？”，能检索并引用大二规定；缺少可确定的指代时先澄清。
- 对测试文档完全未覆盖的问题回答“暂无相关政策”；对仅部分有依据的问题说明缺失项，不编造金额、日期或条件。
- 对包含冲突规定且均被检索到的测试片段，列出差异与各自来源；没有明确生效或废止依据时不擅自判断哪份有效。
- 空目录或仅有无可提取文字的扫描件时，建库提示原因并退出；已有索引时保留它并提示未更新。
- 对同一批文档重复建库，片段数量不增长；删除其中一份文档并在其余文档有效时重建，被删除文档不再出现在检索来源中。
- 不配置 LangSmith 密钥且关闭追踪时问答仍可运行；缺失 DeepSeek 密钥或索引时给出明确提示。
- 业务代码保持精简、可读和可测试，不以压缩行数牺牲维护性；真实密钥只由用户在本地 `.env` 配置，代码、模板、README、日志和版本控制中均不泄露。
