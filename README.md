# Country Information AI Agent

An AI agent that answers natural language questions about countries using real-time data from the [REST Countries API](https://restcountries.com), orchestrated with LangGraph and Gemini 2.5 Flash.

---

## Architecture

```
POST /ask
    │
    ▼
[Node 1: Intent Extraction]        ← Gemini (JSON mode)
  Extracts: country + fields[]
    │
    ▼
[Conditional Router]
    ├── is_valid: false ──→ [Decline Node] ──→ answer
    └── is_valid: true  ──→ [Node 2: API Call]
                                   │
                                   ▼
                          [Node 3: Answer Synthesis] ← Gemini
                                   │
                                   ▼
                                answer
```

**Why this split?**

Separating intent extraction from synthesis means the agent is grounded. It can only answer questions it has data for. The LLM never answers from memory; it only synthesises from what the REST Countries API returned. This eliminates hallucination of country facts.

---

## Tech Stack

| Component | Choice | Why |
|---|---|---|
| Agent orchestration | LangGraph | Explicit state graph makes the control flow auditable and extensible |
| LLM | Gemini 2.5 Flash | Fast, cheap, supports JSON mode natively |
| Data source | REST Countries API | Free, no auth, accurate country data |
| HTTP client | httpx | Async-native, consistent interface, easy timeout handling |
| Serving | FastAPI + uvicorn | Async-first, automatic schema docs, production-ready |
| Containerisation | Docker | Reproducible environment, Cloud Run compatible |

---

## Project Structure

```
├── app/
│   ├── config.py     # All constants (single source of truth)
│   ├── models.py     # Pydantic models: IntentResult, CountryData, AgentState
│   ├── prompts.py    # All LLM prompts (separated from business logic)
│   ├── tools.py      # REST Countries API integration and field parsing
│   ├── nodes.py      # LangGraph node functions
│   ├── agent.py      # Graph definition and compiled agent singleton
│   └── main.py       # FastAPI app and HTTP endpoints
├── Dockerfile
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## Supported Fields

The agent can retrieve: `population`, `capital`, `currency`, `languages`, `area`, `region`, `subregion`, `flag`, `timezones`, `borders`.

If you ask a more general question ("Tell me about France"), Gemini infers the most relevant 2–4 fields.

---

## Local Development

**Prerequisites:** Python 3.14+, [uv](https://docs.astral.sh/uv/getting-started/installation/), [Google Cloud SDK](https://cloud.google.com/sdk/docs/install) with an active project that has the Vertex AI API enabled.

```bash
# 1. Clone and enter the project
cd assignment

# 2. Authenticate with Application Default Credentials
gcloud auth application-default login

# 3. Install dependencies
uv sync

# 4. Start the server
uv run uvicorn app.main:app --reload
```

The API is now running at `http://localhost:8000`. Interactive docs at `http://localhost:8000/docs`.

### Example requests

```bash
# Happy path
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital of Japan?"}'

# Multiple fields
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is the capital and population of Brazil?"}'

# Off-topic (graceful decline)
curl -X POST http://localhost:8000/ask \
  -H "Content-Type: application/json" \
  -d '{"question": "What is 2 + 2?"}'

# Health check
curl http://localhost:8000/health
```

---

## Running with Docker

```bash
docker build -t country-agent .
# Mount your ADC credentials so the container can authenticate
docker run -p 8080:8080 \
  -v "$HOME/.config/gcloud/application_default_credentials.json:/tmp/adc.json:ro" \
  -e GOOGLE_APPLICATION_CREDENTIALS=/tmp/adc.json \
  country-agent
```

---

## Deploying to Cloud Run (GCP)

```bash
# Build and push image to Container Registry
gcloud builds submit --tag gcr.io/PROJECT_ID/country-agent

# Deploy to Cloud Run
# The service account attached to the Cloud Run service must have the
# "Vertex AI User" IAM role so ADC works without any env vars.
gcloud run deploy country-agent \
  --image gcr.io/PROJECT_ID/country-agent \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated
```

---

## API Reference

### `GET /health`
Liveness probe. Returns `{"status": "ok"}`.

### `POST /ask`

**Request:**
```json
{ "question": "What currency does Japan use?" }
```

**Response:**
```json
{ "answer": "Japan uses the Japanese Yen (¥)." }
```

**Validation errors (400):**
- Empty question
- Question longer than 500 characters

---

## Test Cases

| Input | Expected behaviour |
|---|---|
| `"What is the population of Germany?"` | Returns population figure |
| `"What currency does Japan use?"` | Returns currency name + symbol |
| `"What is the capital and population of Brazil?"` | Returns both fields |
| `"Tell me about France"` | Infers relevant fields, returns summary |
| `"What is the population of Germany and France?"` | Declines: one country at a time |
| `"What is the capital of Wakanda?"` | 404 from API and a clean not found message |
| `"What is 2 + 2?"` | Declines as it is not a country question |
| `""` (empty string) | HTTP 400: empty question |
| 501+ character string | HTTP 400: question too long |

---

## Known Limitations

- **One country per question**: multi-country queries are declined by design, not a bug. Supporting them would require parallel API calls and a more complex synthesis prompt, which is a reasonable next step.
- **10 supported fields**: questions about GDP, presidents, or national holidays will be declined or acknowledged as out of scope. The field set is easy to extend via `config.py` and `tools.py`.
- **No caching**: every request hits the REST Countries API and calls Gemini twice. For a higher-traffic deployment, a caching mechanism would meaningfully reduce latency and cost.
