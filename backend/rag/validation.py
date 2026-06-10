import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from rag.llm import get_llm

VALID_CATEGORIES = {"legal", "investigation", "criminal"}

SYSTEM_PROMPT = """You classify uploaded documents for a legal RAG system.

Valid documents are related to:
- legal (contracts, court filings, statutes, legal opinions, leases, agreements)
- investigation (police reports, investigation summaries, forensic reports)
- criminal (charge sheets, criminal complaints, indictment documents)

Invalid documents are unrelated, such as:
- recipes, novels, invoices for groceries, resumes, marketing brochures, school homework

Reply with JSON only, no markdown:
{"is_valid": true or false, "category": "legal" or "investigation" or "criminal" or "other", "reason": "one short sentence"}"""


def _content_to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _parse_validation_response(text: str) -> dict:
    text = text.strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if not match:
            raise ValueError("Validation model did not return valid JSON.")
        data = json.loads(match.group())

    is_valid = bool(data.get("is_valid"))
    category = str(data.get("category", "other")).lower().strip()
    reason = str(data.get("reason", "No reason provided.")).strip()

    if category not in VALID_CATEGORIES:
        is_valid = False

    return {
        "is_valid": is_valid,
        "category": category,
        "reason": reason,
    }


def validate_document(text_sample: str) -> dict:
    if not text_sample.strip():
        return {
            "is_valid": False,
            "category": "other",
            "reason": "No readable text found in the PDF.",
        }

    llm = get_llm()
    response = llm.invoke(
        [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=f"Document sample:\n\n{text_sample}"),
        ]
    )
    return _parse_validation_response(_content_to_str(response.content))
