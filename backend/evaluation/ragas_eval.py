from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from datasets import Dataset
from google import genai
from ragas import evaluate
from ragas.embeddings import GoogleEmbeddings
from ragas.llms import llm_factory
from ragas.metrics import (
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)

import config
from evaluation.rag_pipeline import index_pdf, run_rag_query

logger = logging.getLogger("legal_rag.evaluation")


def _normalize_path(path: Path) -> Path:
    raw = str(path)
    if raw.startswith("file:///"):
        return Path(raw.removeprefix("file:///"))
    if raw.startswith("file://"):
        return Path(raw.removeprefix("file://"))
    return path


def _load_dataset(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, list) or not data:
        raise ValueError("Dataset must be a non-empty JSON array of question objects.")
    for index, row in enumerate(data):
        if not isinstance(row, dict) or "question" not in row:
            raise ValueError(f"Row {index} must be an object with a 'question' field.")
    return data


def _build_ragas_client():
    if not config.GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is required for RAGAS evaluation.")
    return genai.Client(api_key=config.GOOGLE_API_KEY)


def _build_ragas_llm(client):
    return llm_factory(config.GEMINI_MODEL, provider="google", client=client)


def _build_ragas_embeddings(client):
    return GoogleEmbeddings(client=client, model=config.EMBEDDING_MODEL)


def _select_metrics(has_ground_truth: bool) -> list:
    metrics = [faithfulness, answer_relevancy]
    if has_ground_truth:
        metrics.extend([context_precision, context_recall])
    return metrics


def run_evaluation(pdf_path: Path, dataset_path: Path) -> dict:
    rows = _load_dataset(dataset_path)
    pdf_bytes = pdf_path.read_bytes()
    if not pdf_bytes:
        raise ValueError(f"PDF is empty: {pdf_path}")

    logger.info("Indexing %s ...", pdf_path.name)
    retriever, namespace = index_pdf(pdf_bytes)
    logger.info("Indexed into Pinecone namespace %s", namespace)

    questions: list[str] = []
    answers: list[str] = []
    contexts: list[list[str]] = []
    ground_truths: list[str] = []
    has_ground_truth = False

    for index, row in enumerate(rows, start=1):
        question = row["question"].strip()
        logger.info("Running RAG query %d/%d: %s", index, len(rows), question[:80])
        answer, retrieved = run_rag_query(retriever, question)
        questions.append(question)
        answers.append(answer)
        contexts.append(retrieved)
        truth = row.get("ground_truth", "")
        if truth:
            has_ground_truth = True
        ground_truths.append(truth or "")

    payload = {
        "question": questions,
        "answer": answers,
        "contexts": contexts,
    }
    if has_ground_truth:
        payload["ground_truth"] = ground_truths

    eval_dataset = Dataset.from_dict(payload)
    client = _build_ragas_client()
    llm = _build_ragas_llm(client)
    embeddings = _build_ragas_embeddings(client)
    metrics = _select_metrics(has_ground_truth)

    logger.info(
        "Running RAGAS with metrics: %s",
        ", ".join(metric.name for metric in metrics),
    )
    result = evaluate(
        eval_dataset,
        metrics=metrics,
        llm=llm,
        embeddings=embeddings,
    )
    return result.to_pandas()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluate Legal RAG with RAGAS.")
    parser.add_argument("--pdf", required=True, type=Path, help="Path to the PDF to index.")
    parser.add_argument(
        "--dataset",
        required=True,
        type=Path,
        help="JSON file with evaluation questions (see module docstring).",
    )
    args = parser.parse_args(argv)
    args.pdf = _normalize_path(args.pdf)
    args.dataset = _normalize_path(args.dataset)

    logging.basicConfig(level=config.LOG_LEVEL, format="%(levelname)s %(name)s: %(message)s")

    if not args.pdf.is_file():
        logger.error("PDF not found: %s", args.pdf)
        return 1
    if not args.dataset.is_file():
        logger.error("Dataset not found: %s", args.dataset)
        return 1
    if not config.PINECONE_API_KEY:
        logger.error("PINECONE_API_KEY is required for indexing during evaluation.")
        return 1

    try:
        scores_df = run_evaluation(args.pdf, args.dataset)
    except Exception as exc:
        logger.exception("Evaluation failed: %s", exc)
        return 1

    print("\n=== RAGAS scores (per question) ===")
    print(scores_df.to_string(index=False))

    numeric_cols = scores_df.select_dtypes(include="number").columns
    if len(numeric_cols):
        print("\n=== Mean scores ===")
        for name in numeric_cols:
            print(f"  {name}: {scores_df[name].mean():.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
