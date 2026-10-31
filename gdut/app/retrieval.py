"""BM25 and vector retrieval, reciprocal rank fusion, and local reranking."""
import json
import math
import re

import jieba
from langchain_core.documents import Document
from rank_bm25 import BM25Plus

from app.config import ANSWER_K, RETRIEVAL_K, RERANK_K, RRF_K


def tokenize(text):
    return [token for token in jieba.cut_for_search(text.lower())
            if re.search(r"\w", token)]


def chunk_key(document):
    # Article IDs may be shared by multiple chunks; preserve their distinct text.
    return (document.page_content,
            json.dumps(document.metadata, sort_keys=True, ensure_ascii=False))


class HybridRetriever:
    def __init__(self, store, reranker):
        self.store, self.reranker = store, reranker
        records = store.get(include=["documents", "metadatas"])
        unique = {}
        for text, metadata in zip(records["documents"], records["metadatas"]):
            if text and text.strip():
                doc = Document(page_content=text, metadata=metadata or {})
                unique.setdefault(chunk_key(doc), doc)
        self.documents = list(unique.values())
        tokens = [tokenize(doc.page_content) for doc in self.documents]
        self.token_sets = [set(row) for row in tokens]
        # Plus keeps matched terms useful even in very small collections.
        self.bm25 = BM25Plus(tokens) if any(tokens) else None

    def retrieve(self, query):
        if not self.documents:
            return []
        vector_hits = self.store.similarity_search_with_relevance_scores(
            query, k=min(RETRIEVAL_K, len(self.documents)))
        terms = tokenize(query)
        lexical = []
        if self.bm25 is not None and terms:
            scores = self.bm25.get_scores(terms)
            matched = [i for i, tokens in enumerate(self.token_sets)
                       if tokens.intersection(terms)]
            lexical = [self.documents[i] for i in
                       sorted(matched, key=lambda i: scores[i], reverse=True)[:RETRIEVAL_K]]
        fused, documents, similarities = {}, {}, {}
        for doc, score in vector_hits:
            similarities[chunk_key(doc)] = float(score)
        for ranking in ([doc for doc, _ in vector_hits], lexical):
            seen = set()
            for rank, doc in enumerate(ranking, start=1):
                key = chunk_key(doc)
                if key in seen:
                    continue
                seen.add(key)
                documents[key] = doc
                fused[key] = fused.get(key, 0.0) + 1.0 / (RRF_K + rank)
        candidates = sorted(fused, key=fused.get, reverse=True)[:RERANK_K]
        if not candidates:
            return []
        scores = self.reranker.predict(
            [(query, documents[key].page_content) for key in candidates])
        if len(scores) != len(candidates) or not all(math.isfinite(float(s)) for s in scores):
            raise RuntimeError("Invalid reranker scores")
        ranked = sorted(zip(candidates, scores), key=lambda pair: float(pair[1]), reverse=True)
        return [(documents[key], similarities.get(key), float(score))
                for key, score in ranked[:ANSWER_K]]
