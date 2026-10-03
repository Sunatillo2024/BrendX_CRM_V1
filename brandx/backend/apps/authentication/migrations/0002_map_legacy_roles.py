"""
Data migration: map the old role values onto the new role model.

    admin -> owner
    guest -> cashier
    manager -> manager

Safe to run on a fresh database (it simply matches no rows).
"""
from django.db import migrations

LEGACY_TO_NEW = {'admin': 'owner', 'guest': 'cashier'}


def forwards(apps, schema_editor):
    User = apps.get_model('authentication', 'User')
    for old, new in LEGACY_TO_NEW.items():
        User.objects.filter(role=old).update(role=new)


def backwards(apps, schema_editor):
    User = apps.get_model('authentication', 'User')
    for old, new in LEGACY_TO_NEW.items():
        User.objects.filter(role=new).update(role=old)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
