"""Claude AI risk narrative generator for screening results."""
from __future__ import annotations
import os
import httpx
import json
from typing import Optional


ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
MODEL = "claude-haiku-4-5-20251001"


def generate_risk_narrative(
    query_name: str,
    overall_result: str,
    hit_count: int,
    possible_count: int,
    sources_checked: list,
    top_matches: list,
    query_country: Optional[str] = None,
    query_type: Optional[str] = None,
) -> str:
    """Generate a plain-English risk narrative for a screening result using Claude."""
    if not ANTHROPIC_API_KEY:
        return ""

    match_lines = []
    for m in top_matches[:5]:
        match_lines.append(
            f"- {m.get('name')} | Source: {m.get('source')} | Score: {m.get('score')} | "
            f"Result: {m.get('result')} | Program: {m.get('program', 'N/A')} | Country: {m.get('country', 'N/A')}"
        )
    matches_text = "\n".join(match_lines) if match_lines else "No matches above threshold."

    prompt = f"""You are a compliance analyst assistant. A sanctions screening has just been completed. Write a concise, professional risk narrative (3-5 sentences) for the compliance officer reviewing this result.

Screening details:
- Query name: {query_name}
- Entity type: {query_type or "Not specified"}
- Country filter: {query_country or "None"}
- Sources checked: {", ".join(sources_checked)}
- Overall result: {overall_result.upper().replace("_", " ")}
- Confirmed hits: {hit_count}
- Possible matches: {possible_count}

Top matches found:
{matches_text}

Write a professional risk narrative that:
1. States the overall risk level clearly
2. Briefly explains what was found (or not found)
3. Notes which sanctions lists were checked
4. Recommends a clear next action (e.g. "no further action required", "escalate for enhanced due diligence", "block transaction pending review")

Do not use bullet points. Write in flowing paragraphs. Be direct and professional."""

    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": MODEL,
                "max_tokens": 300,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=30,
        )
        response.raise_for_status()
        data = response.json()
        return data["content"][0]["text"].strip()
    except Exception:
        return ""
