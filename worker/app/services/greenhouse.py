import re
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urlparse

import httpx
from fastapi import HTTPException

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"
ALLOWED_HOSTS = {"boards.greenhouse.io", "job-boards.greenhouse.io"}
JOB_PATH = re.compile(r"^/([A-Za-z0-9_-]+)/jobs/([0-9]+)/?$")


class _HTMLTextExtractor(HTMLParser):
    """Convert job-description HTML to plain text without executing markup."""

    BLOCK_TAGS = {
        "address", "article", "br", "dd", "div", "dl", "dt", "h1", "h2",
        "h3", "h4", "h5", "h6", "li", "ol", "p", "section", "table",
        "td", "th", "tr", "ul",
    }

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip_depth = 0

    def handle_starttag(self, tag: str, attrs):
        if tag in {"script", "style", "noscript"}:
            self.skip_depth += 1
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str):
        if tag in {"script", "style", "noscript"} and self.skip_depth:
            self.skip_depth -= 1
        elif self.skip_depth == 0 and tag in self.BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str):
        if self.skip_depth == 0 and data.strip():
            self.parts.append(data.strip() + " ")

    def text(self) -> str:
        raw = "".join(self.parts)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line).strip()


def parse_greenhouse_job_url(url: str) -> tuple[str, int]:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()

    # Exact host allow-list and a strict path pattern prevent arbitrary URL fetches.
    try:
        has_custom_port = parsed.port is not None
    except ValueError:
        has_custom_port = True

    if (
        parsed.scheme.lower() != "https"
        or host not in ALLOWED_HOSTS
        or parsed.username
        or parsed.password
        or has_custom_port
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "Use a public HTTPS Greenhouse job URL from "
                "boards.greenhouse.io or job-boards.greenhouse.io."
            ),
        )

    match = JOB_PATH.fullmatch(parsed.path)
    if not match:
        raise HTTPException(
            status_code=422,
            detail="Expected a Greenhouse job URL like https://boards.greenhouse.io/company/jobs/123456.",
        )

    return match.group(1), int(match.group(2))


def html_to_text(value: str | None) -> str:
    decoded = unescape(unescape(value or ""))
    parser = _HTMLTextExtractor()
    parser.feed(decoded)
    parser.close()
    return parser.text()


async def fetch_greenhouse_job(url: str) -> dict:
    board_token, job_id = parse_greenhouse_job_url(url)
    endpoint = f"{GREENHOUSE_API}/{board_token}/jobs/{job_id}?content=true"

    try:
        async with httpx.AsyncClient(timeout=20.0, follow_redirects=False) as client:
            response = await client.get(
                endpoint,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "JobPilot/0.1 (public job-posting lookup)",
                },
            )
    except httpx.RequestError as exc:
        raise HTTPException(
            status_code=502,
            detail="Could not reach the Greenhouse Job Board API.",
        ) from exc

    if response.status_code == 404:
        raise HTTPException(
            status_code=404,
            detail="This Greenhouse job was not found or is no longer publicly available.",
        )
    if response.status_code == 429:
        raise HTTPException(
            status_code=503,
            detail="Greenhouse rate-limited this request. Please retry later.",
        )
    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Greenhouse Job Board API returned HTTP {response.status_code}.",
        )

    try:
        payload = response.json()
    except ValueError as exc:
        raise HTTPException(
            status_code=502,
            detail="Greenhouse returned an invalid JSON response.",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(status_code=502, detail="Greenhouse returned an unexpected job payload.")

    description = html_to_text(payload.get("content"))
    if not description:
        raise HTTPException(
            status_code=422,
            detail="Greenhouse returned no readable description for this job.",
        )

    location = payload.get("location") or {}
    location_name = location.get("name") if isinstance(location, dict) else None

    return {
        "job_id": int(payload.get("id") or job_id),
        "board_token": board_token,
        "title": payload.get("title") or "Untitled role",
        # Greenhouse public job payloads do not always include a company name.
        # The board token is retained as a transparent fallback.
        "company": payload.get("company_name") or board_token.replace("-", " ").replace("_", " ").title(),
        "location": location_name,
        "job_url": payload.get("absolute_url") or url,
        "description": description[:30000],
        "updated_at": payload.get("updated_at"),
    }
