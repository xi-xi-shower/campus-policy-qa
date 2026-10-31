import unittest
from unittest.mock import Mock

from langchain_core.documents import Document

from app.retrieval import HybridRetriever, tokenize


def document(text, article="article"):
    return Document(page_content=text, metadata={"source": "policy.md", "file_type": "md",
                                                "section": "申请", "doc_id": article})


def retriever_for(docs, vector_hits, scores):
    store, reranker = Mock(), Mock()
    store.get.return_value = {"documents": [d.page_content for d in docs],
                              "metadatas": [d.metadata for d in docs]}
    store.similarity_search_with_relevance_scores.return_value = vector_hits
    reranker.predict.return_value = scores
    return HybridRetriever(store, reranker)


class RetrievalTests(unittest.TestCase):
    def test_chinese_and_case_normalization(self):
        self.assertIn("奖学金", tokenize("奖学金申请，ABC123！"))
        self.assertIn("abc123", tokenize("奖学金申请，ABC123！"))
        self.assertEqual(tokenize(" ，。！？ "), [])

    def test_lexical_rescues_vector_miss_and_reranker_controls_order(self):
        semantic = document("住宿管理规定")
        exact = document("ZX901 奖学金申请条件", "scholarship")
        retriever = retriever_for([semantic, exact], [(semantic, 0.8)], [0.1, 0.9])
        hits = retriever.retrieve("ZX901")
        self.assertEqual([h[0].page_content for h in hits], [exact.page_content, semantic.page_content])
        self.assertIsNone(hits[0][1])
        self.assertEqual(hits[0][2], 0.9)
        self.assertEqual(hits[1][1], 0.8)

    def test_fusion_deduplicates_chunks_not_article_ids(self):
        first, second = document("奖学金申请条件"), document("奖学金申请材料")
        retriever = retriever_for([first, first, second], [(first, 0.9), (second, 0.8)], [1., 2.])
        hits = retriever.retrieve("奖学金")
        pairs = retriever.reranker.predict.call_args.args[0]
        self.assertEqual(len(pairs), 2)
        self.assertEqual(len(hits), 2)
        self.assertEqual(hits[0][0].page_content, second.page_content)

    def test_shared_hit_is_promoted_by_rrf(self):
        vector_only, shared = document("住宿管理"), document("ZX901 奖学金")
        retriever = retriever_for([vector_only, shared], [(vector_only, .9), (shared, .8)], [1., 1.])
        hits = retriever.retrieve("ZX901")
        self.assertEqual(hits[0][0].page_content, shared.page_content)

    def test_unmatched_terms_do_not_add_arbitrary_bm25_hits(self):
        retriever = retriever_for([document("奖学金申请")], [], [])
        self.assertEqual(retriever.retrieve("ZX999"), [])
        retriever.reranker.predict.assert_not_called()

    def test_empty_collection(self):
        retriever = retriever_for([], [], [])
        self.assertEqual(retriever.retrieve("奖学金"), [])
        retriever.store.similarity_search_with_relevance_scores.assert_not_called()
        retriever.reranker.predict.assert_not_called()

    def test_candidate_and_answer_limits(self):
        docs = [document(f"条款 {i}") for i in range(30)]
        retriever = retriever_for(docs, [(d, .5) for d in docs[:20]], list(range(20)))
        hits = retriever.retrieve("unmatched")
        self.assertEqual(len(retriever.reranker.predict.call_args.args[0]), 20)
        self.assertEqual(len(hits), 4)
        self.assertEqual(hits[0][0].page_content, docs[19].page_content)
        retriever.store.similarity_search_with_relevance_scores.assert_called_once_with("unmatched", k=20)

    def test_invalid_reranker_output_fails_explicitly(self):
        doc = document("奖学金")
        for scores in [[], [float("nan")], [float("inf")]]:
            with self.subTest(scores=scores):
                retriever = retriever_for([doc], [(doc, .8)], scores)
                with self.assertRaisesRegex(RuntimeError, "reranker"):
                    retriever.retrieve("奖学金")

    def test_real_chroma_store_without_model_download(self):
        import chromadb
        from langchain_chroma import Chroma
        from langchain_core.embeddings import Embeddings

        class FixedEmbeddings(Embeddings):
            def embed_documents(self, texts):
                return [[1., 0.] for _ in texts]

            def embed_query(self, text):
                return [1., 0.]

        client = chromadb.EphemeralClient()
        name = "hybrid-retrieval-test"
        store = Chroma(client=client, collection_name=name, embedding_function=FixedEmbeddings(),
                       collection_metadata={"hnsw:space": "cosine"})
        try:
            store.add_documents([document("ZX901 奖学金申请")], ids=["chunk-1"])
            reranker = Mock()
            reranker.predict.return_value = [0.9]
            hits = HybridRetriever(store, reranker).retrieve("ZX901")
            self.assertEqual(len(hits), 1)
            self.assertAlmostEqual(hits[0][1], 1.0)
        finally:
            client.delete_collection(name)


if __name__ == "__main__":
    unittest.main()
