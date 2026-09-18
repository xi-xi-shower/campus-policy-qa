"""Optional real-model check: downloads BGE; no DeepSeek call or production index writes."""
import math
import tempfile

from langchain_core.documents import Document
from langchain_chroma import Chroma

from app.config import embeddings, load_environment
from ingest import split_pages, replace_collection
from ingest_md.ingest import split_sections


def main():
    load_environment()
    encoder = embeddings()
    tokenizer = encoder._client.tokenizer
    pages = [Document(page_content="大二学生可申请测试奖学金。" * 100,
                      metadata={"source": "测试.pdf", "page": 2, "file_type": "pdf"})]
    pages.extend(split_sections("# 宿舍报修\n## 渠道\n通过测试服务台提交设施报修。", "测试.md"))
    chunks = split_pages(pages, tokenizer)
    assert all(len(tokenizer.encode(c.page_content, add_special_tokens=False)) <= 400 for c in chunks)
    vectors = encoder.embed_documents([c.page_content for c in chunks])
    assert all(abs(math.sqrt(sum(v * v for v in vector)) - 1) < 0.001 for vector in vectors)
    import chromadb
    # Temporary persisted store verifies reload; never touches gdut/vectorstore.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as folder:
        client = chromadb.PersistentClient(path=folder)
        replace_collection(client, chunks, vectors)
        reloaded = chromadb.PersistentClient(path=folder)
        store = Chroma(client=reloaded, collection_name="campus_policy", embedding_function=encoder)
        found = store.similarity_search("大二奖学金", k=4)
        assert found and found[0].metadata["page"] == 2
        found_md = store.similarity_search("宿舍设施报修渠道", k=4)
        assert any(d.metadata.get("section") == "宿舍报修 > 渠道" for d in found_md)
        assert all("page" not in d.metadata for d in found_md if d.metadata.get("file_type") == "md")
    print(f"Real BGE smoke check passed: {len(chunks)} chunks, normalized vectors, PDF/Markdown persisted retrieval.")


if __name__ == "__main__":
    main()
