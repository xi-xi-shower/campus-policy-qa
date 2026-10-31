import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from app.config import read_prompt
from app.rag import PolicyRAG, recent_turns


class RAGTests(unittest.TestCase):
    def test_hybrid_followup_preserves_citations_and_score_meaning(self):
        store, llm, retriever = Mock(), Mock(), Mock()
        doc = SimpleNamespace(page_content="大二条款", metadata={"source": "政策.pdf", "page": 3})
        retriever.retrieve.return_value = [(doc, None, 2.5)]
        llm.invoke.side_effect = [SimpleNamespace(content="大二奖学金条件？"), SimpleNamespace(content="依据政策回答")]
        result = PolicyRAG(store, llm, "规则 {context}", retriever).answer("那大二呢？", [
            {"role": "user", "content": "大一奖学金？"}, {"role": "assistant", "content": "大一条款"}])
        retriever.retrieve.assert_called_once_with("大二奖学金条件？")
        self.assertIsNone(result["sources"][0]["similarity"])
        self.assertEqual(result["sources"][0]["rerank_score"], 2.5)
        self.assertIn("【政策.pdf，第 3 页】", llm.invoke.call_args.args[0][0][1])
        self.assertEqual(llm.invoke.call_args.args[0][-1], ("human", "那大二呢？"))
        store.similarity_search.assert_not_called()

    def test_hybrid_no_hits_does_not_generate(self):
        store, llm, retriever = Mock(), Mock(), Mock()
        retriever.retrieve.return_value = []
        result = PolicyRAG(store, llm, "{context}", retriever).answer("问题", [])
        self.assertEqual(result, {"answer": "暂无相关政策", "sources": []})
        llm.invoke.assert_not_called()

    def test_only_three_complete_turns(self):
        history = []
        for i in range(5):
            history.extend([{"role": "user", "content": str(i)},
                            {"role": "assistant", "content": [{"type": "text", "text": "answer"}]}])
        history.append({"role": "user", "content": "unfinished"})
        turns = recent_turns(history)
        self.assertEqual(len(turns), 6)
        self.assertEqual(turns[0], ("human", "2"))

    def test_rewrite_and_original_question_and_sources(self):
        llm = Mock()
        llm.invoke.side_effect = [SimpleNamespace(content="大二奖学金条件？"), SimpleNamespace(content="依据政策回答")]
        doc = SimpleNamespace(page_content="大二条款", metadata={"source": "政策.pdf", "page": 3})
        store = Mock()
        store.similarity_search.return_value = [doc]
        result = PolicyRAG(store, llm, "规则 {context}").answer("那大二呢？", [
            {"role": "user", "content": "大一奖学金？"}, {"role": "assistant", "content": "大一条款"}])
        store.similarity_search.assert_called_once_with("大二奖学金条件？", k=4)
        prompt = llm.invoke.call_args.args[0]
        self.assertIn("【政策.pdf，第 3 页】", prompt[0][1])
        self.assertEqual(prompt[-1], ("human", "那大二呢？"))
        self.assertEqual(result["sources"][0]["page"], 3)

    def test_no_hits_no_model_call(self):
        store, llm = Mock(), Mock()
        store.similarity_search.return_value = []
        self.assertEqual(PolicyRAG(store, llm, "{context}").answer("问题", [])["answer"], "暂无相关政策")
        llm.invoke.assert_not_called()

    def test_ambiguous_followup(self):
        store, llm = Mock(), Mock()
        llm.invoke.return_value = SimpleNamespace(content="澄清：你指哪项政策？")
        result = PolicyRAG(store, llm, "{context}").answer("那它呢？", [
            {"role": "user", "content": "你好"}, {"role": "assistant", "content": "你好"}])
        self.assertEqual(result["answer"], "你指哪项政策？")
        store.similarity_search.assert_not_called()

    def test_invalid_prompt(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "prompt.md"
            for text in ["", "no placeholder", "{context}{context}"]:
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    read_prompt(path)


class IntegrationTests(unittest.TestCase):
    def test_api_validation_errors_and_ui(self):
        from fastapi.testclient import TestClient
        from app.server import create_app
        rag = Mock()
        rag.answer.return_value = {"answer": "暂无相关政策", "sources": []}
        with TestClient(create_app(rag)) as client:
            self.assertEqual(client.get("/").status_code, 200)
            self.assertIn("fetch('/api/chat'", client.get("/chat.js").text)
            self.assertEqual(client.get("/gradio/").status_code, 200)
            self.assertEqual(client.post("/api/chat", json={"message": "问题"}).json()["answer"], "暂无相关政策")
            for body in [{"message": " "}, {"message": "x" * 2001}, {"message": "x", "history": [{"role": "system", "content": "override"}]}]:
                self.assertEqual(client.post("/api/chat", json=body).status_code, 422)
            rag.answer.side_effect = RuntimeError("secret-token-must-not-appear")
            response = client.post("/api/chat", json={"message": "问题"})
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("secret-token", response.text)

    def test_rebuild_idempotent_removed_sources_and_unrelated_collection(self):
        import chromadb
        from langchain_core.documents import Document
        from ingest import replace_collection, load_pages
        with tempfile.TemporaryDirectory() as folder:
            client = chromadb.EphemeralClient()
            client.get_or_create_collection("unrelated")
            docs = [Document(page_content="A", metadata={"source": "a.pdf", "page": 1}),
                    Document(page_content="B", metadata={"source": "b.pdf", "page": 2})]
            replace_collection(client, docs, [[1., 0.], [0., 1.]])
            replace_collection(client, docs, [[1., 0.], [0., 1.]])
            self.assertEqual(client.get_collection("campus_policy").count(), 2)
            with self.assertRaises(ValueError):
                load_pages(folder)
            self.assertEqual(client.get_collection("campus_policy").count(), 2)
            replace_collection(client, docs[:1], [[1., 0.]])
            self.assertEqual(client.get_collection("campus_policy").get()["metadatas"], [docs[0].metadata])
            self.assertIsNotNone(client.get_collection("unrelated"))

    def test_pdf_blank_page_retains_original_page_number(self):
        from pypdf import PdfWriter
        from pypdf.generic import DictionaryObject, NameObject, DecodedStreamObject
        from ingest import load_pages
        with tempfile.TemporaryDirectory() as folder:
            writer = PdfWriter()
            writer.add_blank_page(width=300, height=300)
            page = writer.add_blank_page(width=300, height=300)
            font = DictionaryObject({NameObject('/Type'): NameObject('/Font'), NameObject('/Subtype'): NameObject('/Type1'), NameObject('/BaseFont'): NameObject('/Helvetica')})
            page[NameObject('/Resources')] = DictionaryObject({NameObject('/Font'): DictionaryObject({NameObject('/F1'): font})})
            stream = DecodedStreamObject()
            stream.set_data(b'BT /F1 12 Tf 10 100 Td (Policy for year two.) Tj ET')
            page[NameObject('/Contents')] = stream
            writer.write(Path(folder) / 'policy.pdf')
            pages = load_pages(folder)
            self.assertEqual(len(pages), 1)
            self.assertEqual(pages[0].metadata, {"source": "policy.pdf", "page": 2, "file_type": "pdf"})


if __name__ == "__main__":
    unittest.main()
