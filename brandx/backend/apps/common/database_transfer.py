"""One-time database transfer. No SQL dumps or vendor-specific INSERT syntax.

Archives contain password/PIN hashes and customer records: treat them as secrets.
Sessions/JWT tokens are deliberately excluded; require users to log in after cutover.
"""
import hashlib
import json

from django.apps import apps
from django.core import serializers
from django.core.management.base import CommandError
from django.core.management.color import no_style
from django.db import connections, transaction

DOMAIN_APPS = {
    'authentication', 'products', 'inventory', 'vendors', 'customers',
    'sales', 'finance', 'audit', 'stores',
}
TRANSFER_BUILTINS = {'auth.group', 'admin.logentry'}
VERSION = 1


def transfer_models():
    return sorted([
        model for model in apps.get_models()
        if model._meta.managed and not model._meta.proxy
        and (model._meta.app_label in DOMAIN_APPS
             or model._meta.label_lower in TRANSFER_BUILTINS)
    ], key=lambda model: (
        {'stores.store': 0, 'auth.group': 1, 'authentication.user': 2}.get(model._meta.label_lower, 2),
        model._meta.label_lower,
    ))


def digest(records):
    canonical = json.dumps(records, sort_keys=True, ensure_ascii=False,
                           separators=(',', ':')).encode('utf-8')
    return hashlib.sha256(canonical).hexdigest()


def snapshot(using='default'):
    records = []
    for model in transfer_models():
        # Natural foreign keys preserve content-type/permission relations despite
        # different built-in primary keys created by migrate on another engine.
        records.extend(json.loads(serializers.serialize(
            'json', model._base_manager.using(using).order_by('pk'),
            use_natural_foreign_keys=True,
        )))
    return records


def manifest(records):
    result = {}
    for model in transfer_models():
        label = model._meta.label_lower
        rows = [row for row in records if row['model'] == label]
        result[label] = {'count': len(rows), 'sha256': digest(rows)}
    return result


def export_archive(using='default'):
    # Must freeze source writes operationally; atomic alone is not a substitute
    # for a maintenance window and source backup.
    with transaction.atomic(using=using):
        records = snapshot(using)
    return {
        'version': VERSION,
        'source_vendor': connections[using].vendor,
        'manifest': manifest(records),
        'records': records,
        'sha256': digest(records),
    }


def validate_archive(archive):
    if not isinstance(archive, dict) or archive.get('version') != VERSION:
        raise CommandError('Unsupported transfer archive version.')
    records = archive.get('records')
    if not isinstance(records, list) or digest(records) != archive.get('sha256'):
        raise CommandError('Transfer archive checksum mismatch.')
    expected_labels = {model._meta.label_lower for model in transfer_models()}
    identities = set()
    for record in records:
        if not isinstance(record, dict) or record.get('model') not in expected_labels:
            raise CommandError('Unknown model in transfer archive; use matching code/schema versions.')
        if not isinstance(record.get('fields'), dict) or record.get('pk') is None:
            raise CommandError('Invalid serialized record.')
        identity = (record['model'], record['pk'])
        if identity in identities:
            raise CommandError('Duplicate primary key in transfer archive.')
        identities.add(identity)
    if manifest(records) != archive.get('manifest'):
        raise CommandError('Model manifest/count/checksum mismatch; use matching schema versions.')


def import_archive(archive, using='default'):
    validate_archive(archive)
    connection = connections[using]
    models = transfer_models()
    with transaction.atomic(using=using):
        for model in models:
            if model._base_manager.using(using).exists():
                raise CommandError(
                    f'Target is not empty ({model._meta.label_lower}); refusing to overwrite data.'
                )
        # Django-created permission/content-type tables stay in place. Every
        # transferred model must be empty, including users and audit records.
        with connection.constraint_checks_disabled():
            deferred = []
            for obj in serializers.deserialize(
                'json', json.dumps(archive['records']), using=using,
                handle_forward_references=True,
            ):
                # Save as we deserialize so later natural user/group relations
                # resolve against already imported rows, not an empty target.
                obj.save(using=using)
                if obj.deferred_fields:
                    deferred.append(obj)
            for obj in deferred:
                obj.save_deferred_fields(using=using)
        connection.check_constraints()
        with connection.cursor() as cursor:
            for sql in connection.ops.sequence_reset_sql(no_style(), models):
                cursor.execute(sql)
        restored = snapshot(using)
        if digest(restored) != archive['sha256'] or manifest(restored) != archive['manifest']:
            raise CommandError('Restored values/relationships differ from source; import rolled back.')
    return archive['manifest']
