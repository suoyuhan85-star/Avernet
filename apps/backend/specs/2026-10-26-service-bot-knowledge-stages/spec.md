# Service Bot knowledge selection isolation

## Approved outcome

A service Bot has two application-selection values per knowledge base: existing
`enabled` for draft/verification, and `online_enabled` for production. Draft and
verification share one working selection; only draft permits editing. Personal
Bots keep their current, immediately effective selection.

Beginning a publish freezes the enabled KB IDs in that publish record's existing
`ext`. Actual successful online deployment atomically replaces production
selection from that snapshot. Failure, retries, stale callbacks and rollback
admission must not change production. Successful rollback restores its target
snapshot. There is no knowledge-content versioning, new release button or grant
copying; platform grants and native user ACL remain independent live gates.

## Acceptance

- Production {A}, draft {B}: draft/verification read {B}, production reads {A}.
- Publish admission and draft mutation serialize; no mixed snapshot is accepted.
- Only the exact admitted publish attempt may promote production after deployment.
- Empty snapshot is valid; missing/invalid/foreign snapshot never falls back to draft.
- A snapshot cannot revive a different tenant, environment, source Bot or space.
- Personal behavior, native editors, draft revision CAS and grant checks remain.
- New-schema and existing-schema migration scripts are supplied, never run online.
- OCB reads explicitly choose draft or online, including authorized-Bot aggregates.

## Non-goals

Actual MCP runtime wiring, automatic ingestion, Yuque changes, UI, OSS configuration,
production DDL, deployment, pushing and PR creation are outside this implementation.
