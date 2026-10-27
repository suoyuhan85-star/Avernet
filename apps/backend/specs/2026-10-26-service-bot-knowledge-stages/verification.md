# Verification of service Bot knowledge selection isolation

The earlier implementation is reused as a source, not as current acceptance
proof. This change adds default-off publication integration and re-runs the
repository, orchestration, transaction and HTTP contracts on the current tree.

See `tests/community/repository/publishing/test_knowledge_publication_policy.py`
for configuration/DI, missing-schema fail-closed, and disabled restore coverage.
The selection lifecycle, restore, rollback and AUTOCOMMIT fault-injection suites
remain executable without external services.

No deployment, external runtime publication, database migration execution or
multi-process OceanBase verification is claimed by these local tests.

## Current run (2026-10-27)

- **2424 passed, 47 warnings**: bot knowledge, publishing repository, service-Bot
  services, knowledge HTTP, architecture and DI suites. No skipped tests.
- New Python files pass formatting; changed Python files pass lint. All modified
  production source files remain below 1000 lines.
- The initial expanded run exposed local test-environment issues: the shared
  corporate venv lacked the lockfile's PyMySQL dependency and exposed corporate
  editable packages to a community-only import test. Installed the locked test
  dependency and ran the public suite without processing corporate `.pth`
  entries; no production or test assertions were weakened for those issues.
- Gate configuration validates boolean values and exercises the real injected
  publication repository. Default-off missing-schema build and restore paths
  execute without binding SQL; opted-in schema failures roll back explicitly.

The full command uses the following targets in an isolated public environment:
```sh
DEPLOY_PROFILE=test PYTHONPATH=src python -m pytest \
  tests/community/core/bot_knowledge \
  tests/community/repository/publishing \
  tests/community/core/service_bot/services \
  tests/community/endpoints/test_bot_knowledge_router.py \
  tests/community/architecture tests/community/di -q
```
