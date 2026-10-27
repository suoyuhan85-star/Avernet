# Implementation plan

1. Add default-false non-null `online_enabled` to the existing binding ORM and fresh
   schema, plus a separate existing-table ALTER script. Retain unique identity and
   draft CAS revision. Explicit `selection_stage=draft|online` selects the read view;
   legacy current reads retain draft semantics and personal online reads use current.
2. Freeze the bounded KB-ID snapshot into publish.ext at DRAFT -> BUILDING under
   the same Bot lock as draft writes. Save tenant/env/source PK/space with the IDs.
   Extend publication persistence narrowly so successful ONLINE status CAS and
   production-set replacement share one explicit `transactional_orm_session`
   transaction (ordinary PROD ORM sessions use AUTOCOMMIT). Rollback admission cannot
   promote. Existing ext-CAS fences and snapshot validation reject stale writes.
3. Adapt OCB's authorized-Bot reader/HTTP/service contracts to select the stage;
   do not replicate public schema or pass stage into the platform grant API.
4. Run model/service/HTTP, publication lifecycle, rollback and OCB paired tests;
   review fixed diffs and migration semantics. No running cluster is modified.

## Review hardening within the existing publication boundary

- A rejected two-record rollback CAS rolls back both records; no half-flipped
  publication pair is committed.
- Draft restore completion validates the current native operation, attempt,
  source publication and persisted deadline under locks. Selection, restore
  marker, operation result and COMPLETED are committed in one explicit
  transaction. Terminal/expired/superseded attempts have no write effects; a
  completed replay never overwrites subsequent draft edits.
- These guards do not add a new publication state machine or knowledge table.

## Publication opt-in (2026-10-27)

`user_config.bot_knowledge_publication.enabled` defaults to false. Composition
injects `KnowledgePublicationPolicy`; core never reads deployment config. Disabled
publishing uses native sessions and performs no knowledge-table reads/writes,
including draft restoration. Enabled publishing uses explicit transactions and
propagates schema/persistence failures. No catch-and-fallback is permitted.

Existing enabled snapshots should not be downgraded in flight by turning off the
switch; drain active publication/restore work before disabling the integration.
The switch is independent from knowledge management API availability.
