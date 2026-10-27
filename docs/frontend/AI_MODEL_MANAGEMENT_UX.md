# AI Model Management UX (M7C)

## Location

**Settings → AI Models** tab (`NEXT_PUBLIC_FEATURE_AI_MODEL_REGISTRY`, default on in dev).

## User flow

1. Register provider (type card → form with `env://` secret reference)
2. Test connection
3. Register model (CHAT / EMBEDDING / RERANKER)
4. Test model
5. Assign capability (Ask Data, RAG, Skills, etc.)
6. Application runtime resolves registry assignment before legacy env config

## Legacy chat preference

The dropdown at the bottom of the AI Models tab remains the **legacy fallback** preference for new chat UI selection when no registry assignment applies. Registry assignments take precedence at runtime (M7B).

## Security

- UI shows **Credentials configured**, not resolved secrets
- Plaintext API keys are rejected in the secret reference field
- Provider test results show normalized messages only

## Empty states

- No providers → register CTA
- No models → register model after provider exists
- Legacy fallback banner on assignment rows when `source=LEGACY_FALLBACK`
