import json
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings


class ContentGenerationError(Exception):
    def __init__(self, message, status_code=502):
        self.status_code = status_code
        super().__init__(message)


def generate_content(
    *,
    brand,
    voice,
    platform,
    content_type,
    topic,
    keywords,
    call_to_action,
    tone="",
    language="",
):
    if not settings.AI_API_KEY or not settings.AI_MODEL:
        raise ContentGenerationError(
            "AI generation is not configured. Set AI_API_KEY and AI_MODEL in the backend environment.",
            status_code=503,
        )

    if settings.AI_PROVIDER.lower() != "openai":
        raise ContentGenerationError(
            "The configured AI_PROVIDER is unsupported. Use 'openai' with an OpenAI-compatible chat completions endpoint.",
            status_code=503,
        )

    voice_context = voice
    prompt = (
        "Create one original social media post. Return only the post text, "
        "without commentary or markdown fences.\n\n"
        f"Brand: {brand.name}\n"
        f"Brand description: {brand.description or 'Not provided'}\n"
        f"Industry: {brand.industry or 'Not provided'}\n"
        f"Platform: {platform}\n"
        f"Content type: {content_type}\n"
        f"Topic or campaign: {topic}\n"
        f"Keywords: {', '.join(keywords) if keywords else 'None specified'}\n"
        f"Call to action: {call_to_action or 'Choose an appropriate CTA or omit it'}\n"
        f"Tone: {tone or (voice_context.tone if voice_context else 'Friendly')}\n"
        f"Target audience: {voice_context.target_audience if voice_context else 'Not specified'}\n"
        f"Language: {language or (voice_context.language if voice_context else 'English')}\n"
        f"Writing guidelines: {voice_context.writing_guidelines if voice_context else 'None specified'}\n"
        f"Example content for style reference: {voice_context.example_content if voice_context else 'None provided'}"
    )
    body = json.dumps(
        {
            "model": settings.AI_MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are Ibda, a careful social media copywriter. "
                        "Follow the supplied brand voice and use the requested language."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.7,
        }
    ).encode("utf-8")
    request = Request(
        f"{settings.AI_BASE_URL}/chat/completions",
        data=body,
        headers={
            "Authorization": f"Bearer {settings.AI_API_KEY}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )

    try:
        with urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except HTTPError as error:
        if error.code == 429:
            raise ContentGenerationError(
                "The AI provider is rate limiting requests. Please wait and try again.",
                status_code=503,
            ) from error
        raise ContentGenerationError(
            f"The AI provider returned an error (HTTP {error.code}). Please try again.",
            status_code=502,
        ) from error
    except TimeoutError as error:
        raise ContentGenerationError(
            "The AI provider timed out. Please try again.",
            status_code=504,
        ) from error
    except URLError as error:
        raise ContentGenerationError(
            "Unable to connect to the AI provider. Please try again.",
            status_code=502,
        ) from error
    except OSError as error:
        raise ContentGenerationError(
            "Unable to complete the AI provider request. Please try again.",
            status_code=502,
        ) from error
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise ContentGenerationError(
            "The AI provider returned an invalid response.",
            status_code=502,
        ) from error

    try:
        content = result["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as error:
        raise ContentGenerationError(
            "The AI provider response did not contain generated content.",
            status_code=502,
        ) from error

    if not isinstance(content, str) or not content.strip():
        raise ContentGenerationError(
            "The AI provider returned empty content. Please try again.",
            status_code=502,
        )
    if len(content.strip()) > 10000:
        raise ContentGenerationError(
            "The AI provider returned content that is too long. Please try again.",
            status_code=502,
        )

    return content.strip()
