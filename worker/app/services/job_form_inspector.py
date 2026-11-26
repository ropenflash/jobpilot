from typing import Any

from pydantic import BaseModel, HttpUrl

from fastapi import HTTPException

from app.agents.html_job_agent import inspect_html_job_agent
from app.agents.visual_job_agent import inspect_visual_job_agent
from app.agents.application_workflow_agent import analyze_application_workflow
from app.services.greenhouse import fetch_greenhouse_job
from app.services.job_page_inspector import inspect_greenhouse_job_page


class InspectJobFormRequest(BaseModel):
    url: HttpUrl


def _public_visual_result(result: dict) -> dict:
    """Do not send raw image bytes through the API."""
    return {key: value for key, value in result.items() if key != "screenshots"}


async def inspect_job_form(url: str) -> dict[str, Any]:
    # URL parser performs an exact HTTPS Greenhouse host/path allow-list check.
    job = await fetch_greenhouse_job(url)
    html_result = await inspect_html_job_agent(job)

    try:
        visual_context = await inspect_greenhouse_job_page(url, navigate_to_apply=True)
    except Exception:
        visual_context = {
            "status": "unavailable", "screenshots": [], "page_title": None,
            "page_url": url, "page_headings": [], "rendered_text": "",
            "form_controls": [], "links": [], "buttons": [], "instructions": [],
            "application_form_opened": False, "apply_action": "unavailable",
            "note": "Playwright could not render this Greenhouse job page.",
        }

    visual_result = await inspect_visual_job_agent(job, visual_context)
    visual_result["page_title"] = visual_result.get("page_title") or visual_context.get("page_title")
    visual_result["screenshots_captured"] = len(visual_context.get("screenshots") or [])
    visual_result["note"] = visual_context.get("note")
    visual_result["application_form_opened"] = visual_context.get("application_form_opened", False)
    visual_result["apply_action"] = visual_context.get("apply_action", "not_attempted")
    visual_result["form_controls_detected"] = len(visual_context.get("form_controls") or [])
    visual_result["form_flow"] = visual_result.get("form_flow") or {}
    visual_result["form_flow"]["submission_performed"] = False

    # Workflow classification is a separate pass over evidence from DOM, rendered text,
    # controls/options, link destinations/context, buttons, and both extraction agents.
    workflow_evidence = {
        **visual_context,
        "instructions": list(dict.fromkeys(
            (visual_context.get("instructions") or [])
            + (html_result.get("instructions") or [])
            + (visual_result.get("instructions") or [])
        )),
        "form_controls": visual_context.get("form_controls") or [],
        "links": visual_context.get("links") or [],
        "buttons": visual_context.get("buttons") or [],
        "rendered_text": visual_context.get("rendered_text") or "",
        "html_agent": {
            "job_requirements": html_result.get("job_requirements") or [],
            "screening_questions": html_result.get("screening_questions") or [],
            "external_application": html_result.get("external_application"),
        },
    }
    workflow = await analyze_application_workflow(workflow_evidence, job)
    workflow["inspection_only"] = True
    workflow["navigation_performed"] = False
    workflow["submission_performed"] = False

    return {
        "job": {
            "title": job.get("title"), "company": job.get("company"),
            "location": job.get("location"), "job_url": job.get("job_url"),
            "board_token": job.get("board_token"), "job_id": job.get("job_id"),
        },
        "agents": {
            "html": html_result,
            "visual": _public_visual_result(visual_result),
        },
        "workflow": workflow,
        "page_evidence": {
            "page_title": visual_context.get("page_title"),
            "page_url": visual_context.get("page_url"),
            "instructions": workflow_evidence["instructions"],
            "links": workflow_evidence["links"],
            "buttons": workflow_evidence["buttons"],
            "controls": workflow_evidence["form_controls"],
        },
        "comparison": _compare_fields(
            html_result.get("fields") or [], visual_result.get("fields") or [],
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
