# Stage-aware knowledge selection HTTP

## Context Boundary

```yaml
purpose: Adapt authenticated requests for stage-aware application knowledge selection.
provides:
  - router
consumes:
  - BotKnowledgeServiceProtocol
internal_dependencies:
  - agentclaw.community.adapters.http.auth
  - agentclaw.community.api
  - agentclaw.community.di
  - agentclaw.community.kernel
  - agentclaw.community.utils
```

### Change impact
No grant writes or client-controlled publication/version inputs. GET accepts
`selection_stage=draft|online` (default draft); verification shares draft. PUT
only modifies working selection and rejects production fields. Production
advancement is owned by the successful Bot publication transaction.
