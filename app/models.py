"""
Pydantic models that flow through the LangGraph agent.

Three distinct shapes of data move through the pipeline:

  IntentResult  : What Gemini extracted from the user's question
  CountryData   : What the REST Countries API returned
  AgentState    : The envelope that carries all of the above between nodes

Using separate models for each stage makes it straightforward to understand
what data is available at any point in the graph without reading node code.
"""

from enum import Enum
from typing import Optional, Required, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import SUPPORTED_FIELDS

# Dynamically built from SUPPORTED_FIELDS so there is one source of truth.
# Gemini receives this as an enum in the JSON schema and is constrained to
# only return values from this set and preventing hallucinated field names from
# silently passing through to the API tool.
SupportedField = Enum("SupportedField", {f: f for f in SUPPORTED_FIELDS}, type=str)


class IntentResult(BaseModel):
    """Structured output of the intent extraction node."""

    # use_enum_values ensures intent.fields stays list[str] downstream;
    # tools.py and the synthesis node never need to know about the enum.
    model_config = ConfigDict(use_enum_values=True)

    country: str = Field(
        description=(
            "The name of the country the user is asking about. "
            "Empty string when is_valid is false."
        )
    )
    fields: list[SupportedField] = Field(  # type: ignore[valid-type]
        default_factory=list,
        description=(
            "The subset of supported fields the user wants. "
            f"Must only contain values from: {', '.join(SUPPORTED_FIELDS)}. "
            "Empty list when is_valid is false."
        ),
    )
    is_valid: bool = Field(
        description=(
            "True if the question is a valid single-country query. "
            "False if the question is off-topic or asks about multiple countries."
        )
    )
    decline_reason: Optional[str] = Field(
        default=None,
        description=(
            "Human-readable explanation of why the request was declined. "
            "Required when is_valid is false. Must be null when is_valid is true."
        ),
    )

    @model_validator(mode="after")
    def _validate_decline_reason(self) -> "IntentResult":
        if not self.is_valid and not self.decline_reason:
            raise ValueError("decline_reason is required when is_valid is false")
        return self


class CountryData(BaseModel):
    """Structured output of the API call node."""
    country: str
    fields: list[str]
    data: dict              # field → parsed string value (None if not in API response)
    found: bool
    error: Optional[str] = None


class AgentState(TypedDict, total=False):
    """
    The single state object threaded through every node in the graph.

    Fields are populated progressively as each node runs. Only `user_input`
    is set at graph entry; the rest start absent and are filled in by the
    nodes responsible for them.
    """
    user_input: Required[str]
    intent: Optional[IntentResult]
    country_data: Optional[CountryData]
    final_answer: Optional[str]
