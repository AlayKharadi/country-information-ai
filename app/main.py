"""
FastAPI application: The HTTP layer of the Country Information AI Agent.

Responsibilities here are intentionally narrow:
  - Accept and validate the incoming HTTP request
  - Hand a clean question string to the agent
  - Return the agent's answer as a consistent JSON response

Business logic (intent extraction, API calls, answer synthesis) lives in
the agent layer. This file should never need to know about countries or Gemini.
"""

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .agent import agent
from .config import MAX_QUESTION_LENGTH
from .models import AgentState

app = FastAPI(
    title="Country Information AI Agent",
    description=(
        "Answers natural language questions about countries using "
        "the REST Countries API and Gemini 2.5 Flash."
    ),
    version="1.0.0",
)

# Allow all origins; this is a public API with no authentication, so CORS
# restrictions would add friction without providing any security benefit.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class AskRequest(BaseModel):
    question: str

class AskResponse(BaseModel):
    answer: str

@app.get("/health")
async def health():
    """Health probe used by Cloud Run to verify the container is up."""
    return JSONResponse({"status": "ok"})

@app.post("/ask", response_model=AskResponse)
async def ask(request: AskRequest):
    """
    Run the country information agent on a natural language question.

    Returns a grounded, conversational answer drawn from the REST Countries API.
    Off-topic questions (not about a country, multiple countries, etc.) are
    declined gracefully and they come back as a 200 with an explanation in `answer`,
    not as an error status. Only malformed requests produce 4xx responses.
    """
    question = request.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty.")

    if len(question) > MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=400,
            detail=f"Question must be {MAX_QUESTION_LENGTH} characters or fewer.",
        )

    initial_state = AgentState(user_input=question)
    result = await agent.ainvoke(initial_state)

    # LangGraph returns a dict of updated state fields when using Pydantic models.
    # We handle both dict and model return shapes defensively across LangGraph versions.
    if isinstance(result, dict):
        answer = result.get("final_answer") or "Something went wrong, please try again."
    else:
        answer = result.final_answer or "Something went wrong, please try again."

    return AskResponse(answer=answer)
