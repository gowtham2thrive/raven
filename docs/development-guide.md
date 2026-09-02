# Development Guide

> Setup, workflow, and contribution guide for RAVEN.

---

## Prerequisites

| Requirement | Version | Purpose |
|---|---|---|
| Python | ≥ 3.11 | Backend runtime |
| Node.js | ≥ 18 | Frontend build |
| pip | Latest | Python package management |
| npm | Latest | Node package management |
| Docker | Latest (optional) | Containerized deployment |

---

## Quick Start

### 1. Clone & Setup Backend

```bash
cd server

# Create virtual environment (recommended)
python -m venv .venv
.venv\Scripts\activate       # Windows
# source .venv/bin/activate  # macOS/Linux

# Install dependencies
pip install -e ".[dev]"

# Optional: Install agent dependencies (for Gemini ADK)
pip install -e ".[agent]"

# Copy environment file
cp .env.example .env
# Edit .env with your values (see docs/configuration.md)
```

### 2. Generate Synthetic Data

```bash
cd server
python -m data.seed
```

This generates **50 annotated test cases** in `data/synthetic/cases/` covering 5 evidence profiles:

| Profile | Cases | Description |
|---|---|---|
| A_STRONG | 15 | All evidence present, signed delivery, verified auth |
| B_WEAK | 10 | Delivery present but no signature (unverified) |
| C_MISSING | 10 | Missing delivery and shipping evidence |
| D_CONTRADICTORY | 10 | Conflicting delivery vs tracking status |
| E_EDGE | 5 | Timezone mismatches, unusual evidence patterns |

### 3. Start Backend

```bash
cd server
python -m uvicorn app.main:app --reload --port 8000
```

Backend runs at `http://localhost:8000`.

API docs available at `http://localhost:8000/docs`.

### 4. Start Frontend

```bash
cd web
npm install
npm run dev
```

Frontend runs at `http://localhost:5173`.

### 5. Run Demo

```bash
cd server
python -m scripts.demo
```

The demo script:
1. Seeds 8 representative cases (2 per profile)
2. Investigates each case
3. Prints results to terminal
4. Makes everything visible in the dashboard

---

## Project Structure

```
raven/
├── AGENTS.md                          # Engineering contract (immutable)
├── README.md                          # Project overview
├── Dockerfile                         # Production container
├── docker-compose.yml                 # Docker orchestration
│
├── docs/                              # Documentation
│   ├── architecture.md                # System architecture
│   ├── api-reference.md               # REST API reference
│   ├── configuration.md               # Environment & config
│   ├── data-flow-diagram.md           # End-to-end data flow
│   ├── development-guide.md           # This file
│   ├── canonical-evidence-model.md    # Evidence schema
│   ├── decision-engine.md             # Scoring methodology
│   ├── evaluation-report.md           # Test results
│   └── razorpay-integration.md        # Razorpay API guide
│
├── server/                            # Python backend
│   ├── pyproject.toml                 # Project config & dependencies
│   ├── .env.example                   # Environment template
│   │
│   ├── app/                           # Application code
│   │   ├── main.py                    # FastAPI entry point
│   │   ├── config.py                  # Settings (pydantic-settings) + model catalog
│   │   │
│   │   ├── core/                      # Domain primitives
│   │   │   ├── types.py               # All enums + exceptions
│   │   │   ├── schemas.py             # Pydantic models (case, evidence, assessment)
│   │   │   ├── integration_types.py   # Integration-specific enums & errors
│   │   │   └── integration_schemas.py # Integration Pydantic models
│   │   │
│   │   ├── db/                        # Persistence
│   │   │   ├── database.py            # SQLAlchemy engine + session
│   │   │   └── models.py              # ORM models (9 tables)
│   │   │
│   │   ├── connectors/                # Data source abstraction
│   │   │   ├── synthetic.py           # JSON file connector (demo)
│   │   │   ├── razorpay.py            # Razorpay API connector
│   │   │   ├── base_adapter.py        # Abstract adapter interface
│   │   │   ├── adapter_registry.py    # Adapter type discovery
│   │   │   ├── rest_adapter.py        # REST API adapter
│   │   │   ├── database_adapter.py    # Database adapter
│   │   │   ├── file_adapter.py        # File upload adapter (CSV, Excel, PDF)
│   │   │   ├── webhook_adapter.py     # Webhook receiver adapter
│   │   │   ├── carrier.py             # Shipping carrier adapter
│   │   │   └── quarantine.py          # Boundary validation failures
│   │   │
│   │   ├── pipeline/                  # Investigation pipeline
│   │   │   ├── runner.py              # Pipeline orchestrator
│   │   │   ├── ingest.py              # Normalization (raw → canonical)
│   │   │   ├── analysis.py            # Timeline, completeness, contradictions
│   │   │   └── assess.py              # Scoring & decision engine
│   │   │
│   │   ├── agent/                     # AI agent layer
│   │   │   ├── agent.py               # Google ADK agent definition
│   │   │   ├── factory.py             # Agent creation (ADK / deterministic)
│   │   │   ├── callbacks.py           # ADK callback handlers
│   │   │   └── tools.py               # Narrow, validated agent tools
│   │   │
│   │   ├── services/                  # Orchestration
│   │   │   ├── case_service.py        # Case lifecycle management
│   │   │   ├── integration_service.py # Integration CRUD, sync, field mapping
│   │   │   ├── simulator_service.py   # Case generation from presets
│   │   │   └── model_service.py       # AI model discovery
│   │   │
│   │   └── api/                       # HTTP layer
│   │       ├── deps.py                # Dependency injection
│   │       ├── routes.py              # Cases, webhooks, metrics, models, simulator, stream
│   │       ├── integration_routes.py  # Integrations CRUD + sync + mappings
│   │       └── settings_routes.py     # Credentials + guardrails
│   │
│   ├── data/                          # Data layer
│   │   ├── seed.py                    # Synthetic data generator
│   │   └── synthetic/
│   │       └── cases/                 # Generated JSON case files
│   │
│   ├── scripts/                       # CLI tools
│   │   └── demo.py                    # Demo script
│   │
│   └── tests/                         # Test suite (330 tests)
│       ├── unit/                      # Unit tests
│       │   ├── test_analysis.py       # Pipeline analysis (timeline, contradictions)
│       │   ├── test_database.py       # ORM models, state transitions
│       │   ├── test_schemas.py        # Pydantic schema validation
│       │   ├── test_razorpay_client.py # Razorpay client mocking
│       │   ├── test_adapters.py       # Connector adapters
│       │   ├── test_adk_callbacks.py  # ADK callback handlers
│       │   ├── test_adk_factory.py    # Agent factory
│       │   ├── test_audit.py          # Audit trail
│       │   ├── test_diverse_disputes.py # Multi-dispute-type coverage
│       │   ├── test_dynamic_checklist.py # Dynamic evidence checklists
│       │   ├── test_dynamic_types.py  # Dynamic type handling
│       │   ├── test_error_cases.py    # Error/failure paths
│       │   ├── test_integrations.py   # Integration service
│       │   ├── test_new_evidence_tools.py # Evidence tool expansion
│       │   ├── test_robustness.py     # Edge cases and resilience
│       │   ├── test_simulator.py      # Simulator service
│       │   └── test_submit_investigation.py # Submit + investigate flow
│       ├── integration/               # Integration tests
│       │   └── test_api.py            # Full API endpoint testing
│       ├── golden/                    # Golden case tests
│       │   └── test_golden_cases.py   # Stable expected outcomes
│       └── evaluation/                # Evaluation framework
│           ├── annotations.py         # Ground truth annotations
│           ├── metrics.py             # Precision, recall, F1
│           └── runner.py              # Evaluation entry point
│
└── web/                               # React frontend
    ├── package.json
    ├── vite.config.js
    ├── index.html
    └── src/
        ├── main.jsx                   # Entry point
        ├── App.jsx                    # Root component (router, layout)
        ├── App.css                    # Global styles
        │
        ├── api/                       # API client layer
        │   ├── client.js              # Core API client (cases, metrics, etc.)
        │   └── integrations.js        # Integrations API client
        │
        ├── pages/                     # Page components
        │   ├── DisputesPage.jsx       # Case queue + history views
        │   ├── CaseDetailPage.jsx     # Full case detail
        │   ├── AnalyticsPage.jsx      # Dashboard analytics
        │   ├── IntegrationsPage.jsx   # Integration management
        │   └── SettingsPage.jsx       # Credentials + guardrails
        │
        ├── components/                # Reusable UI components
        │   ├── Sidebar.jsx            # Collapsible navigation sidebar
        │   ├── MobileNavbar.jsx       # Responsive mobile nav
        │   ├── DisputeTable.jsx       # Case list table
        │   ├── DisputeDrawer.jsx      # Case detail drawer
        │   ├── DisputeHistoryTable.jsx # History table
        │   ├── EvidenceItem.jsx       # Evidence display card
        │   ├── TimelineEvent.jsx      # Timeline event entry
        │   ├── ContradictionAlert.jsx # Contradiction warning
        │   ├── ResponsePackageCard.jsx # Response draft display
        │   ├── CaseSimulatorModal.jsx # Case generation modal
        │   ├── ModelPicker.jsx        # AI model selector
        │   ├── Badge.jsx              # Status badges
        │   ├── DeadlineBadge.jsx      # Deadline countdown
        │   ├── EmptyState.jsx         # Empty state placeholder
        │   ├── Spinner.jsx            # Loading spinner
        │   ├── Icons.jsx              # Icon components
        │   └── integrations/          # Integration-specific components
        │       ├── IntegrationWizard.jsx  # Setup wizard
        │       ├── IntegrationTable.jsx   # Integration list
        │       ├── IntegrationCard.jsx    # Integration summary card
        │       ├── IntegrationDrawer.jsx  # Integration detail drawer
        │       ├── FieldMappingEditor.jsx # Field mapping UI
        │       └── FileUploader.jsx       # File upload UI
        │
        ├── context/                   # React context providers
        │   └── ModelContext.jsx        # AI model selection state
        │
        ├── hooks/                     # Custom React hooks
        │   └── useDeadline.js         # Deadline countdown logic
        │
        ├── styles/                    # CSS modules
        │   ├── tokens.css             # Design tokens (colors, spacing, etc.)
        │   ├── layout.css             # Layout and grid
        │   ├── components.css         # Component styles
        │   ├── pages.css              # Page-specific styles
        │   └── integrations.css       # Integration-specific styles
        │
        └── utils/                     # Utility functions
            ├── format.js              # Number/date formatting
            └── generateDefensePdf.js  # PDF generation for defense packages
```

---

## Testing

### Unit Tests

```bash
cd server
python -m pytest tests/unit/ -v
```

Tests cover:
- **Pipeline analysis** — Normalizer, timeline builder, completeness checker, contradiction detector
- **Database** — ORM models, state transitions, cascade deletes
- **Razorpay** — Client mocking, webhook parsing
- **Schemas** — Pydantic model validation, serialization
- **Adapters** — REST, database, file, webhook, carrier connector adapters
- **Agent** — ADK callbacks, agent factory, evidence tools
- **Audit** — Audit trail recording and retrieval
- **Integrations** — CRUD, sync, field mapping
- **Simulator** — Case generation from presets
- **Robustness** — Error paths, edge cases, diverse dispute types, dynamic checklists

### Integration Tests

```bash
cd server
python -m pytest tests/integration/ -v
```

Tests the full API stack end-to-end via FastAPI's test client:
- Webhook reception and case creation
- Investigation pipeline
- Evidence retrieval
- Human review workflow
- Metrics calculation

### Golden Case Tests

```bash
cd server
python -m pytest tests/golden/ -v
```

A small set of manually reviewed cases whose expected outcomes must remain stable across changes.

### Evaluation Suite

```bash
cd server
python -m tests.evaluation.runner
```

Runs 50 annotated cases across all 5 profiles and produces:
- Decision precision, recall, F1
- Contradiction detection precision/recall
- Evidence coverage metrics
- Integrity metrics (unsupported claims, fabricated evidence)

### Full Test Suite

```bash
cd server
python -m pytest tests/ -v
# 330 tests
```

---

## Common Development Tasks

### Add a New Evidence Category

1. Add the category to `EvidenceCategory` enum in [`types.py`](file:///c:/Users/gowth/Desktop/raven/server/app/core/types.py)
2. Add normalization logic in [`ingest.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/ingest.py)
3. Add to the connector interface in [`synthetic.py`](file:///c:/Users/gowth/Desktop/raven/server/app/connectors/synthetic.py)
4. Update the completeness template in [`analysis.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/analysis.py)
5. Add timeline label mapping in [`analysis.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/analysis.py)
6. Add section to response generation in [`assess.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/assess.py)
7. Add agent tool in [`tools.py`](file:///c:/Users/gowth/Desktop/raven/server/app/agent/tools.py)
8. Update synthetic data generator in [`seed.py`](file:///c:/Users/gowth/Desktop/raven/server/data/seed.py)
9. Add tests

### Add a New Contradiction Rule

1. Add detection function in [`analysis.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/analysis.py)
2. Call it from the contradiction detection pipeline
3. Add test cases in `test_analysis.py`
4. Update evaluation annotations if needed

### Add a New Dispute Type

1. Add to `DisputeReason` enum in [`types.py`](file:///c:/Users/gowth/Desktop/raven/server/app/core/types.py)
2. Create a new requirements template in [`analysis.py`](file:///c:/Users/gowth/Desktop/raven/server/app/pipeline/analysis.py)
3. Add dispute-specific contradiction rules
4. Update response generation templates
5. Create synthetic cases for the new type
6. Add evaluation annotations

### Switch to a Different LLM

1. Change `RAVEN_AGENT_MODEL` in `.env`
2. The ADK agent automatically uses the new model
3. Scoring remains deterministic — only tool selection changes

---

## Architecture Principles

These are enforced by the [AGENTS.md](file:///c:/Users/gowth/Desktop/raven/AGENTS.md) contract:

1. **Evidence first** — The investigation pipeline is the product, not the LLM
2. **Source data is authority** — Every claim traces to a source record
3. **Honesty over defense** — Contradictions are surfaced, never hidden
4. **Business-agnostic core** — Merchant-specific logic at the boundary only
5. **Bounded authority** — Humans authorize consequential actions
6. **Structured investigation** — Not a chatbot, a workflow engine

---

## Useful Commands

```bash
# Start backend (with auto-reload)
cd server && python -m uvicorn app.main:app --reload --port 8000

# Start frontend (dev mode)
cd web && npm run dev

# Generate synthetic data
cd server && python -m data.seed

# Run demo (seed + investigate)
cd server && python -m scripts.demo

# Investigate a single case (CLI)
cd server && python -m app.pipeline.runner CASE-00001

# Run all tests
cd server && python -m pytest tests/ -v

# Run evaluation
cd server && python -m tests.evaluation.runner

# Build frontend for production
cd web && npm run build

# Docker build + run
docker compose up --build

# Lint code
cd server && ruff check .
```
