"""Small helper so callers never forget the username snapshot."""
from .models import AuditLog


def log_action(action, *, user=None, entity='', entity_id='', details=None, store=None):
    """
    Record an audit entry.

    NEVER pass secrets (PINs, passwords, tokens) inside ``details``.
    """
    try:
        return AuditLog.objects.create(
            store=store or getattr(user, 'store', None),
            user=user if getattr(user, 'pk', None) else None,
            username=getattr(user, 'username', '') or '',
            action=action,
            entity=entity,
            entity_id=str(entity_id) if entity_id != '' else '',
            details=details or {},
        )
    except Exception:  # noqa: BLE001 - auditing must never break a business flow
        return None
