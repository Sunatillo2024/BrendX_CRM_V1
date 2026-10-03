"""Store-level service functions (DRF-free)."""
import uuid

from apps.authentication.models import User


def make_owner(store, name, pin, language):
    """Create the first owner account for a newly provisioned store."""
    user = User(username=f'{store.code.lower()}-owner-{uuid.uuid4().hex[:8]}',
                first_name=name, role='owner', store=store, language=language)
    user.set_unusable_password()
    user.set_pin(pin)
    user.save()
    return user
