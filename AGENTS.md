# RAVEN — AGENTS.md

**Risk Analysis & Verification for Evidence Navigation**

> **Purpose:** Engineering standards for building RAVEN — a chargeback investigation and evidence-response system that handles any dispute type efficiently.
>
> This document defines **how code must be written** — not what components, schemas, or frameworks to use. Architecture will evolve. These standards do not.
>
> **Read this document completely before writing code.**

---

## 0. Identity — DO NOT MODIFY

**RAVEN is an evidence investigation and verification system for chargeback disputes.**

The AI agent is one component inside the investigation pipeline — it is not the product itself.

The product is:

```
Investigate → Verify → Correlate → Explain → Recommend
```

Six permanent truths:

1. **Evidence first.** The investigation pipeline is the core product. The LLM is a tool within it.
2. **Source data is the authority.** The agent cannot invent, fabricate, override, or silently omit evidence. Every claim must trace to a source record.
3. **Honesty over defense.** RAVEN does not blindly defend the merchant. Missing, contradictory, or insufficient evidence is surfaced, never hidden.
4. **Business-agnostic at the core.** Merchant-specific schemas are normalized at the boundary. The investigation engine operates on canonical evidence.
5. **Bounded authority.** RAVEN investigates and recommends. Humans authorize consequential actions. Autonomous submission requires explicit, scoped authorization.
6. **Structured investigation, not conversation.** RAVEN is not a chatbot. It runs a structured investigation workflow.

**Any change that violates these six statements is invalid, regardless of justification.** Section 0 must never be modified.

---

## 1. Comprehension First

**Read before you write. Trace before you change.**

Before modifying anything:

1. Read the relevant files.
2. Understand the data flow and why the existing boundary exists.
3. Check callers and downstream consumers.
4. Only then decide what needs to change.

Never refactor a component because its structure looks unfamiliar. Never replace an implementation merely because another approach is fashionable. Every change must begin with understanding existing behavior and end with verifying the intended behavior still holds.

---

## 2. Single Intent

**Every change must have one primary purpose.** State what you are changing and why before implementation.

Do not combine unrelated refactoring, UI redesign, infrastructure migration, and feature work into one change.

**Definition of done** — a feature is complete when:

- the behavior is implemented and tested;
- failure cases are handled;
- observability exists;
- the feature works through the real path, not just in isolation;
- documentation is updated if the contract changed.

---

## 3. Code Quality Standards

### Write production code — always

Every line of code must be written as if it ships to production today. There is no "prototype now, clean up later." Prototype code that works becomes permanent code that nobody rewrites.

- Never commit placeholder functions, `TODO` stubs that silently pass, or half-implemented features behind flags.
- If a function exists, it must work. If it cannot work yet, do not create it.
- Every function must handle its failure modes — not just the happy path.
- No hardcoded magic numbers or strings. Extract constants with descriptive names. `AUTO_SUBMIT_THRESHOLD = 0.80` not `if score > 0.8`.
- No shortcut logic that "works for now." If a condition is temporary, it will outlive you.

### No dead code

- Do not leave commented-out code, unused imports, or orphaned functions.
- If code is not called, remove it. Version control preserves history.
- Do not leave `print()` debugging statements. Use proper logging.

### Readability is non-negotiable

Code is read far more often than it is written. Every file must be understandable by a human engineer who has never seen it before.

- Write code that explains itself. If a block needs a comment to be understood, rewrite the block first.
- Keep functions short and focused — one function does one thing.
- Keep files focused — one module owns one responsibility. Split when a file grows beyond a single clear purpose.
- Prefer clear over clever — but clear does not mean verbose. Use the most concise expression that remains immediately understandable.
- Use docstrings on every public function and class. The docstring states what it does and why — not how.
- Group related logic with clear section headers when a module covers multiple concerns.

### Complete error handling

- Every external call (API, database, file I/O) must have explicit error handling.
- Distinguish between retryable and permanent failures.
- Never catch-and-ignore. Every exception must be logged, re-raised, or converted to a meaningful error state.
- Never retry forever. Use bounded retries with backoff for genuinely retryable errors.
- Never silently continue with fabricated placeholder data when a real call fails.

### Type safety

- Use type annotations on every function signature and return type.
- Use enums for finite state sets (statuses, categories, decisions) — not bare strings.
- Use validated models (Pydantic or equivalent) at system boundaries.

### Naming

Names are the first layer of documentation. A developer must understand what something does from its name alone.

- **Functions**: verb + noun describing the action. `assess_case_strength`, `detect_contradictions`, `normalize_delivery` — not `run_v2`, `process`, `handle_stuff`.
- **Variables**: describe the content, not the type. `missing_categories` not `list1`. `dispute_created_at` not `dt`.
- **Booleans**: must read as assertions. `is_verified`, `has_signature`, `timezone_confident` — not `flag`, `check`, `status_bool`.
- **Constants**: uppercase with underscores describing the meaning. `MAX_TOOL_CALLS_PER_CASE` not `LIMIT`.
- **Modules and files**: named for their responsibility. `contradiction_detection.py` not `utils2.py`.
- Never use single-letter variables outside of trivial loop indices. Never use abbreviations that aren't universally understood.

---

## 4. Evidence as the Foundation

Every important claim RAVEN makes must answer: **which source record supports this?**

### Source vs. derived vs. generated

- **Source evidence**: original records from external systems (payments, orders, delivery, auth, comms, refunds).
- **Derived analysis**: anything RAVEN calculates (classification, score, contradiction, recommendation).
- **Generated output**: anything RAVEN creates (timeline, response draft, explanation).

Never store a generated claim as if it were original evidence. Every derived statement must retain a link to the evidence that supports it.

### No unsupported claims

A missing record, an unusual signal, and a confirmed event are three different states. Never conflate them.

- "No delivery record found" is not "Product was not delivered."
- "Device is new" is not "Transaction is fraudulent."
- "Evidence is incomplete" is not "Case should be accepted."

### Evidence states

Evidence must support at minimum these availability states: available, missing, conflicting, unverified, not applicable. Do not force every category into a binary yes/no model.

---

## 5. Boundary Discipline

### Merchant-specific logic stays at the boundary

Different businesses have different data schemas. Normalize source data into a canonical model at the connector/adapter layer. The investigation engine operates on canonical evidence only.

Never scatter conditions like `if merchant == ...` through the analysis, agent, or UI layers. When a business needs a special mapping, isolate it in a connector.

### External inputs are untrusted

Validate API responses, uploaded files, user-provided text, model outputs, environment variables, and configuration.

When an external source violates the expected schema:

1. Reject or quarantine it.
2. Record the failure with enough detail to debug.
3. Do not silently coerce it into a plausible but incorrect value.

### Boundary validation

Use strict validation schemas at ingestion. Vendor APIs may add fields (allow extras); controlled internal schemas must not (forbid extras). Data that fails validation must be quarantined — never silently dropped and never silently accepted.

---

## 6. Contradiction Detection

RAVEN must actively look for conflicts across evidence sources. Contradictions are surfaced, never hidden.

Every detected contradiction must include: which evidence items conflict, what each claims, the severity/impact, and whether human review is required.

Design contradiction rules to be composable — each rule checks one specific conflict pattern. New dispute types should be supportable by adding rules, not by modifying existing ones.

---

## 7. Timeline Reconstruction

For disputes, chronology is more useful than a flat document dump. Reconstruct timelines from evidence. Every event must retain its source evidence link.

**Never invent missing timestamps.** If a timestamp is unavailable, the event is excluded from the timeline. If the timezone is unknown or ambiguous, flag it explicitly.

Normalize all timestamps to UTC. Preserve the original timezone when available. A 12-hour timezone error can make a legitimate delivery appear to happen before the order.

---

## 8. Scoring and Confidence

Confidence must be proportional to evidence. Scores must be deterministic and reproducible from the same inputs.

- Do not let an LLM generate a number and call it a metric. Define the scoring methodology and implement it deterministically.
- Document the methodology alongside the score (e.g., `weighted_evidence_checklist_v1`).
- Separate the scoring logic from the evidence-gathering logic. Scoring is a pure function of gathered evidence and detected contradictions.

---

## 9. LLM Discipline

The LLM is not the source of truth. Use it where language reasoning genuinely helps (dispute interpretation, evidence synthesis, response drafting). Prefer deterministic methods for identity, authorization, arithmetic, timestamps, evidence IDs, database lookups, business limits, action gating, and state transitions.

Never use an LLM where a deterministic check is safer and sufficient.

Do not make the architecture depend on one model or provider. Abstract the reasoning interface so the underlying model can be swapped.

The agent must have bounded resource usage per investigation (tool calls, latency, tokens, retries). If the budget is exceeded, stop and escalate — never loop indefinitely.

---

## 10. Authority and Safety

RAVEN's authority must be explicit and layered:

- **Read**: collect and inspect evidence.
- **Analyze**: classify, correlate, score, identify conflicts.
- **Draft**: prepare an explanation and evidence package.
- **Recommend**: suggest an action with supporting evidence.
- **Execute**: submit to payment gateway. Requires either explicit human approval OR satisfaction of all auto-pilot guardrail criteria.

The higher the consequence, the stronger the authorization requirement.

### Auto-pilot guardrails

Autonomous submission is authorized when **all** of the following are true:

1. Auto-contest is explicitly enabled in system settings.
2. The recommendation is "contest" with auto-submit eligibility (no contradictions, no missing required evidence, no unverified evidence).
3. The confidence score meets or exceeds the configured minimum threshold.
4. The dispute amount does not exceed the configured maximum.
5. The dispute amount is below the mandatory human review threshold.

If any criterion fails, the case routes to human review. The audit trail records every auto-submission with the guardrail values that authorized it.

### State management

Every case must have a well-defined state with explicit transitions. The system must not silently advance a case to a new state. If an investigation fails midway, the case remains in its current state with the failure recorded — it does not advance with incomplete evidence.

### Re-investigation safety

Investigating the same case twice must be safe. Re-investigation must not duplicate evidence. Previously gathered evidence should be reused unless invalidated. The audit trail must record each attempt.

---

## 11. Testing Standards

Tests must cover more than the happy path. At minimum, cover:

- Complete evidence, partial evidence, missing critical evidence, conflicting evidence.
- Customer communications that contradict merchant records.
- Duplicate events, out-of-order events.
- Invalid IDs, malformed input data.
- External API timeout, model timeout, model returning invalid output.
- Empty case, large case.
- Unauthorized action attempt.
- Human rejects recommendation.

### Golden cases

Maintain a small set of manually reviewed cases with stable expected outcomes. Every major reasoning change must be evaluated against them.

### Evaluation

Build a held-out evaluation set. Measure evidence coverage, contradiction detection precision/recall, unsupported claim rate, and investigation time. A system that is impressive on average but confidently fabricates evidence is not acceptable.

---

## 12. Observability and Audit

Every investigation must have a traceable case ID. Record tool calls, tool outcomes, evidence IDs accessed, model used, latency, errors, recommendation, human decision, and final outcome.

The audit trail must answer: **What did RAVEN know, what did it retrieve, what did it conclude, and what action was authorized?**

Do not log unnecessary sensitive content. Use synthetic or anonymized data for development.

---

## 13. API and Interface Standards

- API contracts must be explicit, validated, and idempotent where appropriate.
- Do not expose internal agent state as an API contract without a clear product reason.
- Every loading, empty, error, and partial state in the UI must have a useful message.
- Never display "success" before the underlying operation succeeded.
- Avoid decorative AI features that do not improve investigation.

---

## 14. Structured Outputs

Whenever an AI result is consumed by software, use structured output (JSON with a schema). Validate structured output before it enters the next system boundary. Free-text output is for human-facing content only.

---

## 15. Modularity

Components should know the contract of another component, not its internal implementation. The investigation engine should not know whether evidence came from PostgreSQL, MongoDB, an API, a CSV, or a future vendor.

When designing tools for the agent:

- Each tool has one clear purpose and validates its own inputs.
- Prefer read-only investigation tools over mutation-capable tools.
- Return source identifiers with every result.
- Report errors honestly — never return fabricated fallback data.

When evidence sources are independent, prefer parallel retrieval. When one tool's output determines the next tool's input, sequential execution is required.

---

## 16. Incrementalism

Prefer small change → run tests → inspect output → commit. Every change should be independently understandable and reversible. Keep commits atomic with descriptive messages.

**Avoid these patterns:**

- Starting with the UI or agent framework before the investigation pipeline works.
- Using LLM output as unquestioned truth.
- Fabricating missing evidence.
- Hiding failures.
- Reporting accuracy without explaining the test set.
- Optimizing only for the happy path.
- Adding libraries because they are trendy.
- Adding autonomous actions merely to look more "agentic."
- Claiming production readiness from a synthetic demo.

---

## Final Standard

RAVEN is successful when it is:

- **Useful** — it removes real investigation work.
- **Grounded** — important claims point to evidence.
- **Honest** — uncertainty and missing evidence remain visible.
- **Safe** — authority is bounded and consequential actions are controlled.
- **Measurable** — performance is demonstrated on held-out cases.
- **Generalizable** — works across dispute types; merchant-specific logic stays at the boundary.
- **Maintainable** — responsibilities are separated and contracts are explicit.
- **Verifiable** — failures are tested, not ignored.
- **Simple** — every layer earns its existence.

Build RAVEN as though another engineer will inherit it tomorrow and a dispute investigator will rely on it under pressure.

**The implementation may change. These standards do not.**
