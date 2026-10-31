import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODEL = "BAAI/bge-small-zh-v1.5"
COLLECTION = "campus_policy"
RERANKER_MODEL = "BAAI/bge-reranker-base"
RETRIEVAL_K = 20
RERANK_K = 20
ANSWER_K = 4
RRF_K = 60


def load_environment():
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env")
    os.environ.setdefault("LANGSMITH_TRACING", "false")
    os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
    os.environ.setdefault("HF_HOME", str(ROOT.parent / ".model-cache"))


def read_prompt(path=None):
    path = path or ROOT.parent / "prompt.md"
    try:
        prompt = path.read_text(encoding="utf-8")
    except OSError:
        raise ValueError("缺少 prompt.md，请恢复答案提示词。") from None
    if not prompt.strip() or prompt.count("{context}") != 1:
        raise ValueError("prompt.md 必须非空且包含唯一的 {context} 占位符。")
    return prompt


def embeddings():
    from langchain_huggingface import HuggingFaceEmbeddings
    return HuggingFaceEmbeddings(
        model_name=MODEL, model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
