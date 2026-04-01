"""
LangGraph node functions.

Each node is a focused unit of work: receive state, do one thing, return a dict
containing only the field(s) it updated. LangGraph merges these partial updates
into the next state automatically.

Execution order:
  intent_extraction  →  [conditional router]
                              ├── decline  →  END
                              └── api_call  →  answer_synthesis  →  END

Gemini calls use the google-genai SDK which exposes a native async interface
(client.aio.models.generate_content), so no asyncio.to_thread is needed.
"""

import logging

from google import genai
from google.genai import types

from .config import GEMINI_MODEL
from .models import AgentState, IntentResult
from .prompts import INTENT_EXTRACTION_PROMPT, ANSWER_SYNTHESIS_PROMPT
from .tools import fetch_country_data

logger = logging.getLogger(__name__)

# A single Client instance is safe to share across requests as it holds no
# per-request state and the underlying HTTP connections are pooled internally.
_client = genai.Client(vertexai=True)


async def intent_extraction_node(state: AgentState) -> dict:
    """
    Node 1: Extract the country name and requested fields from the user's question.

    Uses Gemini in JSON mode so we get a structured response we can parse
    directly into IntentResult; no regex, no brittle string matching.
    If the LLM response is malformed or the API is unavailable, we decline
    gracefully rather than crashing. A 500 to the user is not required.
    """
    prompt = INTENT_EXTRACTION_PROMPT.format(user_input=state["user_input"])

    try:
        response = await _client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema=IntentResult,
            ),
        )
        intent = IntentResult.model_validate_json(response.text)
    except Exception:
        # Catch-all: JSON parse errors, validation errors, API errors.
        # Surface a clean message rather than an internal traceback.
        # A more detailed handling can be done here to handle different error scenarios
        logger.exception("intent_extraction failed")
        intent = IntentResult(
            country="",
            fields=[],
            is_valid=False,
            decline_reason=(
                "I had trouble understanding your question. "
                "Could you rephrase it and try again?"
            ),
        )

    return {"intent": intent}


async def api_call_node(state: AgentState) -> dict:
    """
    Node 2: Fetch country data from the REST Countries API.

    By the time we reach this node the intent is guaranteed to be valid
    (the router sends invalid intents to the decline node instead).
    This node is purely I/O; no LLM call, no business logic.
    """
    country_data = await fetch_country_data(
        country=state["intent"].country,
        fields=state["intent"].fields,
    )
    return {"country_data": country_data}


async def answer_synthesis_node(state: AgentState) -> dict:
    """
    Node 3: Turn raw API data into a natural language answer.

    If the API lookup failed (country not found, timeout, etc.) we return
    the error message directly; no point calling Gemini with empty data.
    Otherwise we format the data as bullet points and let Gemini compose
    a conversational response grounded strictly in what the API returned.
    """
    if not state["country_data"].found:
        # Propagate the user-facing error from the API tool as the final answer.
        return {"final_answer": state["country_data"].error}

    # Format data as bullet points. None values become "Not available" so the
    # LLM knows to acknowledge the gap rather than invent information.
    data_bullets = "\n".join(
        f"- {field}: {value if value is not None else 'Not available'}"
        for field, value in state["country_data"].data.items()
    )

    prompt = ANSWER_SYNTHESIS_PROMPT.format(
        user_input=state["user_input"],
        country=state["country_data"].country,
        data_bullets=data_bullets,
    )

    try:
        response = await _client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )
        answer = response.text.strip()
    except Exception:
        # Synthesis failure is rare (data is correct) so fall back to the raw
        # bullet list rather than returning a generic error to the user.
        answer = (
            f"Here is what I found about {state['country_data'].country}:\n{data_bullets}"
        )

    return {"final_answer": answer}


async def decline_node(state: AgentState) -> dict:
    """
    Decline node: Surface the rejection reason as the final answer.

    No LLM call: The intent node already composed a user-facing message.
    We simply promote it to final_answer so the API response is consistent.
    """
    return {"final_answer": state["intent"].decline_reason}
