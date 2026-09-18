import re
from pathlib import Path

from langchain_core.documents import Document

HEADING = re.compile(r"^ {0,3}(#{1,3})[ \t]+(.+?)\s*$")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


def split_sections(text, filename):
    """保留原始 Markdown，按 H1–H3 分节；代码围栏内的 # 不视为标题。"""
    documents, headings, lines = [], [], []
    fence_char, fence_length = None, 0

    def flush():
        content = "".join(lines).strip()
        if content:
            documents.append(Document(page_content=content, metadata={
                "source": filename, "file_type": "md",
                "section": " > ".join(title for _, title in headings) or "正文",
            }))

    for line in text.splitlines(keepends=True):
        fence = FENCE.match(line)
        if fence_char:
            lines.append(line)
            if fence and fence[1][0] == fence_char and len(fence[1]) >= fence_length and not fence[2].strip():
                fence_char = None
            continue
        if fence:
            fence_char, fence_length = fence[1][0], len(fence[1])
            lines.append(line)
            continue
        heading = HEADING.match(line)
        if heading:
            flush()
            level = len(heading[1])
            title = re.sub(r"[ \t]+#+[ \t]*$", "", heading[2]).strip()
            headings = [(depth, name) for depth, name in headings if depth < level]
            headings.append((level, title))
            lines = []
        lines.append(line)
    flush()
    return documents


def load_sections(directory, *, allow_empty=False):
    documents = []
    for path in sorted(Path(directory).glob("*")):
        if not path.is_file() or path.suffix.lower() != ".md":
            continue
        try:
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeError):
            raise ValueError(f"无法读取 {path.name}；请检查文件权限并使用 UTF-8 编码。索引未更新。") from None
        documents.extend(split_sections(text, path.name))
    if not documents and not allow_empty:
        raise ValueError("没有有效的 Markdown 文本；已有索引保留，未更新。")
    return documents
