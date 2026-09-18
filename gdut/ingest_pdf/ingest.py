from pathlib import Path


def load_pages(directory, *, allow_empty=False):
    """读取指定目录的直接子文件；由统一入口决定空结果是否终止建库。"""
    from langchain_community.document_loaders import PyPDFLoader
    pages = []
    for path in sorted(Path(directory).glob("*")):
        if not path.is_file() or path.suffix.lower() != ".pdf":
            continue
        try:
            loaded = PyPDFLoader(str(path)).load()
        except Exception:
            raise ValueError(f"无法读取 {path.name}；请检查文件是否损坏或加密。索引未更新。") from None
        for page in loaded:
            if page.page_content.strip():
                page.metadata = {"source": path.name, "page": page.metadata["page"] + 1,
                                 "file_type": "pdf"}
                pages.append(page)
    if not pages and not allow_empty:
        raise ValueError("没有可提取文字的 PDF（空目录、空白页或扫描件）；已有索引保留，未更新。")
    return pages
