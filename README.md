# PageTalk : Legal RAG

PageTalk is an intelligent, agentic document validation and chat platform designed for modern professionals. By fusing cutting-edge RAG architecture with a sleek, conversational UI, PageTalk eliminates manual document auditing. Upload complex PDFs to instantly verify critical clauses, cross-reference data across multiple sources, and ask complex questions. Every single response is directly anchored to your source text, eliminating hallucinations and ensuring total compliance.

## Structure

```
legal_rag/
├── backend/     # FastAPI + LangGraph RAG pipeline
├── frontend/    # React UI
└── docker-compose.yml
```

## Prerequisites

- Python 3.12+
- Node.js 20+ (for local frontend dev)
- Google Gemini and Pinecone API keys

## Setup

1. Copy `.env.example` to `.env` and add your API keys.
2. Choose one of the run options below.

## Run with Docker

No local venv needed — Docker builds and runs everything in containers.

```bash
docker compose up --build
```

- Frontend: http://localhost:3000
- Backend API: http://localhost:8000

## Run locally (development)

**Backend**

```bash
cd backend
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**Frontend** (separate terminal)

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173 — the Vite dev server proxies `/api` to the backend.

## RAGAS evaluation

Offline evaluation for the retrieval + generation pipeline (`backend/evaluation/`).

| Metric | What it measures | Needs ground truth? |
|--------|------------------|---------------------|
| Faithfulness | Is the answer supported by retrieved chunks? (hallucination check) | No |
| Answer relevancy | Does the answer actually address the question? | No |
| Context precision | Are the retrieved chunks relevant and well-ranked? | Yes |
| Context recall | Did retrieval find enough info to answer correctly? | Yes |

```bash
cd backend
python -m evaluation.ragas_eval --pdf path/to/document.pdf --dataset evaluation/sample_dataset_small.json
```

Dataset format: JSON array of `{"question": "...", "ground_truth": "..."}`. `ground_truth` is optional; without it, only faithfulness and answer relevancy run.

## Logging

Backend logs go to stdout. Set optional env vars in `.env`:

- `LOG_LEVEL` — default `INFO`
- `LOG_FILE` — optional file path for persistent logs
