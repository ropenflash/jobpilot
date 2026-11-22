import base64
import os

import httpx
import google.auth
from google.auth.exceptions import DefaultCredentialsError
from google.auth.transport.requests import Request

CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
SUPPORTED_IMAGE_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_INLINE_IMAGE_BYTES = 12 * 1024 * 1024
MAX_INLINE_IMAGES = 5


class VertexError(RuntimeError):
    pass


def project_id() -> str:
    return os.getenv("GCP_PROJECT", "agentos-514612")


def location() -> str:
    return os.getenv("GCP_LOCATION", "global")


def model_name() -> str:
    return os.getenv("VERTEX_MODEL", "gemini-3.8-flash")


def credentials_available() -> bool:
    try:
        google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        return True
    except DefaultCredentialsError:
        return False


def _access_token() -> str:
    try:
        credentials, _ = google.auth.default(scopes=[CLOUD_PLATFORM_SCOPE])
        credentials.refresh(Request())
    except DefaultCredentialsError as exc:
        raise VertexError(
            "GCP credentials are not available. Run gcloud auth application-default login."
        ) from exc
    if not credentials.token:
        raise VertexError("GCP credentials did not return an access token.")
    return credentials.token


def _endpoint(model: str) -> str:
    region = location()
    host = (
        "aiplatform.googleapis.com"
        if region == "global"
        else f"{region}-aiplatform.googleapis.com"
    )
    return (
        f"https://{host}/v1/projects/{project_id()}/locations/{region}"
        f"/publishers/google/models/{model}:generateContent"
    )


def _encode_images(images: list[tuple[str, bytes]] | None) -> list[dict]:
    if not images:
        return []
    if len(images) > MAX_INLINE_IMAGES:
        raise ValueError(f"At most {MAX_INLINE_IMAGES} screenshots can be sent to Vertex AI.")

    total_bytes = 0
    parts = []
    for mime_type, content in images:
        if mime_type not in SUPPORTED_IMAGE_MIME_TYPES:
            raise ValueError(f"Unsupported image MIME type: {mime_type}")
        if not isinstance(content, bytes) or not content:
            raise ValueError("Image content must be non-empty bytes.")
        total_bytes += len(content)
        parts.append({
            "inlineData": {
                "mimeType": mime_type,
                "data": base64.b64encode(content).decode("ascii"),
            }
        })

    if total_bytes > MAX_INLINE_IMAGE_BYTES:
        raise ValueError("Combined inline image content exceeds the 12 MB limit.")
    return parts


def _payload(
    messages: list[dict],
    *,
    json_mode: bool,
    max_output_tokens: int | None = None,
    images: list[tuple[str, bytes]] | None = None,
) -> dict:
    system_parts: list[str] = []
    contents: list[dict] = []
    for message in messages:
        role = message.get("role", "user")
        text = message.get("content", "")
        if role == "system":
            if text:
                system_parts.append(text)
            continue
        contents.append({
            "role": "model" if role == "assistant" else "user",
            "parts": [{"text": text}],
        })
    if not contents:
        contents.append({"role": "user", "parts": [{"text": "Continue."}]})

    image_parts = _encode_images(images)
    if image_parts:
        target = next(
            (item for item in reversed(contents) if item["role"] == "user"),
            None,
        )
        if target is None:
            raise ValueError("Images can only be attached to a user message.")
        target["parts"].extend(image_parts)

    generation_config: dict = {
        "temperature": 0.2,
        "maxOutputTokens": max_output_tokens or int(os.getenv("VERTEX_MAX_TOKENS", "3000")),
        "thinkingConfig": {"thinkingBudget": 0},
    }
    if json_mode:
        generation_config["responseMimeType"] = "application/json"

    payload: dict = {"contents": contents, "generationConfig": generation_config}
    if system_parts:
        payload["systemInstruction"] = {"parts": [{"text": "\n\n".join(system_parts)}]}
    return payload


def _read_text(body: dict) -> str:
    candidates = body.get("candidates") or []
    if not candidates:
        raise VertexError("Vertex returned an empty response.")
    candidate = candidates[0]
    finish_reason = candidate.get("finishReason")
    if finish_reason == "MAX_TOKENS":
        raise VertexError(
            "Vertex output reached its token limit. Increase the configured output-token limit."
        )
    parts = ((candidate.get("content") or {}).get("parts")) or []
    texts = [
        part.get("text", "")
        for part in parts
        if isinstance(part, dict) and part.get("text") and not part.get("thought")
    ]
    text = "\n".join(texts).strip()
    if not text:
        raise VertexError(f"Vertex returned an empty response ({finish_reason or 'no text'}).")
    return text


async def generate_text(
    messages: list[dict],
    model: str | None = None,
    *,
    json_mode: bool = False,
    max_output_tokens: int | None = None,
    images: list[tuple[str, bytes]] | None = None,
) -> str:
    chosen_model = model or model_name()
    request_payload = _payload(
        messages,
        json_mode=json_mode,
        max_output_tokens=max_output_tokens,
        images=images,
    )
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                _endpoint(chosen_model),
                headers={
                    "Authorization": f"Bearer {_access_token()}",
                    "Content-Type": "application/json",
                },
                json=request_payload,
            )
            response.raise_for_status()
            return _read_text(response.json())
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise VertexError(
            f"Vertex returned HTTP {exc.response.status_code}: {detail}"
        ) from exc
    except httpx.RequestError as exc:
        raise VertexError(f"Could not reach Vertex AI: {exc}") from exc
