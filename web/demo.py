"""Demo data, to switch on and off (Demo data, for administrators; ``manage.py demo [--off]``).

Switched on, example data is made alongside what is there already: departments, parts and assets with their categories'
attributes (an auto ID too), parts in locations, budgets, an order on its way and a late one, devices with their
connectors and pins (a bought power supply among them) and the assets that are them, and a project with harnesses and a
tree of configurations. Every row it made is remembered (DemoRecord); switched off, those rows go, and nothing else."""
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Max

from accounts.models import Department
from budgets.models import Budget, Cost
from devices.models import Connector, Device, Pin
from harnesses.models import Harness, HarnessEnd, HarnessItem, Wire
from inventory import stock
from inventory.models import Attribute, Category, Location, Part, PartLink, PartValue, Vendor
from orders import service
from orders.models import Order
from projects import configs
from projects.models import Configuration, Project
from assets.models import Asset, PartAsset
from inventory.attributes import number_up
from web import versions

PARTS = [  # number, description, category, unit, vendor, price, minimum, on hand
    ('DSUB-9-PLUG', 'D-sub 9 plug housing, crimp', 'D-sub', 'pcs', 'Acme Connectors', '2.40', 10, 6),
    ('DSUB-9-RECEPT', 'D-sub 9 receptacle, panel mount', 'D-sub', 'pcs', 'Acme Connectors', '3.10', 5, 8),
    ('DSUB-CONTACT-M', 'D-sub crimp contact, male, 20-24 AWG', 'Contacts', 'pcs', 'Acme Connectors', '0.18', 100, 240),
    ('M12-5-F', 'M12 5-pin cable socket, female', 'M12', 'pcs', 'Acme Connectors', '6.80', 4, 2),
    ('WIRE-22-RED', 'Hook-up wire 22 AWG red', 'Wire', 'm', 'Cable World', '0.12', 50, 80),
    ('WIRE-22-BLK', 'Hook-up wire 22 AWG black', 'Wire', 'm', 'Cable World', '0.12', 50, 35),
    ('WIRE-24-TP', 'Twisted pair 24 AWG, shielded', 'Wire', 'm', 'Cable World', '0.85', 20, 25),
    ('TIE-100', 'Cable tie 100 x 2.5 mm', 'Accessories', 'pcs', 'Cable World', '0.02', 200, 500),
]
ATTRIBUTES = {   # category: [(name, kind, unit, choices)]
    'Connectors': [('Positions', 'integer', '', ''), ('Gender', 'choice', '', 'male\nfemale')],
    'D-sub': [('Mounting', 'choice', '', 'cable\npanel'), ('Shielded', 'yesno', '', '')],
    'Wire': [('Gauge', 'integer', 'AWG', ''), ('Colour', 'text', '', ''), ('Max. temperature', 'decimal', '°C', '')],
}
VALUES = {   # part: {attribute: value}
    'DSUB-9-PLUG': {'Positions': '9', 'Gender': 'male', 'Mounting': 'cable', 'Shielded': 'No'},
    'DSUB-9-RECEPT': {'Positions': '9', 'Gender': 'female', 'Mounting': 'panel', 'Shielded': 'Yes'},
    'DSUB-CONTACT-M': {'Gender': 'male'},
    'M12-5-F': {'Positions': '5', 'Gender': 'female'},
    'WIRE-22-RED': {'Gauge': '22', 'Colour': 'red', 'Max. temperature': '105'},
    'WIRE-22-BLK': {'Gauge': '22', 'Colour': 'black', 'Max. temperature': '105'},
    'WIRE-24-TP': {'Gauge': '24', 'Colour': 'white/green', 'Max. temperature': '80'},
}
PINS = {   # device: [(connector, name, part, [(pin, signal)])]
    'CTRL-100': [('J1', 'Bus', 'DSUB-9-RECEPT', [('1', '+24 V'), ('2', '0 V'), ('3', 'Enable'), ('6', 'CAN H'), ('7', 'CAN L'), ('9', 'CAN GND')]),
                 ('J2', 'Sensor', 'M12-5-F', [('1', '+24 V'), ('2', 'Signal'), ('3', '0 V')])],
    'LOAD-200': [('J1', 'Bus in', 'DSUB-9-RECEPT', [('1', '+24 V'), ('3', '0 V'), ('5', 'Enable'), ('2', 'CAN H'), ('7', 'CAN L'), ('8', 'Shield')]),
                 ('J2', 'Bus out', 'DSUB-9-RECEPT', [('1', '+24 V'), ('3', '0 V'), ('2', 'CAN H'), ('7', 'CAN L')])],
}


def _make(user):
    """Everything of the demo, made in Osmia as it is."""
    engineering = Department.objects.create(name='Engineering', manager=user)
    Department.objects.create(name='Test', parent=engineering)
    Department.objects.create(name='Operations')
    if user is not None and user.department_id is None:
        get_user_model().objects.filter(pk=user.pk).update(department=engineering)
    store = Location.objects.create(name='Main store')
    shelves = [Location.objects.create(name=f'Shelf {n}', parent=store) for n in (1, 2)]
    Location.objects.create(name='Workbench')
    vendors = {name: Vendor.objects.create(name=name, email=f'sales@{name.split()[0].lower()}.example') for name in ('Acme Connectors', 'Cable World')}
    connectors = Category.objects.create(name='Connectors')
    categories = {'D-sub': Category.objects.create(name='D-sub', parent=connectors), 'M12': Category.objects.create(name='M12', parent=connectors),
                  'Contacts': Category.objects.create(name='Contacts', parent=connectors), 'Wire': Category.objects.create(name='Wire'),
                  'Accessories': Category.objects.create(name='Accessories')}
    attributes = {}
    for category, items in ATTRIBUTES.items():
        for position, (name, kind, unit, choices) in enumerate(items):
            attributes[name] = Attribute.objects.create(category=categories.get(category) or connectors, name=name, kind=kind,
                                                        unit=unit, choices=choices, position=position)
    parts = {}
    for i, (number, description, category, unit, vendor, price, minimum, have) in enumerate(PARTS):
        parts[number] = Part.objects.create(number=number, description=description, category=categories[category], unit=unit,
                                            vendor=vendors[vendor], price=Decimal(price), minimum=minimum)
        stock.add(parts[number], have, shelves[i % 2], user, 'demo')
        for name, raw in VALUES.get(number, {}).items():
            value, figure = attributes[name].clean_value(raw)
            PartValue.objects.create(part=parts[number], attribute=attributes[name], value=value, number=figure)
    workshop = Category.objects.create(name='Workshop')
    crimpers = Category.objects.create(name='Crimp tools', parent=workshop)
    lab = Category.objects.create(name='Lab equipment', parent=workshop)
    Attribute.objects.create(category=crimpers, name='Wire size', kind='text', help='e.g. 20-24 AWG')
    Attribute.objects.create(category=lab, name='Output', kind='text', help='e.g. 0-30 V, 5 A')
    crimp = Asset.objects.create(number='T-001', name='D-sub crimp tool', kind='tool', category=crimpers, manufacturer='TE',
                                 location=store, keeper=user, calibration_months=12, calibrated_on=date.today() - timedelta(days=355))
    Asset.objects.create(number='T-002', name='Contact extraction tool', kind='tool', category=crimpers, location=store)
    Asset.objects.create(number='M-001', name='Multimeter', kind='measuring', category=lab, manufacturer='Fluke', location=store,
                         keeper=user, calibration_months=12, calibrated_on=date.today() - timedelta(days=100))
    asset_id = Attribute.objects.create(category=workshop, name='Asset ID', kind='auto', prefix='WS-', digits=4)
    fits = Attribute.objects.create(category=categories['Contacts'], name='Fits into', kind='interacts', target=categories['D-sub'],
                                    reverse_name='Takes contacts')
    crimped = Attribute.objects.create(category=categories['Contacts'], name='Crimped with', kind='link', links_to='asset',
                                       reverse_name='Crimps')
    PartLink.objects.create(part=parts['DSUB-CONTACT-M'], attribute=fits, target=parts['DSUB-9-PLUG'])
    PartAsset.objects.create(part=parts['DSUB-CONTACT-M'], attribute=crimped, asset=crimp)
    year = Budget.objects.create(number='FY26', name='2026', amount=50000, owner=user)
    eng_budget = Budget.objects.create(number='FY26-ENG', name='Engineering', parent=year, amount=20000, owner=user, department=engineering)
    Budget.objects.create(number='FY26-OPS', name='Operations', parent=year, amount=15000, owner=user)
    Cost.objects.create(budget=eng_budget, spent_on=date.today(), description='EMC test lab, one day', amount=1800, created_by=user)
    late = service.reorder(parts['M12-5-F'], user).order
    late.budget = eng_budget
    late.save()
    service.place(late, user, date.today() - timedelta(days=3))
    coming = service.reorder(parts['WIRE-22-BLK'], user).order
    coming.budget = eng_budget
    coming.save()
    service.place(coming, user, date.today() + timedelta(days=4))
    Order.objects.create(kind=Order.Kind.REQUEST, budget=eng_budget, created_by=user,
                         request='Heat shrink, 6 mm, a spool of black and one of red, for the load board harnesses.')

    devices = {}
    for number, name, colour in (('CTRL-100', 'Rack controller', '#3b7dd8'), ('LOAD-200', 'Load board', '#c2410c')):
        devices[number] = Device.objects.create(number=number, name=name, colour=colour, manufacturer='In house')
        for position, (designator, title, part, pins) in enumerate(PINS[number]):
            c = Connector.objects.create(device=devices[number], designator=designator, name=title, part=parts[part], position=position)
            Pin.objects.bulk_create(Pin(connector=c, number=p, signal=s) for p, s in pins)
        versions.save(devices[number], user, 'first')
    for n in (1, 2, 3):
        Asset.objects.create(number=f'LOAD-200-{n:03d}', name='Load board', kind='device', device=devices['LOAD-200'], version=1,
                             serial=f'LB-{n:04d}', status='in_use' if n < 3 else 'available', location=store)
    psu = Device.objects.create(number='PSU-24', name='Lab power supply 24 V', origin='external', manufacturer='Delta', model='E 030-5',
                                colour='#4b5563')
    out = Connector.objects.create(device=psu, designator='OUT', name='DC out')
    Pin.objects.bulk_create([Pin(connector=out, number='1', signal='+24 V'), Pin(connector=out, number='2', signal='0 V')])
    versions.save(psu, user, 'as bought')
    Asset.objects.create(number='PSU-01', name='Lab power supply 24 V', kind='lab', category=lab, device=psu, version=1,
                         manufacturer='Delta', model='E 030-5', serial='DE-77812', location=store, keeper=user)

    project = Project.objects.create(code='BR-1', name='Burn-in rack', owner=user, department=engineering,
                                     description='The burn-in rack: a controller and its load boards.')
    Budget.objects.create(number='FY26-ENG-BR', name='Burn-in rack', parent=eng_budget, project=project, amount=8000, owner=user)
    bus = _harness(project, 'Controller to load board', [('P1', 'DSUB-9-PLUG', devices['CTRL-100'], 'J1'), ('P2', 'DSUB-9-PLUG', devices['LOAD-200'], 'J1')],
                       [('1', '1', 'red', 'WIRE-22-RED', '', 'Twisted'), ('2', '3', 'black', 'WIRE-22-BLK', '', 'Twisted'),
                        ('3', '5', 'blue', '', '', 'Straight'), ('6', '2', 'white', 'WIRE-24-TP', 'P2', 'Shielded twisted'),
                        ('7', '7', 'green', 'WIRE-24-TP', 'P2', 'Shielded twisted')], parts, user)
    link = _harness(project, 'Load board link', [('P1', 'DSUB-9-PLUG', devices['LOAD-200'], 'J2'), ('P2', 'DSUB-9-PLUG', devices['LOAD-200'], 'J1')],
                        [('1', '1', 'red', 'WIRE-22-RED', '', 'Straight'), ('3', '3', 'black', 'WIRE-22-BLK', '', 'Straight'),
                         ('2', '2', 'white', 'WIRE-24-TP', 'P1', 'Shielded twisted'), ('7', '7', 'green', 'WIRE-24-TP', 'P1', 'Shielded twisted')], parts, user)
    base = Configuration.objects.create(project=project, name='Base', description='One load board.')
    ctrl = configs.place(base, kind='device', device_id=devices['CTRL-100'].pk, label='Controller', x=40, y=60)
    first = configs.place(base, kind='device', device_id=devices['LOAD-200'].pk, label='Load board 1', x=420, y=40)
    configs.place(base, kind='harness', harness_id=bus.pk, ends={str(e.pk): k for e, k in zip(bus.ends.all(), (ctrl, first))})
    two = Configuration.objects.create(project=project, name='Two load boards', parent=base)
    second = configs.place(two, kind='device', device_id=devices['LOAD-200'].pk, label='Load board 2', x=420, y=260)
    configs.place(two, kind='harness', harness_id=link.pk, ends={str(e.pk): k for e, k in zip(link.ends.all(), (first, second))})
    Configuration.objects.create(project=project, name='Test rig', parent=two, description='Two load boards, on the bench.')
    number_up(asset_id, list(Asset.objects.filter(category__in=workshop.below()).order_by('pk')))

def _harness(project, name, ends, wires, parts, user):
    h = Harness.objects.create(project=project, name=name, status='released')
    made = []
    for position, (designator, part, device, connector) in enumerate(ends):
        made.append(HarnessEnd.objects.create(harness=h, designator=designator, part=parts[part], position=position,
                                              connector=device.connectors.get(designator=connector)))
    for a, b, colour, part, wire_set, set_type in wires:
        signal = made[0].connector.pins.get(number=a).signal
        Wire.objects.create(harness=h, from_end=made[0], from_pin=a, to_end=made[1], to_pin=b, signal=signal, colour=colour,
                            gauge='22 AWG', length=Decimal(450), part=parts[part] if part else None, wire_set=wire_set, set_type=set_type)
    HarnessItem.objects.create(harness=h, part=parts['DSUB-CONTACT-M'], quantity=2 * len(wires))
    HarnessItem.objects.create(harness=h, part=parts['TIE-100'], quantity=4)
    versions.save(h, user, 'first')
    return h


# -- switching it on and off ----------------------------------------------------------------------------------

def _models():
    from django.apps import apps
    return [m for m in apps.get_models() if m._meta.app_label not in ('admin', 'auth', 'contenttypes', 'sessions')
            and m._meta.label != 'web.DemoRecord']


def is_on():
    from .models import DemoRecord
    return DemoRecord.objects.exists()


@transaction.atomic
def switch_on(user):
    """Make the demo data, and remember every row it made (all that is new in each table) to take away later."""
    from .models import DemoRecord
    if is_on():
        raise ValidationError('The demo data is on already.')
    before = {m: m.objects.aggregate(n=Max('pk'))['n'] or 0 for m in _models()}
    try:
        with transaction.atomic():
            _make(user)
    except IntegrityError:
        raise ValidationError('The demo data can\'t go in: something real already has one of its names or numbers '
                              '(e.g. a part DSUB-9-PLUG or a vendor Acme Connectors).')
    made = []
    for model, last in before.items():
        made += [DemoRecord(model=model._meta.label, object_id=pk)
                 for pk in model.objects.filter(pk__gt=last).values_list('pk', flat=True)]
    DemoRecord.objects.bulk_create(made)
    return len(made)


@transaction.atomic
def switch_off():
    """Take away every row the demo made. What real data uses now (a real order line of a demo part) stays: returns
    those, as text."""
    from django.apps import apps
    from django.db.models import ProtectedError, RestrictedError

    from .models import DemoRecord
    left = {}
    for record in DemoRecord.objects.all():
        left.setdefault(record.model, set()).add(record.object_id)
    for _ in range(20):   # deleting a row can free another (an order line, then its part)
        progress = False
        for label, ids in list(left.items()):
            model = apps.get_model(label)
            for pk in list(ids):
                obj = model.objects.filter(pk=pk).first()
                if obj is not None:
                    try:
                        with transaction.atomic():
                            obj.delete()
                    except (ProtectedError, RestrictedError):
                        continue
                ids.discard(pk)
                progress = True
            if not ids:
                del left[label]
        if not left or not progress:
            break
    kept = [str(apps.get_model(label).objects.get(pk=pk)) for label, ids in left.items() for pk in ids
            if apps.get_model(label).objects.filter(pk=pk).exists()]
    DemoRecord.objects.all().delete()
    return kept
