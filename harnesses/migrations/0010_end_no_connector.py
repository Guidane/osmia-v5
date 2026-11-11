"""A harness's connector no longer says which device connector it plugs into: the wire diagram does
(projects 0007 moved it there first)."""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('harnesses', '0009_wire_to_signal'),
        ('projects', '0007_ends_connectors'),
    ]

    operations = [
        migrations.RemoveField(model_name='harnessend', name='connector'),
    ]
