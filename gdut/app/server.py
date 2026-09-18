from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.config import ROOT


class Message(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=20000)


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    history: list[Message] = Field(default_factory=list, max_length=6)


def create_app(rag, with_gradio=True):
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.get("/")
    def index():
        return FileResponse(ROOT / "app" / "static" / "index.html")

    @app.get("/chat.js")
    def javascript():
        return FileResponse(ROOT / "app" / "static" / "chat.js", media_type="text/javascript")

    @app.get("/api/health")
    def health():
        return {"status": "ready"}

    @app.post("/api/chat")
    def chat(request: ChatRequest):
        if not request.message.strip():
            raise HTTPException(422, "请输入校园政策问题。")
        try:
            return rag.answer(request.message, [m.model_dump() for m in request.history])
        except Exception:
            raise HTTPException(503, "问答暂时不可用，请检查模型服务、网络和账户配置后重试。") from None

    if with_gradio:
        import gradio as gr

        def respond(message, history):
            try:
                return rag.answer(message, history)["answer"]
            except Exception:
                raise gr.Error("问答暂时不可用，请检查模型服务、网络和账户配置后重试。") from None

        ui = gr.ChatInterface(fn=respond, title="广工校园助手", save_history=False, analytics_enabled=False,
                              description="依据本地 PDF 和 Markdown 政策回答，关键结论附文件名与页码或章节。")
        app = gr.mount_gradio_app(app, ui, path="/gradio")
    return app
