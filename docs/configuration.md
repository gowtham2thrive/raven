# RAVEN Configuration Guide

> All environment variables, settings, and deployment configuration.

---

## Environment Variables

All settings are read from environment variables with the `RAVEN_` prefix, or from a `.env` file in the `server/` directory.

**Source file:** [`config.py`](file:///c:/Users/gowth/Desktop/raven/server/app/config.py)

### Quick Setup

```bash
cd server
cp .env.example .env
# Edit .env with your values
```

---

## Variable Reference

### Database

| Variable | Default | Description |
|---|---|---|
| `RAVEN_DATABASE_URL` | `sqlite:///./raven.db` | Database connection string |

**Examples:**

```env
# SQLite (development)
RAVEN_DATABASE_URL=sqlite:///./raven.db

# PostgreSQL (production)
RAVEN_DATABASE_URL=postgresql://raven:password@localhost:5432/raven
```

> **Note:** SQLite is used for development and demo. PostgreSQL is recommended for production.

---

### Razorpay

| Variable | Default | Description |
|---|---|---|
| `RAVEN_RAZORPAY_KEY_ID` | `""` | Razorpay API key ID |
| `RAVEN_RAZORPAY_KEY_SECRET` | `""` | Razorpay API key secret |
| `RAVEN_RAZORPAY_WEBHOOK_SECRET` | `""` | Webhook signature verification secret |

**Test vs Live Mode:**

| Key Prefix | Mode | Behavior |
|---|---|---|
| `rzp_test_` | Test | Synthetic data, no real transactions |
| `rzp_live_` | Live | Real payments, real disputes |

The `is_test_mode` property automatically detects test mode from the key prefix.

---

### Agent (AI)

| Variable | Default | Description |
|---|---|---|
| `RAVEN_GEMINI_API_KEY` | `""` | Google Gemini API key for ADK agent |
| `RAVEN_AGENT_MODEL` | `gemini-3.6-flash` | LLM model name for the ADK agent |
| `RAVEN_AGENT_MAX_TOOL_CALLS` | `15` | Maximum tool calls per investigation |
| `RAVEN_AGENT_MAX_LATENCY_SECONDS` | `60` | Maximum investigation duration (seconds) |
| `RAVEN_AGENT_MAX_RETRIES` | `2` | Maximum retries per failed tool call |

**How the agent mode is determined:**

```
RAVEN_GEMINI_API_KEY is set?
    │
    ├── YES → ADK Agent mode
    │         LLM decides tool order via function calling
    │         Falls back to deterministic on failure
    │
    └── NO  → Deterministic mode
              All tools called in fixed order
              No API key needed, works offline
```

> **Important:** Scoring and assessment are ALWAYS deterministic, regardless of agent mode. The LLM only influences tool selection order and reasoning messages.

### Available Models

RAVEN ships with a curated model catalog. The active model is configurable via `RAVEN_AGENT_MODEL`:

| Model ID | Tier | Speed | Default |
|---|---|---|---|
| `gemini-3.6-flash` | Free / Economy | ⚡ Ultra Fast (~1.5s) | ✅ |
| `gemini-2.5-flash-lite` | Budget | ⚡⚡ Fastest (~0.8s) | |
| `gemini-3.7-flash` | Hybrid Reasoning | ⚡ Fast (~2.0s) | |
| `gemini-2.5-pro` | Deep Reasoning | 🧠 Deep (~4.0s) | |

---

### Application

| Variable | Default | Description |
|---|---|---|
| `RAVEN_ENVIRONMENT` | `development` | Environment name (`development`, `production`) |
| `RAVEN_DEBUG` | `true` | Enable debug mode |
| `RAVEN_LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |

---

## Complete `.env.example`

```env
# RAVEN Server Environment Variables
# Copy to .env and fill in your values

# Database (SQLite for dev, PostgreSQL for production)
RAVEN_DATABASE_URL=sqlite:///./raven.db
# RAVEN_DATABASE_URL=postgresql://raven:raven@localhost:5432/raven

# Razorpay API Keys (test mode)
RAVEN_RAZORPAY_KEY_ID=rzp_test_xxxxxxxxxxxxx
RAVEN_RAZORPAY_KEY_SECRET=xxxxxxxxxxxxxxxxxxxx
RAVEN_RAZORPAY_WEBHOOK_SECRET=xxxxxxxxxxxxxxxxxxxx

# Agent (Google ADK — model-agnostic)
RAVEN_GEMINI_API_KEY=
RAVEN_AGENT_MODEL=gemini-3.6-flash

# Application
RAVEN_ENVIRONMENT=development
RAVEN_DEBUG=true
RAVEN_LOG_LEVEL=INFO
```

---

## Docker Configuration

### Dockerfile

The Docker build is a multi-step process:

```
1. Base image: python:3.12-slim
2. Install Python dependencies from pyproject.toml
3. Copy server code
4. Copy pre-built frontend (web/dist/)
5. Set PYTHONPATH, expose port 8000
6. Health check at /health every 30s
7. Run uvicorn on 0.0.0.0:8000
```

### docker-compose.yml

```yaml
services:
  raven:
    build: .
    ports:
      - "8000:8000"
    environment:
      - RAVEN_GEMINI_API_KEY=${GEMINI_API_KEY:-}
      - RAVEN_DATABASE_URL=sqlite:///./raven.db
      - RAVEN_ENVIRONMENT=production
      - RAVEN_DEBUG=false
    volumes:
      - raven-data:/app/data
    restart: unless-stopped

volumes:
  raven-data:
```

### Building & Running with Docker

```bash
# Build frontend first
cd web && npm run build && cd ..

# Build and run
docker compose up --build

# Access at http://localhost:8000
```

### Passing the Gemini API Key

```bash
GEMINI_API_KEY=your_key_here docker compose up
```

---

## CORS Configuration

The server allows cross-origin requests from these origins:

| Origin | Purpose |
|---|---|
| `http://localhost:5173` | Vite dev server |
| `http://localhost:5174` | Vite fallback port |
| `http://localhost:3000` | Next.js dev server |
| `http://127.0.0.1:5173` | Vite (IP variant) |
| `http://127.0.0.1:5174` | Vite fallback (IP variant) |
| `http://127.0.0.1:3000` | Next.js (IP variant) |

In production, restrict these to your actual frontend domain.

---

## Static File Serving

When running in production (Docker), the server automatically serves the pre-built frontend from `web/dist/` if the directory exists:

```
web/dist/ exists?
    │
    ├── YES → Mount at "/" as static HTML
    │         Single-page app served by FastAPI
    │
    └── NO  → Frontend not served
              Use Vite dev server separately
```

---

## Agent Budget Configuration

The agent has bounded resource usage per investigation to prevent runaway execution:

| Budget | Variable | Default | Exceeded → |
|---|---|---|---|
| Tool calls | `RAVEN_AGENT_MAX_TOOL_CALLS` | 15 | Stop + escalate |
| Latency | `RAVEN_AGENT_MAX_LATENCY_SECONDS` | 60s | Stop + escalate |
| Retries | `RAVEN_AGENT_MAX_RETRIES` | 2 | Fall back to deterministic |

> **Principle:** A runaway agent is worse than a slow human.

---

## Dependencies

### Core Dependencies

| Package | Version | Purpose |
|---|---|---|
| `fastapi` | ≥ 0.115 | Web framework |
| `uvicorn[standard]` | ≥ 0.30 | ASGI server |
| `sqlalchemy` | ≥ 2.0 | ORM |
| `alembic` | ≥ 1.13 | Database migrations |
| `pydantic` | ≥ 2.0 | Data validation |
| `pydantic-settings` | ≥ 2.0 | Settings management |
| `razorpay` | ≥ 1.4 | Razorpay SDK |
| `httpx` | ≥ 0.27 | HTTP client |
| `python-dotenv` | ≥ 1.0 | Environment file loading |

### Optional: Agent Dependencies

```bash
pip install -e ".[agent]"
```

| Package | Version | Purpose |
|---|---|---|
| `google-adk` | ≥ 0.5 | Google Agent Development Kit |
| `google-genai` | ≥ 1.0 | Google Generative AI SDK |

### Development Dependencies

```bash
pip install -e ".[dev]"
```

| Package | Version | Purpose |
|---|---|---|
| `pytest` | ≥ 8.0 | Testing framework |
| `pytest-asyncio` | ≥ 0.24 | Async test support |
| `pytest-cov` | ≥ 5.0 | Coverage reporting |
| `ruff` | ≥ 0.5 | Linting & formatting |
