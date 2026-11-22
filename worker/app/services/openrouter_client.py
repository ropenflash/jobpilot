
import os
import httpx

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    pass


async def chat_completion(messages: list[dict], model: str | None = None) -> dict:
    api_key = os.getenv("OPENROUTER_API_KEY")

    if not api_key:
        raise OpenRouterError(
            "OPENROUTER_API_KEY is not configured."
        )

    payload = {
        "model": model or os.getenv(
            "OPENROUTER_MODEL", "openai/gpt-4o"
        ),
        "messages": messages,
        "max_tokens": int(
            os.getenv("OPENROUTER_MAX_TOKENS", "3000")
        ),
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "HTTP-Referer": os.getenv(
            "OPENROUTER_SITE_URL", "http://localhost:3000"
        ),
        "X-Title": os.getenv(
            "OPENROUTER_SITE_NAME", "JobPilot"
        ),
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                OPENROUTER_URL,
                headers=headers,
                json=payload,
            )

            response.raise_for_status()
            return response.json()

    except httpx.HTTPStatusError as exc:
        detail = exc.response.text[:1000]
        raise OpenRouterError(
            f"OpenRouter returned HTTP "
            f"{exc.response.status_code}: {detail}"
        ) from exc

    except httpx.RequestError as exc:
        raise OpenRouterError(
            f"Could not reach OpenRouter: {exc}"
        ) from exc
