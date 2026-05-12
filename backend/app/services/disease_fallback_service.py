import asyncio
import json
import logging
import re
from typing import Any

from google import genai
from google.genai import types

from app.core.config import settings

logger = logging.getLogger(__name__)

DISEASE_FALLBACK_PROMPT = """
You are FasalX Plant Health Assistant. The requested crop is not covered by the
local disease-classification ML models, or the user supplied a text-only issue.

Use the crop name, user's issue text, and optional crop image to provide a
careful advisory. Do not claim a definitive diagnosis. Give practical next
steps and mention when the farmer should consult a local agronomist.

Return only compact JSON with this exact shape:
{
  "issue_summary": "short summary",
  "possible_causes": ["cause 1", "cause 2"],
  "risk_level": "low|medium|high|unknown",
  "recommended_actions": ["action 1", "action 2"],
  "prevention_tips": ["tip 1", "tip 2"],
  "when_to_seek_expert_help": "short guidance",
  "confidence_note": "short uncertainty note"
}
""".strip()


def _failure(message: str) -> dict[str, Any]:
    return {
        "success": False,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": message,
        "source": "gemini",
    }


async def get_gemini_disease_advisory(
    crop_name: str,
    issue_text: str | None = None,
    image_bytes: bytes | None = None,
    content_type: str | None = None,
) -> dict[str, Any]:
    if not settings.GEMINI_API_KEY:
        return _failure("Gemini API key is not configured for unsupported crop advisory.")

    try:
        response = await asyncio.to_thread(
            _generate_disease_advisory,
            crop_name,
            issue_text,
            image_bytes,
            content_type,
        )
    except Exception as exc:
        logger.error("Gemini disease advisory request failed: %s", exc)
        return _failure("Failed to generate unsupported crop disease advisory.")

    advisory = _parse_advisory_json(_extract_text(response))
    if advisory is None:
        return _failure("Gemini returned an invalid disease advisory.")

    return {
        "success": True,
        "disease": None,
        "confidence": 0,
        "top3": [],
        "error": None,
        "source": "gemini",
        "model_supported": False,
        "crop_name": crop_name,
        "advisory": advisory,
    }


def _generate_disease_advisory(
    crop_name: str,
    issue_text: str | None,
    image_bytes: bytes | None,
    content_type: str | None,
):
    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    contents: list[Any] = [
        (
            f"{DISEASE_FALLBACK_PROMPT}\n\n"
            f"Crop name: {crop_name.strip()}\n"
            f"User issue text: {(issue_text or 'No text issue provided.').strip()}"
        )
    ]
    if image_bytes and content_type:
        contents.append(types.Part.from_bytes(data=image_bytes, mime_type=content_type))

    return client.models.generate_content(
        model=settings.GEMINI_DISEASE_FALLBACK_MODEL,
        contents=contents,
        config={
            "temperature": 0.2,
            "response_mime_type": "application/json",
        },
    )


def _extract_text(response) -> str:
    text = getattr(response, "text", None)
    if text:
        return text.strip()

    parts_text = []
    for candidate in getattr(response, "candidates", []) or []:
        content = getattr(candidate, "content", None)
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts_text.append(part_text)
    return "\n".join(parts_text).strip()


def _parse_advisory_json(text: str) -> dict[str, Any] | None:
    if not text:
        return None

    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?", "", cleaned, flags=re.IGNORECASE).strip()
        cleaned = re.sub(r"```$", "", cleaned).strip()

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(payload, dict):
        return None

    return {
        "issue_summary": str(payload.get("issue_summary") or "Plant health issue reported."),
        "possible_causes": _string_list(payload.get("possible_causes")),
        "risk_level": str(payload.get("risk_level") or "unknown").lower(),
        "recommended_actions": _string_list(payload.get("recommended_actions")),
        "prevention_tips": _string_list(payload.get("prevention_tips")),
        "when_to_seek_expert_help": str(payload.get("when_to_seek_expert_help") or ""),
        "confidence_note": str(payload.get("confidence_note") or ""),
    }


def _string_list(value) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []
