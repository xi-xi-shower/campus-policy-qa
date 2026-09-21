import os
import sys

from app.rag import build_rag


def main():
    try:
        rag = build_rag()
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception:
        print("启动失败，请检查依赖、模型缓存和索引；未输出敏感配置。", file=sys.stderr)
        return 1
    import uvicorn
    from app.server import create_app
    uvicorn.run(create_app(rag), host=os.getenv("HOST", "127.0.0.1"), port=7860)
    return 0


if __name__ == "__main__":
    sys.exit(main())
