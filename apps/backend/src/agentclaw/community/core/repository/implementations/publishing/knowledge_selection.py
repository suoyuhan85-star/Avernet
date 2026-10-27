"""Knowledge selection effects inside the caller's publication transaction.

No remote I/O, independent commit, Bot.ext writes or knowledge-content snapshots. Bot
locking is shared with the binding writer (including SQLite's write reservation).
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from uuid import uuid4

from agentclaw.community.core.bot_knowledge.repository.models import (
    BotKnowledgeBindingModel as Binding,
)
from agentclaw.community.core.bot_knowledge.repository.store import resolve_bot
from agentclaw.community.core.service_bot.repository.config_artifact_offload import (
    ARTIFACT_KEY,
    ARTIFACT_OSS_MARKER,
)
from agentclaw.community.core.service_bot.repository.models import (
    BotPublishModel as Publish,
)
from agentclaw.community.core.service_bot.repository.models import (
    PublishOperationKind,
    PublishOperationState,
    PublishStatus,
)
from agentclaw.community.core.service_bot.repository.models import (
    PublishOperationModel as Operation,
)
from agentclaw.community.kernel.knowledge import (
    BotKnowledgeScope,
    KnowledgeError,
    require_knowledge_id,
)
from agentclaw.community.plugin_api.models import BotModel
from agentclaw.community.utils.env_utils import get_current_env
from sqlalchemy import func, or_

SNAPSHOT_KEY = "knowledge_selection_snapshot"
_RESTORE_KEY = "knowledge_selection_restore"
_ROLLBACK_BASE_KEY = "knowledge_selection_rollback_base"
_MAX_SELECTION = 100
_MAX_EXT_BYTES = 60000


def _locked_source(session, publish):
    source = (
        session.query(BotModel)
        .filter(
            BotModel.id == publish.source_bot_pk,
            BotModel.bot_id == publish.source_bot_id,
            BotModel.env == publish.env,
            BotModel.bot_type == "service",
            BotModel.is_delete == 0,
        )
        .one_or_none()
    )
    if source is None or publish.env != get_current_env():
        raise KnowledgeError("KNOWLEDGE_PUBLISH_SOURCE_MISMATCH")
    source = resolve_bot(
        session,
        BotKnowledgeScope(source.bot_id, source.owner_id, source.env),
        lock=True,
    )
    session.refresh(publish, with_for_update=True)
    if (
        source.id != publish.source_bot_pk
        or source.bot_id != publish.source_bot_id
        or source.env != publish.env
        or source.bot_type != "service"
        or source.is_delete
    ):
        raise KnowledgeError("KNOWLEDGE_PUBLISH_SOURCE_MISMATCH")
    return source


def _bindings(session, bot):
    return session.query(Binding).filter(
        Binding.bot_pk == bot.id,
        Binding.env == bot.env,
        Binding.space_id == bot.space_id,
        Binding.avernet_tenant == bot.avernet_tenant,
    )


def _ext(row):
    return json.loads(row.ext) if row.ext else {}


def encode_ext(ext):
    # Match offloader.prepare's persisted ordering without resolving or dropping
    # an existing OSS marker. Otherwise the very next exact ext CAS would miss.
    artifact_keys = (ARTIFACT_KEY, ARTIFACT_OSS_MARKER)
    canonical = {key: value for key, value in ext.items() if key not in artifact_keys}
    for key in artifact_keys:
        if key in ext:
            canonical[key] = ext[key]
    encoded = json.dumps(canonical, ensure_ascii=False)
    validate_encoded_ext(encoded)
    return encoded


def validate_encoded_ext(encoded):
    if encoded is None or len(encoded.encode("utf-8")) <= _MAX_EXT_BYTES:
        return
    ext = json.loads(encoded)
    if SNAPSHOT_KEY in ext or _RESTORE_KEY in ext:
        raise KnowledgeError("KNOWLEDGE_PUBLISH_EXT_TOO_LARGE")


def _unconfigured(session, source):
    # No old-space rows either: a move must not turn missing history into an
    # invented empty snapshot. This exemption only preserves non-knowledge Bots.
    return (
        session.query(Binding.id)
        .filter(
            Binding.bot_pk == source.id,
            Binding.env == source.env,
            Binding.avernet_tenant == source.avernet_tenant,
        )
        .first()
        is None
    )


def _snapshot_or_unconfigured(session, publish, source):
    if SNAPSHOT_KEY not in _ext(publish) and _unconfigured(session, source):
        return None
    return validate_snapshot(publish, source)


def validate_snapshot(publish, source):
    snapshot = _ext(publish).get(SNAPSHOT_KEY)
    if snapshot is None:
        raise KnowledgeError("KNOWLEDGE_SNAPSHOT_MISSING")
    expected = {
        "schema_version": 1,
        "source_bot_pk": source.id,
        "space_id": source.space_id,
        "env": source.env,
        "avernet_tenant": source.avernet_tenant,
        "publish_id": publish.id,
    }
    if not isinstance(snapshot, dict) or any(
        type(snapshot.get(k)) is not type(v) or snapshot.get(k) != v
        for k, v in expected.items()
    ):
        raise KnowledgeError("KNOWLEDGE_SNAPSHOT_SCOPE_MISMATCH")
    ids = snapshot.get("enabled_kb_ids")
    generation = snapshot.get("generation")
    if (
        not isinstance(generation, str)
        or len(generation) != 32
        or not isinstance(ids, list)
        or len(ids) > _MAX_SELECTION
        or any(not isinstance(kb, str) for kb in ids)
        or len(set(ids)) != len(ids)
        or (source.space_id is None and ids)
    ):
        raise KnowledgeError("KNOWLEDGE_SNAPSHOT_INVALID")
    try:
        for kb in ids:
            require_knowledge_id(kb, "kb_id")
        int(generation, 16)
    except ValueError as exc:
        raise KnowledgeError("KNOWLEDGE_SNAPSHOT_INVALID") from exc
    return snapshot


def freeze_build(session, publish_id):
    publish = session.query(Publish).filter(Publish.id == publish_id).one_or_none()
    if publish is None or publish.status != PublishStatus.DRAFT:
        return False
    source = _locked_source(session, publish)
    if publish.status != PublishStatus.DRAFT:
        return False
    ids = [
        r[0]
        for r in _bindings(session, source)
        .with_entities(Binding.kb_id)
        .filter(Binding.enabled.is_(True))
        .order_by(Binding.kb_id)
        .limit(_MAX_SELECTION + 1)
        .all()
    ]
    if len(ids) > _MAX_SELECTION:
        raise KnowledgeError("KNOWLEDGE_LIMIT_EXCEEDED")
    predecessor_generation = None
    if publish.last_pub_id:
        predecessor = (
            session.query(Publish)
            .filter(
                Publish.id == publish.last_pub_id,
                Publish.source_bot_pk == source.id,
                Publish.env == source.env,
            )
            .one_or_none()
        )
        if predecessor is None:
            raise KnowledgeError("KNOWLEDGE_PUBLISH_SOURCE_MISMATCH")
        predecessor_generation = (_ext(predecessor).get(SNAPSHOT_KEY) or {}).get(
            "generation"
        )
    ext = _ext(publish)
    ext.pop(_ROLLBACK_BASE_KEY, None)
    ext[SNAPSHOT_KEY] = {
        "schema_version": 1,
        "source_bot_pk": source.id,
        "space_id": source.space_id,
        "env": source.env,
        "avernet_tenant": source.avernet_tenant,
        "publish_id": publish.id,
        "generation": uuid4().hex,
        "enabled_kb_ids": ids,
        "predecessor_generation": predecessor_generation,
    }
    publish.ext = encode_ext(ext)
    publish.status = PublishStatus.BUILDING
    publish.gmt_modified = func.now()
    session.flush()
    return True


def protected_ext(session, publish_id, incoming):
    """A legacy/background ext writer cannot erase or replace a frozen selection."""
    row = (
        session.query(Publish)
        .filter(Publish.id == publish_id)
        .with_for_update()
        .one_or_none()
    )
    result = copy.deepcopy(incoming)
    stored = _ext(row) if row is not None else {}
    for key in (SNAPSHOT_KEY, _RESTORE_KEY, _ROLLBACK_BASE_KEY):
        if key in result and result[key] != stored.get(key):
            raise KnowledgeError("KNOWLEDGE_SNAPSHOT_READ_ONLY")
        if key in stored:
            result[key] = copy.deepcopy(stored[key])
    return result


def prepare_online(session, publish_id, expected_json):
    """Lock Bot before publication CAS; reject a stale outcome without effects."""
    publish = session.query(Publish).filter(Publish.id == publish_id).one_or_none()
    if (
        publish is None
        or publish.status != PublishStatus.ONLINE_PUB
        or publish.ext != expected_json
    ):
        return None
    source = _locked_source(session, publish)
    if publish.status != PublishStatus.ONLINE_PUB or publish.ext != expected_json:
        return None
    snapshot = _snapshot_or_unconfigured(session, publish, source)
    if snapshot is not None:
        _require_success_predecessor(session, publish, source, snapshot)
    return source, snapshot


def replace_online(session, source, snapshot):
    """Called only after the status/ext CAS won, in that exact transaction."""
    if snapshot is None:
        return
    query = _bindings(session, source)
    # A disabled row remains durable, so historical frozen ids must still exist.
    ids = snapshot["enabled_kb_ids"]
    present = (
        {
            r[0]
            for r in query.with_entities(Binding.kb_id)
            .filter(Binding.kb_id.in_(ids))
            .all()
        }
        if ids
        else set()
    )
    if not set(snapshot["enabled_kb_ids"]).issubset(present):
        raise KnowledgeError("KNOWLEDGE_SNAPSHOT_BINDING_MISSING")
    query.filter(Binding.online_enabled.is_(True), Binding.kb_id.not_in(ids)).update(
        {Binding.online_enabled: False},
        synchronize_session=False,
    )
    if ids:
        query.filter(Binding.online_enabled.is_(False), Binding.kb_id.in_(ids)).update(
            {Binding.online_enabled: True},
            synchronize_session=False,
        )


def _locked_restore_operation(
    session,
    draft,
    *,
    source_publish_id,
    operation_id,
    expected_attempt,
):
    operation = (
        session.query(Operation)
        .filter(Operation.id == operation_id)
        .with_for_update()
        .one_or_none()
    )
    if (
        operation is None
        or operation.publish_id != draft.id
        or operation.operation_kind != str(PublishOperationKind.DRAFT_RESTORE)
        or operation.stage != "draft"
        or operation.env != draft.env
        or type(expected_attempt) is not int
        or expected_attempt <= 0
        or operation.attempt != expected_attempt
    ):
        raise KnowledgeError("KNOWLEDGE_RESTORE_OPERATION_MISMATCH")
    params = json.loads(operation.params) if operation.params else {}
    if (
        not isinstance(params, dict)
        or type(params.get("source_publish_id")) is not int
        or params["source_publish_id"] != source_publish_id
        or type(params.get("source_version")) is not int
        or params["source_version"] <= 0
    ):
        raise KnowledgeError("KNOWLEDGE_RESTORE_OPERATION_MISMATCH")
    # The ledger, not a marker left by a previous partial implementation, is
    # authoritative. Completed delivery must never replay the selection write.
    if operation.state == PublishOperationState.COMPLETED:
        return operation, params
    if operation.state not in (
        PublishOperationState.PENDING,
        PublishOperationState.ID_RECORDED,
    ):
        raise KnowledgeError("KNOWLEDGE_RESTORE_OPERATION_TERMINAL")
    latest = (
        session.query(Operation)
        .filter(
            Operation.publish_id == draft.id,
            Operation.operation_kind == str(PublishOperationKind.DRAFT_RESTORE),
            Operation.stage == "draft",
            Operation.env == draft.env,
        )
        .order_by(Operation.attempt.desc(), Operation.id.desc())
        .with_for_update()
        .first()
    )
    if latest.id != operation.id:
        raise KnowledgeError("KNOWLEDGE_RESTORE_OPERATION_SUPERSEDED")
    return operation, params


def _require_restore_deadline(params):
    raw = params.get("deadline_at")
    try:
        if not isinstance(raw, str) or not raw:
            raise ValueError("deadline_at is missing")
        deadline = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise KnowledgeError("KNOWLEDGE_RESTORE_DEADLINE_INVALID") from exc
    if datetime.now(tz=deadline.tzinfo) >= deadline:
        raise KnowledgeError("KNOWLEDGE_RESTORE_OPERATION_EXPIRED")


def restore_draft(
    session,
    *,
    draft_publish_id,
    source_publish_id,
    operation_id,
    expected_attempt: int,
    final_result: dict,
):
    """Commit the selection and native operation completion in one transaction."""
    draft = session.query(Publish).filter(Publish.id == draft_publish_id).one_or_none()
    if draft is None:
        return False
    source = _locked_source(session, draft)
    operation, params = _locked_restore_operation(
        session,
        draft,
        source_publish_id=source_publish_id,
        operation_id=operation_id,
        expected_attempt=expected_attempt,
    )
    if operation.state == PublishOperationState.COMPLETED:
        return True
    latest = (
        session.query(Publish)
        .filter(
            Publish.source_bot_pk == source.id,
            Publish.env == source.env,
        )
        .order_by(Publish.version.desc(), Publish.id.desc())
        .with_for_update()
        .first()
    )
    if draft.status != PublishStatus.DRAFT or latest.id != draft.id:
        raise KnowledgeError("BOT_DRAFT_REQUIRED", 403)
    previous = (
        session.query(Publish)
        .filter(
            Publish.id == source_publish_id,
            Publish.source_bot_pk == source.id,
            Publish.env == source.env,
        )
        .with_for_update()
        .one_or_none()
    )
    if (
        previous is None
        or draft.last_pub_id != previous.id
        or previous.version != params["source_version"]
    ):
        raise KnowledgeError("KNOWLEDGE_PUBLISH_SOURCE_MISMATCH")
    snapshot = _snapshot_or_unconfigured(session, previous, source)
    bindings = []
    ids = set(snapshot["enabled_kb_ids"]) if snapshot is not None else set()
    if snapshot is not None:
        bindings = (
            _bindings(session, source)
            .filter(or_(Binding.enabled.is_(True), Binding.kb_id.in_(ids)))
            .with_for_update()
            .limit(_MAX_SELECTION * 2 + 1)
            .all()
        )
        if len(bindings) > _MAX_SELECTION * 2:
            raise KnowledgeError("KNOWLEDGE_LIMIT_EXCEEDED")
        if not ids.issubset({row.kb_id for row in bindings}):
            raise KnowledgeError("KNOWLEDGE_SNAPSHOT_BINDING_MISSING")
    # Check after every potentially blocking lock read, just before any writes.
    _require_restore_deadline(params)
    result_json = json.dumps(final_result, ensure_ascii=False)
    for row in bindings:
        value = row.kb_id in ids
        if row.enabled != value:
            row.enabled = value
            row.revision += 1
            row.updated_by = "publish_restore"
    if snapshot is not None:
        ext = _ext(draft)
        ext[_RESTORE_KEY] = {
            "operation_id": operation_id,
            "source_publish_id": source_publish_id,
        }
        draft.ext = encode_ext(ext)
        draft.gmt_modified = func.now()
    operation.result = result_json
    operation.state = PublishOperationState.COMPLETED.value
    operation.gmt_modified = func.now()
    session.flush()
    return True


def prepare_rollback_base(session, demoted_publish_id, restored_publish_id):
    """Capture the exact demoted generation, before native rollback changes status.

    Lock order remains Bot -> publish. No knowledge state is advanced here.
    """
    demoted = (
        session.query(Publish).filter(Publish.id == demoted_publish_id).one_or_none()
    )
    restored = (
        session.query(Publish).filter(Publish.id == restored_publish_id).one_or_none()
    )
    if demoted is None or restored is None:
        return None
    if SNAPSHOT_KEY not in _ext(demoted) and SNAPSHOT_KEY not in _ext(restored):
        return None  # untouched legacy publication, with no knowledge metadata
    if restored.source_bot_pk != demoted.source_bot_pk or restored.env != demoted.env:
        raise KnowledgeError("KNOWLEDGE_PUBLISH_SOURCE_MISMATCH")
    source = _locked_source(session, demoted)
    session.refresh(restored, with_for_update=True)
    if (
        restored.source_bot_pk != source.id
        or restored.env != source.env
        or demoted.last_pub_id != restored.id
    ):
        raise KnowledgeError("KNOWLEDGE_PUBLISH_SOURCE_MISMATCH")
    validate_snapshot(restored, source)
    snapshot = validate_snapshot(demoted, source)
    return {"publish_id": demoted.id, "generation": snapshot["generation"]}


def with_rollback_base(ext, baseline):
    result = copy.deepcopy(ext)
    if baseline is not None:
        result[_ROLLBACK_BASE_KEY] = baseline
    return result


def _require_success_predecessor(session, publish, source, snapshot):
    rollback_base = _ext(publish).get(_ROLLBACK_BASE_KEY) or {}
    successes = (
        session.query(Publish)
        .filter(
            Publish.source_bot_pk == source.id,
            Publish.env == source.env,
            Publish.status == PublishStatus.SUCCESS,
            Publish.id != publish.id,
        )
        .limit(3)
        .all()
    )  # only last_pub_id and rollback base can legitimately precede us
    for previous in successes:
        generation = (_ext(previous).get(SNAPSHOT_KEY) or {}).get("generation")
        if previous.id == publish.last_pub_id and generation == snapshot.get(
            "predecessor_generation"
        ):
            continue
        if (
            previous.id == rollback_base.get("publish_id")
            and previous.id == _ext(publish).get("rollback_restored_from")
            and generation == rollback_base.get("generation")
        ):
            continue
        raise KnowledgeError("KNOWLEDGE_ONLINE_PREDECESSOR_CHANGED")
