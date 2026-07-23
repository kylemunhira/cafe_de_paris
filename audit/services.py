from decimal import Decimal

from django.db import models

from .models import AuditAction, AuditEvent


def serialize_value(value):
    """Convert model field values to JSON-safe primitives."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, models.Model):
        return value.pk
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except (TypeError, ValueError):
            return str(value)
    if isinstance(value, (list, tuple)):
        return [serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): serialize_value(item) for key, item in value.items()}
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def snapshot_fields(instance, fields):
    """Read whitelisted fields from a model instance into a plain dict."""
    data = {}
    for field in fields:
        if hasattr(instance, f"{field}_id") and not hasattr(instance, field):
            data[field] = getattr(instance, f"{field}_id")
            continue
        try:
            value = getattr(instance, field)
        except AttributeError:
            continue
        if isinstance(value, models.Manager):
            continue
        if isinstance(value, models.Model):
            data[field] = value.pk
        else:
            data[field] = serialize_value(value)
    return data


def diff_dicts(before, after):
    """Return {field: {"from": ..., "to": ...}} for changed keys."""
    changes = {}
    keys = set(before) | set(after)
    for key in keys:
        old = before.get(key)
        new = after.get(key)
        if old != new:
            changes[key] = {"from": old, "to": new}
    return changes


def resolve_actor_branch(actor, entity=None, explicit_branch=None):
    if explicit_branch is not None:
        return explicit_branch
    if entity is not None:
        branch = getattr(entity, "branch", None)
        if branch is not None and hasattr(branch, "pk"):
            return branch
        branch_id = getattr(entity, "branch_id", None)
        if branch_id:
            from branches.models import Branch

            return Branch.objects.filter(pk=branch_id).first()
        # Staff user: profile branch
        profile = getattr(entity, "staff_profile", None)
        if profile is not None:
            return getattr(profile, "branch", None)
    if actor is not None and getattr(actor, "is_authenticated", False):
        profile = getattr(actor, "staff_profile", None)
        if profile is not None:
            return getattr(profile, "branch", None)
    return None


def entity_label_for(instance, label_field="name"):
    if callable(label_field):
        try:
            return str(label_field(instance))[:255]
        except Exception:
            return str(instance.pk)
    if isinstance(label_field, (list, tuple)):
        parts = []
        for field in label_field:
            value = getattr(instance, field, None)
            if value:
                parts.append(str(value))
        if parts:
            return " ".join(parts)[:255]
    value = getattr(instance, label_field, None) if label_field else None
    if value:
        return str(value)[:255]
    return str(instance)[:255]


def record_audit(
    *,
    action,
    entity_type,
    entity_id,
    entity_label="",
    changes=None,
    actor=None,
    branch=None,
    request=None,
):
    """Persist an append-only audit event. Never raises to callers."""
    try:
        actor_user = None
        if actor is not None and getattr(actor, "is_authenticated", False):
            actor_user = actor

        path = ""
        if request is not None:
            path = (getattr(request, "path", "") or "")[:255]

        return AuditEvent.objects.create(
            actor=actor_user,
            branch=branch,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id),
            entity_label=(entity_label or "")[:255],
            changes=changes or {},
            request_path=path,
        )
    except Exception:
        # Audit must not break business mutations.
        return None


def record_entity_change(
    *,
    action,
    entity,
    entity_type,
    changes=None,
    actor=None,
    branch=None,
    request=None,
    label_field="name",
):
    resolved_branch = resolve_actor_branch(actor, entity=entity, explicit_branch=branch)
    return record_audit(
        action=action,
        entity_type=entity_type,
        entity_id=entity.pk,
        entity_label=entity_label_for(entity, label_field),
        changes=changes or {},
        actor=actor,
        branch=resolved_branch,
        request=request,
    )


def action_for_update(before, after):
    """Prefer deactivate when is_active flips true → false."""
    if (
        before.get("is_active") is True
        and after.get("is_active") is False
    ):
        return AuditAction.DEACTIVATE
    return AuditAction.UPDATE
