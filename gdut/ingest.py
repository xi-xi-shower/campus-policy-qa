"""运行前停止问答服务；成功提取、切块、嵌入后再更新项目集合。"""
import sys
from pathlib import Path

from app.config import ROOT, COLLECTION, embeddings, load_environment
from ingest_pdf.ingest import load_pages
from ingest_md.ingest import load_sections
from ingest_md.handbook import HANDBOOK


def load_documents(directory):
    directory = Path(directory)
    documents = []
    for loader, subdirectory in [(load_pages, "pdf"), (load_sections, "md")]:
        for location in [directory, directory / subdirectory]:
            loaded = loader(location, allow_empty=True)
            for document in loaded:
                document.metadata["path"] = (
                    location.relative_to(directory) / document.metadata["source"]
                ).as_posix()
            documents.extend(loaded)
    if not documents:
        raise ValueError("docs/ 没有有效的 PDF 或 Markdown 文本（空目录、空白文件或扫描件）；已有索引保留，未更新。")
    # The reviewed Markdown replaces the same handbook PDF, avoiding duplicate
    # retrievals with incompatible page-based IDs. Other PDFs remain unchanged.
    if any(d.metadata["source"] == HANDBOOK for d in documents):
        documents = [d for d in documents if d.metadata["source"] != Path(HANDBOOK).with_suffix(".pdf").name]
    # Only disambiguate duplicate basenames; usual citations remain filename-only.
    paths = {}
    for document in documents:
        paths.setdefault(document.metadata["source"], set()).add(document.metadata["path"])
    for document in documents:
        if len(paths[document.metadata["source"]]) > 1:
            document.metadata["source"] = document.metadata["path"]
    return documents


def split_pages(pages, tokenizer):
    from langchain_text_splitters import RecursiveCharacterTextSplitter
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=400, chunk_overlap=60,
        length_function=lambda text: len(tokenizer.encode(text, add_special_tokens=False)),
        separators=["\n\n", "\n", "。", "！", "？", "；", "，", " ", ""],
    )
    chunks = splitter.split_documents(pages)
    if not chunks:
        raise ValueError("未切分出有效文本；已有索引保留，未更新。")
    if any(len(tokenizer.encode(c.page_content, add_special_tokens=False)) > 400 for c in chunks):
        raise ValueError("切块超过 400 token；已有索引保留，未更新。")
    return chunks


def replace_collection(client, chunks, vectors):
    # Preserve a recoverable snapshot of this collection only.
    existing = {c.name for c in client.list_collections()}
    old = client.get_collection(COLLECTION) if COLLECTION in existing else None
    backup = old.get(include=["documents", "metadatas", "embeddings"]) if old else None
    metadata = old.metadata if old else None
    if old:
        client.delete_collection(COLLECTION)
    try:
        collection = client.create_collection(COLLECTION, metadata={"hnsw:space": "cosine"})
        batch = client.get_max_batch_size()
        for start in range(0, len(chunks), batch):
            subset = chunks[start:start + batch]
            collection.add(
                ids=[str(i) for i in range(start, start + len(subset))],
                documents=[c.page_content for c in subset],
                metadatas=[c.metadata for c in subset], embeddings=vectors[start:start + batch],
            )
    except Exception:
        client.delete_collection(COLLECTION)
        if backup is not None:
            restored = client.create_collection(COLLECTION, metadata=metadata)
            if backup["ids"]:
                restored.add(**{key: backup[key] for key in ("ids", "documents", "metadatas", "embeddings")})
        raise


def main():
    load_environment()
    documents = load_documents(ROOT / "docs")
    encoder = embeddings()
    chunks = split_pages(documents, encoder._client.tokenizer)
    vectors = encoder.embed_documents([c.page_content for c in chunks])
    import chromadb
    client = chromadb.PersistentClient(path=str(ROOT / "vectorstore"))
    replace_collection(client, chunks, vectors)
    pdf_pages = sum(d.metadata["file_type"] == "pdf" for d in documents)
    print(f"建库完成：{pdf_pages} 个 PDF 页面，{len(documents) - pdf_pages} 个 Markdown 章节，{len(chunks)} 个片段。")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
    except Exception:
        print("建库失败，请检查依赖、模型下载和目录权限；请勿启动问答服务，先重新成功建库。", file=sys.stderr)
        sys.exit(1)
