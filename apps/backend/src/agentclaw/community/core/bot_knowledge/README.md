# Bot knowledge

External platforms own grants. The platform catalog uses the existing business
Bot ID and target user identifier; no new UUID contract. Service Bots edit only
in draft and have separate working (`enabled`) and production (`online_enabled`)
selection. Draft and verification share the working selection. Personal Bots
keep their immediately effective current selection. Knowledge content is not
version-frozen and no independent knowledge publication workflow is introduced.

## Context Boundary

```yaml
purpose: Persist working and production knowledge selection independently of platform grants.
provides:
  - BotKnowledgeService
  - BotKnowledgeRepository
consumes:
  - DatabasePlugin
  - KnowledgeCatalogPlugin
internal_dependencies:
  - agentclaw.community.kernel
  - agentclaw.community.plugin_api
  - agentclaw.community.core.base
  - agentclaw.community.core.bot_knowledge
  - agentclaw.community.core.bot_collaborator
  - agentclaw.community.core.spaces
  - agentclaw.community.core.service_bot
  - agentclaw.community.utils
```

Only native Owner/explicit Editor may edit. Enabling consults the platform with
the business Bot ID, existing owner/user identifier and current space; disabling does not require a platform call. Revision CAS and
native editor/draft checks run in the same transaction as the current selection.
Re-read on stale revision; no request history is replayed. Deployments must apply
the reviewed current-state schema before enabling integration.

Space-mismatched selections are not inherited. A new-space write uses revision
zero (the absent view); enabling rechecks that space's external catalog. Reusing
an old row keeps its monotonically increasing revision. Only current-space rows
consume the enabled limit. Disabling an absent relation returns disabled/revision
zero without creating a row. Enabled reads/counts and cursor pages have matching
indexes; current service-Bot draft checks retain their transactional recheck.


## Native editability and tenant lineage

Personal Space Owners and explicit Editors do not need Space-member rows.
Team Space edits still require ACTIVE owner and actor membership as well as
ownership or an explicit editor grant. Space existence, editor standing and
current service-Bot draft state are rechecked inside the write transaction.

`ac_bot_publish` has no tenant column. For legacy `default` Bots, publication
candidates are restricted to source Bot rows in the current tenant/environment
before selecting the latest version. A retained historical source PK remains
valid even if it differs from the current Bot PK; it is never silently rebound.
A matching publication whose source was hard-deleted cannot be attributed to a
tenant and fails closed (`BOT_DRAFT_REQUIRED`), including when ignoring it would
otherwise reveal an older draft. No new publication ownership is inferred from
business Bot/owner IDs alone, and no publication schema or DDL is changed.

## Live local acceptance

The unified Singlebox manifest registers all production Core files, both HTTP
routes and both declared `KnowledgeCatalogPlugin` methods. `list_authorized`
is exercised; `list_in_space` currently has no production caller, remains in the
denominator and is not manufactured into coverage through test-only business
calls. The initial Plugin API threshold is the measured 1/2 (50%), not a claim
that both methods were called. The three live HTTP/DB stories cover
selection/CAS/pagination, Personal editor access, Team revocation, draft lifecycle
and tenant-isolated legacy publication selection.

The runner sets `SINGLEBOX_ACCEPTANCE_KNOWLEDGE_FIXTURE_FILE` to the reviewed JSON
catalog. Only the `SINGLEBOX` composition profile reads it; exact Bot/owner/env/
space keys select grants through the existing local Plugin API. Missing catalog
configuration still fails closed; production and unit-test profiles ignore the
fixture variable. This is an external-catalog double, not real remote-platform
integration evidence. Full shared-stack acceptance and artifact verification
must be reported separately from an isolated Backend run.

## Reviewed schema and deferred indexes (2026-10-26)

The approved OceanBase MySQL-mode table definition is
`apps/backend/sql/2026_10_22_bot_knowledge.sql`. It adds database-defaulted
`gmt_create TIMESTAMP`, uses `TIMESTAMP` for `gmt_modified`, retains signed
`BIGINT` IDs/revision and the original business columns/index keys, and supplies
Chinese comments plus OB `GLOBAL` secondary indexes. The portable ORM mirrors
these columns, timestamp defaults and BIGINT revision; it does not emit OB-only
`GLOBAL` syntax. The deployment script supplies database-side `ON UPDATE
CURRENT_TIMESTAMP`; the ORM also sets modification time for local SQLite writes.
Neither timestamp is added to the HTTP response contract.

The two existing-table publication indexes are **deferred and not executed**.
They are recorded separately in
`apps/backend/sql/2026_10_22_bot_knowledge_publish_indexes.sql`, not in the table
creation script. Inspect actual target indexes and query plans and obtain
separate deployment approval before applying them. The ORM still declares these
indexes for fresh local schemas; that is not evidence they exist in an already
running database. Deferring them does not change draft-check correctness, but
production query/lock cost without them remains unverified. No automatic
existing-database migration, production DDL, or deployment is performed here.

## Draft and production selection (2026-10-26)

`GET /api/bot-knowledge/{bot_id}?selection_stage=draft|online` explicitly selects
the view; the default remains draft for compatibility. `items[].enabled` is the
selected value. A service online view reports `runtime_selection=online`; personal
Bots report current in both views. `list_enabled_current` remains a compatibility
working-selection API; new consumers use `list_enabled(..., selection_stage=...)`.
Production state is never writable through the settings API.

`ac_bot_knowledge_binding` retains its identity and draft revision CAS. Production
advancement does not increment that editor revision. Publication owns freezing
the bounded enabled KB-ID set into its existing ext, and atomically replacing
production selection when actual online deployment succeeds. Failed deployment
or rollback admission is not production success. Snapshots cannot cross source
Bot, tenant, environment or space. Reclaiming a binding after a space move clears
its old production flag. Platform grants and native user ACL remain live gates,
not snapshot fields. Actual MCP consumption wiring is outside this change.

Fresh schemas use the updated create script. Existing databases must apply the
review-only `apps/backend/sql/2026_10_26_bot_knowledge_online_selection.sql` before
deploying the new code. It initializes production to false, not from draft:
historical service publications without a trustworthy snapshot must republish.
No migration is executed at startup or against any running environment here.

### Publication integration opt-in

`user_config.bot_knowledge_publication.enabled` is false by default. It controls
only publication snapshot/promotion/restore effects, not knowledge management
APIs. Disabled publication never queries the binding table; enabled integration
requires the additive `online_enabled` column and fails closed on DB errors.
Do not toggle off in the middle of active publication or restore operations.
