"""A placed harness's ends: which device connector each plugs into is the wire diagram's to say, not the harness's.
{end id: device key} becomes {end id: [device key, connector id]}, the connector taken from the end as it was."""
from django.db import migrations


def forwards(apps, schema_editor):
    Placement = apps.get_model('projects', 'Placement')
    HarnessEnd = apps.get_model('harnesses', 'HarnessEnd')
    plugged = dict(HarnessEnd.objects.values_list('pk', 'connector_id'))
    for p in Placement.objects.filter(kind='harness'):
        ends = p.ends or {}
        new = {e: (v if isinstance(v, list) else [v, plugged.get(int(e))]) for e, v in ends.items() if v}
        if new != ends:
            p.ends = new
            p.save(update_fields=['ends'])


def backwards(apps, schema_editor):
    Placement = apps.get_model('projects', 'Placement')
    for p in Placement.objects.filter(kind='harness'):
        ends = p.ends or {}
        old = {e: (v[0] if isinstance(v, list) else v) for e, v in ends.items()}
        if old != ends:
            p.ends = old
            p.save(update_fields=['ends'])


class Migration(migrations.Migration):

    dependencies = [
        ('projects', '0006_project_in_project'),
        ('harnesses', '0009_wire_to_signal'),
    ]

    operations = [migrations.RunPython(forwards, backwards)]
