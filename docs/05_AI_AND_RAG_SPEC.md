# 05 — AI Assistant and RAG Specification

## 1. Principles

- AI is assistive, not autonomous, in MVP.
- All AI results are untrusted external input.
- Never expose API keys to the browser.
- Use explicit timeouts, bounded retries, rate limits, usage limits, and cost monitoring.
- Use a provider adapter so tests and future providers do not depend on one vendor.
- Do not log full prompts/responses by default; redact sensitive fields.
- Treat ticket text and retrieved documents as data, not instructions. Prompt injection can occur inside both.
- No AI draft may be sent to a customer without an authorized human action.

## 2. Classification output

Require a strict structured schema similar to:

```json
{
  "category": "billing",
  "sentiment": "negative",
  "suggested_priority": "high",
  "confidence": 0.82,
  "rationale": "Customer reports duplicate billing and repeated unsuccessful contact."
}
```

Validation:
- Enum values must be allowlisted.
- Confidence must be numeric within [0, 1].
- Rationale must be short and must not be treated as authoritative fact.
- If schema validation fails, mark job failed/retry only when appropriate; do not blindly trust malformed output.
- AI may suggest priority, but deterministic rules can enforce urgent categories and policy overrides.

## 3. Reply generation flow

1. Load ticket and conversation through tenant-scoped services.
2. Retrieve published knowledge chunks belonging to the same workspace.
3. Build a bounded context window; minimize personal data.
4. Call LLM with a versioned prompt.
5. Require structured output with draft text and source IDs.
6. Validate every returned source ID against the retrieved candidate set.
7. Persist draft and source metadata.
8. Show agent the draft, sources, and clear approval action.
9. Only a separate authorized message-send endpoint can publish a reply.

If retrieval returns no relevant content, the model should ask for more information or draft a cautious acknowledgement rather than inventing policy.

## 4. RAG implementation

MVP options:
- Simpler initial release: PostgreSQL full-text search.
- Semantic search: PostgreSQL with `pgvector` and an embedding model.

Pipeline:
- Normalize article text.
- Split into chunks with overlap and stable identifiers.
- Embed chunks asynchronously.
- Store `workspace_id`, article/version IDs, content, and embedding.
- Retrieve only from published articles in the authorized workspace.
- Rank candidates and return a small bounded set.
- Include source title/section in UI.
- Reindex on article version changes and remove/archive obsolete chunks.

Tenant filter must be applied in the retrieval query itself, not after content has already been sent to the model.

## 5. Prompt-injection defenses

- System/developer instructions define policy; user/ticket/article text is explicitly untrusted.
- Do not give the model tools that can execute arbitrary actions in MVP.
- The model cannot change permissions, issue refunds, close tickets, or send messages.
- Validate model output and source IDs in application code.
- Escape content in the frontend.
- Test malicious ticket text and malicious knowledge articles.
- Never rely on a prompt alone as an authorization boundary.

## 6. Reliability and cost controls

- Set connection and read timeouts.
- Retry transient errors with exponential backoff and jitter; do not retry validation errors indefinitely.
- Limit input length, retrieved chunks, output tokens, and per-workspace requests.
- Track job status, latency, provider, model, token/cost estimate where available, and error category.
- Use idempotency keys or unique job keys to avoid duplicate processing.
- Provide manual retry for failed jobs.
- Implement a fake provider for deterministic tests.
- Keep ticket creation successful if AI processing fails.

## 7. Evaluation

Maintain a small versioned test set of fictional tickets and knowledge articles. Evaluate:
- Classification schema validity.
- Category/priority agreement with expected labels.
- Whether cited sources actually support the draft.
- Whether the answer refuses to invent policy when sources are absent.
- Prompt injection resistance.
- No cross-tenant retrieval.
- Tone, relevance, and inappropriate content.
- Regression when prompt/model/provider changes.

Record prompt version and evaluation result. Do not claim AI quality from a few successful demos; document known limitations.
