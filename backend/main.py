"""通用数据分析 Agent — FastAPI 后端入口"""
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from backend.api.routes import router
from backend.core.config import settings
from backend.utils.logger import logger


app = FastAPI(
    title="通用数据分析 Agent",
    description="上传 CSV，自然语言提问，AI 自动查数据、画图、给洞察",
    version="1.0.0",
)

# CORS 中间件（允许 Streamlit 前端跨域）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载路由
app.include_router(router, prefix="", tags=["agent"])


# 全局异常处理中间件
@app.middleware("http")
async def global_exception_handler(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    except Exception as e:
        logger.error(f"[Global] 未捕获异常: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "code": 500,
                "msg": "内部错误",
                "detail": str(e),
            },
        )


@app.on_event("startup")
async def startup():
    logger.info(f"[Main] FastAPI 启动在 {settings.BACKEND_HOST}:{settings.BACKEND_PORT}")


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "backend.main:app",
        host=settings.BACKEND_HOST,
        port=settings.BACKEND_PORT,
        reload=True,
    )
