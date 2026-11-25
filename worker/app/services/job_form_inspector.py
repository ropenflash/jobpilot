from typing import Any

from pydantic import BaseModel, Field, HttpUrl

from fastapi import HTTPException

from app.agents.html_job_agent import inspect_html_job_agent
from app.agents.visual_job_agent import inspect_visual_job_agent
from app.services.greenhouse import fetch_greenhouse_job
from app.services.job_page_inspector import inspect_greenhouse_job_page


class InspectJobFormRequest(BaseModel):
    url: HttpUrl


def _public_visual_result(result: dict) -> dict:
    """Do not send raw image bytes through the API."""
    return {
        key: value
        for key, value in result.items()
        if key != "screenshots"
    }


async def inspect_job_form(url: str) -> dict[str, Any]:
    # The shared URL parser performs an exact HTTPS Greenhouse host/path allow-list check.
    job = await fetch_greenhouse_job(url)

    # The two agents have independent source evidence: parsed HTML/API data vs screenshots.
    html_result = await inspect_html_job_agent(job)

    try:
        visual_context = await inspect_greenhouse_job_page(url)
    except Exception:
        visual_context = {
            "status": "unavailable",
            "screenshots": [],
            "page_title": None,
            "page_headings": [],
            "rendered_text": "",
            "note": "Playwright could not render this Greenhouse job page.",
        }

    visual_result = await inspect_visual_job_agent(job, visual_context)
    visual_result["page_title"] = visual_result.get("page_title") or visual_context.get("page_title")
    visual_result["screenshots_captured"] = len(visual_context.get("screenshots") or [])
    visual_result["note"] = visual_context.get("note")

    return {
        "job": {
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "job_url": job.get("job_url"),
            "board_token": job.get("board_token"),
            "job_id": job.get("job_id"),
        },
        "agents": {
            "html": html_result,
            "visual": _public_visual_result(visual_result),
        },
        "comparison": _compare_fields(
            html_result.get("fields") or [],
            visual_result.get("fields") or [],
        ),
    }


def _normalize_field(value: Any) -> str:
    return " ".join(str(value or "").lower().replace("_", " ").split())


def _compare_fields(html_fields: list[dict], visual_fields: list[dict]) -> dict:
    html_map = {
        _normalize_field(item.get("field")): item
        for item in html_fields
        if isinstance(item, dict) and item.get("field")
    }
    visual_map = {
        _normalize_field(item.get("field")): item
        for item in visual_fields
        if isinstance(item, dict) and item.get("field")
    }
    shared = sorted(set(html_map) & set(visual_map))
    html_only = sorted(set(html_map) - set(visual_map))
    visual_only = sorted(set(visual_map) - set(html_map))
    return {
        "shared_fields": shared,
        "html_only_fields": html_only,
        "visual_only_fields": visual_only,
        "field_count": len(set(html_map) | set(visual_map)),
    }
