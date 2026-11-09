"""Connector faces live on families: a family's pin layout (else that of a part of it) becomes its face; a part with a
layout and no family gets a family of its own ("<part> connector"). Branches named pin/male/plug have pins, those
named socket/female/receptacle sockets. Then the layout fields go."""
from django.db import migrations, models

PINS, SOCKETS = {'pin', 'pins', 'male', 'plug', 'plugs'}, {'socket', 'sockets', 'female', 'receptacle', 'recept'}


def to_faces(apps, schema_editor):
    from inventory.faces import start
    Family, Part, Branch = apps.get_model('inventory', 'Family'), apps.get_model('inventory', 'Part'), apps.get_model('inventory', 'Branch')

    def face(thing):
        return start(thing.pin_layout, thing.pin_positions or 1, thing.pin_columns)

    for family in Family.objects.exclude(pin_layout=''):
        family.face = face(family)
        family.save(update_fields=['face'])
    for part in Part.objects.exclude(pin_layout='').order_by('pk'):
        if part.family_id:
            family = Family.objects.get(pk=part.family_id)
            if not family.face:
                family.face = face(part)
                family.save(update_fields=['face'])
            continue
        name, n = f'{part.number} connector', 1
        while Family.objects.filter(name__iexact=name).exists():
            n += 1
            name = f'{part.number} connector {n}'
        part.family = Family.objects.create(name=name, face=face(part))
        part.save(update_fields=['family'])
    for branch in Branch.objects.all():
        word = branch.name.strip().lower()
        branch.contacts = 'pin' if word in PINS else 'socket' if word in SOCKETS else ''
        branch.save(update_fields=['contacts'])


class Migration(migrations.Migration):

    dependencies = [
        ('inventory', '0010_pin_layout'),
    ]

    operations = [
        migrations.AddField(
            model_name='branch',
            name='contacts',
            field=models.CharField(blank=True, choices=[('pin', 'Pins'), ('socket', 'Sockets')], max_length=6),
        ),
        migrations.AddField(
            model_name='family',
            name='face',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.RunPython(to_faces, migrations.RunPython.noop),
        migrations.RemoveField(model_name='family', name='pin_columns'),
        migrations.RemoveField(model_name='family', name='pin_layout'),
        migrations.RemoveField(model_name='family', name='pin_positions'),
        migrations.RemoveField(model_name='part', name='pin_columns'),
        migrations.RemoveField(model_name='part', name='pin_layout'),
        migrations.RemoveField(model_name='part', name='pin_positions'),
    ]
