from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import config
from api.routes import router
from logging_config import setup_logging

logger = setup_logging()


@asynccontextmanager
async def lifespan(_: FastAPI):
    tracing = config.LANGSMITH_TRACING
    project = config.LANGSMITH_PROJECT or "(default)"
    logger.info("Legal RAG API starting (CORS: %s)", ", ".join(config.CORS_ORIGINS))
    if tracing:
        logger.info("LangSmith tracing enabled (project: %s)", project)
    else:
        logger.info("LangSmith tracing disabled")
    yield


app = FastAPI(title="Legal RAG API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
