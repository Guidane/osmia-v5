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
from inventory.models import Attribute, Branch, Category, Family, Location, Part, PartLink, PartValue, Vendor, part_or_family
from orders import service
from orders.models import Order
from projects import configs
from projects.models import Configuration, Project
from assets.models import Asset, PartAsset
from inventory.attributes import number_up
from web import versions

PARTS = [  # number, description, category, unit, vendor, price, minimum, on hand
    ('DSUB-9-PLUG', 'D-sub 9 plug housing, crimp', 'D-sub', 'pcs', 'Acme Connectors', '2.40', 10, 6),
    ('DSUB-9-PLUG-B', 'D-sub 9 plug housing, crimp (other make)', 'D-sub', 'pcs', 'Acme Connectors', '2.95', 0, 4),
    ('DSUB-9-RECEPT', 'D-sub 9 receptacle, panel mount', 'D-sub', 'pcs', 'Acme Connectors', '3.10', 5, 8),
    ('DSUB-25-PLUG', 'D-sub 25 plug housing, crimp', 'D-sub', 'pcs', 'Acme Connectors', '4.20', 4, 6),
    ('DSUB-25-RECEPT', 'D-sub 25 receptacle, panel mount', 'D-sub', 'pcs', 'Acme Connectors', '5.10', 2, 4),
    ('DSUB-CONTACT-M', 'D-sub crimp contact, pin, 20-24 AWG', 'Contacts', 'pcs', 'Acme Connectors', '0.18', 100, 240),
    ('M12-5-F', 'M12 5-pin cable socket', 'M12', 'pcs', 'Acme Connectors', '6.80', 4, 2),
    ('WIRE-22-RED', 'Hook-up wire 22 AWG red', 'Wire', 'm', 'Cable World', '0.12', 50, 80),
    ('WIRE-22-BLK', 'Hook-up wire 22 AWG black', 'Wire', 'm', 'Cable World', '0.12', 50, 35),
    ('WIRE-24-TP', 'Twisted pair 24 AWG, shielded', 'Wire', 'm', 'Cable World', '0.85', 20, 25),
    ('TIE-100', 'Cable tie 100 x 2.5 mm', 'Accessories', 'pcs', 'Cable World', '0.02', 200, 500),
]
ATTRIBUTES = {   # category: [(name, kind, unit, choices)]
    'Connectors': [('Positions', 'integer', '', ''), ('Contact type', 'choice', '', 'pin\nsocket')],
    'D-sub': [('Mounting', 'choice', '', 'cable\npanel'), ('Shielded', 'yesno', '', '')],
    'Wire': [('Gauge', 'integer', 'AWG', ''), ('Colour', 'text', '', ''), ('Max. temperature', 'decimal', '°C', '')],
}
VALUES = {   # part: {attribute: value}
    'DSUB-9-PLUG': {'Positions': '9', 'Contact type': 'pin', 'Mounting': 'cable', 'Shielded': 'No'},
    'DSUB-9-RECEPT': {'Positions': '9', 'Contact type': 'socket', 'Mounting': 'panel', 'Shielded': 'Yes'},
    'DSUB-25-PLUG': {'Positions': '25', 'Contact type': 'pin', 'Mounting': 'cable', 'Shielded': 'Yes'},
    'DSUB-25-RECEPT': {'Positions': '25', 'Contact type': 'socket', 'Mounting': 'panel', 'Shielded': 'Yes'},
    'DSUB-CONTACT-M': {'Contact type': 'pin'},
    'M12-5-F': {'Positions': '5', 'Contact type': 'socket'},
    'WIRE-22-RED': {'Gauge': '22', 'Colour': 'red', 'Max. temperature': '105'},
    'WIRE-22-BLK': {'Gauge': '22', 'Colour': 'black', 'Max. temperature': '105'},
    'WIRE-24-TP': {'Gauge': '24', 'Colour': 'white/green', 'Max. temperature': '80'},
}
SETS = {'+24 V': ('PWR', 'Twisted'), '0 V': ('PWR', 'Twisted'), 'CAN H': ('CAN', 'Shielded twisted'),
        'CAN L': ('CAN', 'Shielded twisted')}   # signal: the set its pins are in
PINS = {   # device: [(connector, name, part, [(pin, signal)])]
    'CTRL-100': [('J1', 'Bus', 'DSUB-9-RECEPT', [('1', '+24 V'), ('2', '0 V'), ('3', 'Enable'), ('6', 'CAN H'), ('7', 'CAN L'), ('9', 'Shield')]),
                 ('J2', 'Sensor', 'M12-5-F', [('1', '+24 V'), ('2', 'Signal'), ('3', '0 V')])],
    'LOAD-200': [('J1', 'Bus in', 'D-sub 9 / socket', [('1', '+24 V'), ('3', '0 V'), ('5', 'Enable'), ('2', 'CAN H'), ('7', 'CAN L'), ('8', 'Shield')]),
                 ('J2', 'Bus out', 'D-sub 9 / socket', [('1', '+24 V'), ('3', '0 V'), ('2', 'CAN H'), ('7', 'CAN L')])],
    'HUB-500': [('J1', 'Outputs 1-3', 'D-sub 25 / socket', [('1', '+24 V'), ('14', '0 V'), ('2', 'Data +'), ('15', 'Data -'), ('3', 'Shield'), ('4', '+24 V'), ('17', '0 V'), ('5', 'Data +'), ('18', 'Data -'), ('6', 'Shield'), ('7', '+24 V'), ('20', '0 V'), ('8', 'Data +'), ('21', 'Data -'), ('9', 'Shield')]),
                ('J2', 'Outputs 4-5', 'D-sub 25 / socket', [('1', 'Data +'), ('14', 'Data -'), ('2', 'Shield'), ('4', '+24 V'), ('17', '0 V'), ('5', 'Data +'), ('18', 'Data -'), ('6', 'Data GND'), ('7', 'Shield')])],
    'SENS-10': [('J1', 'Power and data', 'D-sub 9 / socket', [('1', '+24 V'), ('6', '0 V'), ('2', 'Data +'), ('7', 'Data -'), ('3', 'Data GND'), ('5', 'Shield')])],
    'FAN-20': [('J1', 'Power and data', 'D-sub 9 / socket', [('1', '+24 V'), ('6', '0 V'), ('2', 'Data +'), ('7', 'Data -'), ('3', 'Data GND'), ('5', 'Shield')])],
    'LED-30': [('J1', 'Power and data', 'D-sub 9 / socket', [('1', '+24 V'), ('6', '0 V'), ('2', 'Data +'), ('7', 'Data -'), ('3', 'Data GND'), ('5', 'Shield')])],
    'MOT-40': [('J1', 'Power and data', 'D-sub 9 / socket', [('1', '+24 V'), ('6', '0 V'), ('2', 'Data +'), ('7', 'Data -'), ('3', 'Data GND'), ('5', 'Shield')])],
    'CAM-50': [('J1', 'Power and data', 'D-sub 9 / socket', [('1', '+24 V'), ('6', '0 V'), ('2', 'Data +'), ('7', 'Data -'), ('3', 'Data GND'), ('5', 'Shield')])],
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
    Part.objects.filter(pk=parts['DSUB-9-PLUG'].pk).update(notes='Use the gold plated contacts with it.\nKeep two spare in the lab.')
    vendors['Cable World'].notes = 'Free delivery above 200. Ask for Jan.'
    vendors['Cable World'].save()
    from inventory.faces import start
    dsub9 = Family.objects.create(name='D-sub 9', face=start('staggered', 9))
    pin, socket = Branch.objects.create(family=dsub9, name='pin', contacts='pin'), Branch.objects.create(family=dsub9, name='socket', contacts='socket')
    m12 = Family.objects.create(name='M12 5-pin', face=start('circle', 5))
    Branch.objects.create(family=m12, name='pin', contacts='pin')
    Part.objects.filter(number='M12-5-F').update(family=m12, branch=Branch.objects.create(family=m12, name='socket', contacts='socket'))
    dsub25 = Family.objects.create(name='D-sub 25', face=start('staggered', 25))
    Part.objects.filter(number='DSUB-25-PLUG').update(family=dsub25, branch=Branch.objects.create(family=dsub25, name='pin', contacts='pin'))
    Part.objects.filter(number='DSUB-25-RECEPT').update(family=dsub25, branch=Branch.objects.create(family=dsub25, name='socket', contacts='socket'))
    Part.objects.filter(number__in=['DSUB-9-PLUG', 'DSUB-9-PLUG-B']).update(family=dsub9, branch=pin)
    Part.objects.filter(number='DSUB-9-RECEPT').update(family=dsub9, branch=socket)
    workshop = Category.objects.create(name='Workshop', kind='assets')
    crimpers = Category.objects.create(name='Crimp tools', parent=workshop, kind='assets')
    lab = Category.objects.create(name='Lab equipment', parent=workshop, kind='assets')
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
    late.budget, late.notes = eng_budget, 'Acme says it ships next week.'
    late.save()
    service.place(late, user, date.today() - timedelta(days=3))
    coming = service.reorder(parts['WIRE-22-BLK'], user).order
    coming.budget = eng_budget
    coming.save()
    service.place(coming, user, date.today() + timedelta(days=4))
    sam = get_user_model().objects.create_user('demo.sam', first_name='Sam', last_name='Lee', department=engineering.children.get())
    sam.set_unusable_password()
    sam.save()
    asked = Order.objects.create(kind=Order.Kind.REQUEST, budget=eng_budget, created_by=sam, ask=user,
                                 request='200 D-sub crimp contacts (pins) for the next load boards. Needed by Friday.')
    service.ask(asked)
    mine = Order.objects.create(kind=Order.Kind.REQUEST, budget=eng_budget, created_by=user, vendor=vendors['Cable World'],
                                request='A bag of small cable ties (100 mm) for the load board harnesses.')
    mine.lines.create(part=parts['TIE-100'], quantity=100, price=parts['TIE-100'].price)
    service.place(mine, user, date.today() + timedelta(days=6))

    devices = {}
    for number, name, colour in (('CTRL-100', 'Rack controller', '#3b7dd8'), ('LOAD-200', 'Load board', '#c2410c'),
                                 ('HUB-500', 'Rack hub', '#334155'),
                                 ('SENS-10', 'Temperature sensor', '#0f766e'),
                                 ('FAN-20', 'Fan controller', '#7c3aed'),
                                 ('LED-30', 'Light bar', '#ca8a04'),
                                 ('MOT-40', 'Motor driver', '#be123c'),
                                 ('CAM-50', 'Camera', '#0369a1')):
        devices[number] = Device.objects.create(number=number, name=name, colour=colour, manufacturer='In house')
        for position, (designator, title, part, pins) in enumerate(PINS[number]):
            c = Connector(device=devices[number], designator=designator, name=title, position=position)
            c.used = part_or_family(part)   # a part, or a family's branch
            c.save()
            Pin.objects.bulk_create(Pin(connector=c, number=p, signal=s, wire_set=SETS.get(s, ('', ''))[0],
                                        set_type=SETS.get(s, ('', 'Straight'))[1]) for p, s in pins)
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
                       [('1', '1', 'red', 'WIRE-22-RED', 'PWR', 'Twisted'), ('2', '3', 'black', 'WIRE-22-BLK', 'PWR', 'Twisted'),
                        ('3', '5', 'blue', '', '', 'Straight'), ('6', '2', 'white', 'WIRE-24-TP', 'CAN', 'Shielded twisted'),
                        ('7', '7', 'green', 'WIRE-24-TP', 'CAN', 'Shielded twisted'), ('9', '8', 'grey', '', 'CAN', 'Shield')], parts, user)
    link = _harness(project, 'Load board link', [('P1', pin.number, devices['LOAD-200'], 'J2'), ('P2', pin.number, devices['LOAD-200'], 'J1')],
                        [('1', '1', 'red', 'WIRE-22-RED', '', 'Straight'), ('3', '3', 'black', 'WIRE-22-BLK', '', 'Straight'),
                         ('2', '2', 'white', 'WIRE-24-TP', 'P1', 'Shielded twisted'), ('7', '7', 'green', 'WIRE-24-TP', 'P1', 'Shielded twisted')], parts, user)
    # the rack hub's two D-sub 25s to five devices' D-sub 9s, each with power and shielded data: every kind of set, a
    # shielded twist of three, and splices (the motor driver's power taken off the sensor's)
    hub = devices['HUB-500']
    ends = [('P1', 'D-sub 25 / pin', hub, 'J1'), ('P2', 'D-sub 25 / pin', hub, 'J2')]
    ends += [(f'P{i}', pin.number, devices[n], 'J1') for i, n in enumerate(['SENS-10', 'FAN-20', 'LED-30', 'MOT-40', 'CAM-50'], 3)]
    loom = _harness(project, 'Rack loom', ends, [
        ('P1:1', 'P3:1', 'red', 'WIRE-22-RED', 'PWR1', 'Twisted'), ('P1:14', 'P3:6', 'black', 'WIRE-22-BLK', 'PWR1', 'Twisted'),
        ('P1:2', 'P3:2', 'white', 'WIRE-24-TP', 'DATA1', 'Shielded twisted'), ('P1:15', 'P3:7', 'brown', 'WIRE-24-TP', 'DATA1', 'Shielded twisted'),
        ('P1:3', 'P3:5', 'grey', '', 'DATA1', 'Shield'),
        ('P1:4', 'P4:1', 'red', 'WIRE-22-RED', 'PWR2', 'Straight'), ('P1:17', 'P4:6', 'black', 'WIRE-22-BLK', 'PWR2', 'Straight'),
        ('P1:5', 'P4:2', 'white', '', 'DATA2', 'Shielded'), ('P1:18', 'P4:7', 'brown', '', 'DATA2', 'Shielded'),
        ('P1:6', 'P4:5', 'grey', '', 'DATA2', 'Shield'),
        ('P1:7', 'P5:1', 'red', 'WIRE-22-RED', '', 'Straight'), ('P1:20', 'P5:6', 'black', 'WIRE-22-BLK', '', 'Straight'),
        ('P1:8', 'P5:2', 'white', 'WIRE-24-TP', 'DATA3', 'Shielded twisted'), ('P1:21', 'P5:7', 'brown', 'WIRE-24-TP', 'DATA3', 'Shielded twisted'),
        ('P1:9', 'P5:5', 'grey', '', 'DATA3', 'Shield'),
        ('P1:1', 'P6:1', 'red', 'WIRE-22-RED', 'PWR4', 'Twisted'), ('P1:14', 'P6:6', 'black', 'WIRE-22-BLK', 'PWR4', 'Twisted'),   # spliced
        ('P2:1', 'P6:2', 'white', 'WIRE-24-TP', 'DATA4', 'Shielded twisted'), ('P2:14', 'P6:7', 'brown', 'WIRE-24-TP', 'DATA4', 'Shielded twisted'),
        ('P2:2', 'P6:5', 'grey', '', 'DATA4', 'Shield'),
        ('P2:4', 'P7:1', 'red', 'WIRE-22-RED', 'PWR5', 'Twisted'), ('P2:17', 'P7:6', 'black', 'WIRE-22-BLK', 'PWR5', 'Twisted'),
        ('P2:5', 'P7:2', 'white', '', 'DATA5', 'Shielded twisted'), ('P2:18', 'P7:7', 'brown', '', 'DATA5', 'Shielded twisted'),
        ('P2:6', 'P7:3', 'green', '', 'DATA5', 'Shielded twisted'),                                                        # a twist of three
        ('P2:7', 'P7:5', 'grey', '', 'DATA5', 'Shield')], parts, user)
    Harness.objects.filter(pk=bus.pk).update(notes='Keep it under 50 cm: the rack is tight behind the controller.')
    base = Configuration.objects.create(project=project, name='Base', description='One load board.')
    ctrl = configs.place(base, kind='device', device_id=devices['CTRL-100'].pk, label='Controller', x=40, y=60)
    first = configs.place(base, kind='device', device_id=devices['LOAD-200'].pk, label='Load board 1', x=420, y=40)
    configs.place(base, kind='harness', harness_id=bus.pk, ends={str(e.pk): k for e, k in zip(bus.ends.all(), (ctrl, first))})
    two = Configuration.objects.create(project=project, name='Two load boards', parent=base)
    second = configs.place(two, kind='device', device_id=devices['LOAD-200'].pk, label='Load board 2', x=420, y=260)
    configs.place(two, kind='harness', harness_id=link.pk, ends={str(e.pk): k for e, k in zip(link.ends.all(), (first, second))})
    Configuration.objects.create(project=project, name='Test rig', parent=two, description='Two load boards, on the bench.')
    rack = Configuration.objects.create(project=project, name='Rack hub', description='The rack hub and the five devices it feeds.')
    at = {'HUB-500': configs.place(rack, kind='device', device_id=hub.pk, label='Rack hub', x=40, y=250)}
    for i, n in enumerate(['SENS-10', 'FAN-20', 'LED-30', 'MOT-40', 'CAM-50']):
        at[n] = configs.place(rack, kind='device', device_id=devices[n].pk, label=devices[n].name, x=840, y=20 + i * 120)
    configs.place(rack, kind='harness', harness_id=loom.pk,
                  ends={str(e.pk): at[e.connector.device.number] for e in loom.ends.select_related('connector__device')})
    configs.ask_harness(two, ctrl, second, 'The sensor cable from the controller to load board 2, about 2 m, shielded.', user, sam)
    number_up(asset_id, list(Asset.objects.filter(category__in=workshop.below()).order_by('pk')))
    _work(user, engineering, project, devices, psu, parts, [late, coming, asked, mine])


def _picture(shape, colour, holes=0):
    """A small drawing of something (PNG): a D-sub, a round connector, a coil of wire, a box, a tool, a rack."""
    from io import BytesIO

    from PIL import Image, ImageDraw
    img = Image.new('RGB', (240, 180), '#f8fafc')
    d = ImageDraw.Draw(img)
    if shape == 'dsub':
        d.polygon([(30, 50), (210, 50), (195, 130), (45, 130)], fill=colour, outline='#334155', width=4)
        top, low = (holes + 1) // 2, holes // 2
        for i in range(top):
            x = 60 + i * (120 / max(top - 1, 1))
            d.ellipse([x - 7, 68, x + 7, 82], fill='#f8fafc', outline='#334155', width=2)
        for i in range(low):
            x = 60 + (i + 0.5) * (120 / max(top - 1, 1))
            d.ellipse([x - 7, 98, x + 7, 112], fill='#f8fafc', outline='#334155', width=2)
    elif shape == 'round':
        d.ellipse([60, 30, 180, 150], fill=colour, outline='#334155', width=5)
        for x, y in ((120, 60), (150, 90), (120, 120), (90, 90), (120, 90)):
            d.ellipse([x - 8, y - 8, x + 8, y + 8], fill='#f8fafc', outline='#334155', width=2)
    elif shape == 'wire':
        for i in range(7):
            d.ellipse([40 + i * 14, 40, 120 + i * 14, 140], outline=colour, width=6)
    elif shape == 'tool':
        d.rounded_rectangle([30, 75, 150, 105], 12, fill=colour, outline='#334155', width=3)
        d.polygon([(150, 80), (215, 55), (215, 125), (150, 100)], fill='#94a3b8', outline='#334155')
    elif shape == 'rack':
        d.rounded_rectangle([50, 15, 190, 165], 8, fill='#e2e8f0', outline='#334155', width=4)
        for i in range(4):
            d.rounded_rectangle([62, 26 + i * 34, 178, 52 + i * 34], 4, fill=colour, outline='#334155', width=2)
            d.ellipse([160, 34 + i * 34, 170, 44 + i * 34], fill='#22c55e')
    else:   # a box with lights
        d.rounded_rectangle([35, 45, 205, 135], 12, fill=colour, outline='#334155', width=4)
        for i in range(4):
            d.ellipse([55 + i * 22, 60, 69 + i * 22, 74], fill='#22c55e' if i % 2 == 0 else '#facc15')
        d.rectangle([150, 95, 190, 120], fill='#1e293b')
    out = BytesIO()
    img.save(out, 'PNG')
    return out.getvalue()


PDF = (b'%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj 2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj '
       b'3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 300 120]/Contents 4 0 R/Resources<</Font<</F1 5 0 R>>>>>>endobj '
       b'4 0 obj<</Length 52>>stream\nBT /F1 18 Tf 20 60 Td (Demo datasheet) Tj ET\nendstream endobj '
       b'5 0 obj<</Type/Font/Subtype/Type1/BaseFont/Helvetica>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF')


def _attach(thing, name, data, user, preview=False):
    from django.contrib.contenttypes.models import ContentType
    from django.core.files.base import ContentFile

    from web.models import Attachment
    item = Attachment(content_type=ContentType.objects.get_for_model(thing), object_id=thing.pk, name=name, size=len(data),
                      preview=preview, uploaded_by=user)
    item.file.save(name, ContentFile(data), save=False)
    item.save()
    return item


def _page(title, body, user, owner=None, parent=None, position=0):
    from django.contrib.contenttypes.models import ContentType

    from web.models import Page, PageVersion
    page = Page.objects.create(title=title, body=body, parent=parent, position=position, created_by=user, updated_by=user,
                               content_type=ContentType.objects.get_for_model(owner) if owner else (parent.content_type if parent else None),
                               object_id=owner.pk if owner else (parent.object_id if parent else None))
    PageVersion.objects.create(page=page, number=1, title=title, body=body, saved_by=user)
    return page


def _work(user, engineering, diagram, devices, psu, parts, orders):
    """Projects with what is in them, documentation pages, and pictures and files of things."""
    from work.models import Project as Work
    tools = list(Asset.objects.filter(kind='tool'))
    burn = Work.objects.create(code='BR', name='Burn-in rack', owner=user, department=engineering,
                               description='The burn-in rack: a controller, its load boards, the rack hub and the five devices it feeds.',
                               notes='Ready for the test lab by the end of the quarter.')
    burn.devices.set(devices.values())
    burn.assets.set(list(Asset.objects.filter(device__in=devices.values())) + tools)
    Project.objects.filter(pk=diagram.pk).update(in_project=burn)
    Order.objects.filter(pk__in=[o.pk for o in orders[:3]]).update(in_project=burn)
    lab = Work.objects.create(code='LAB', name='Lab upkeep', owner=user, department=engineering,
                              description='Keeping the lab going: tools, instruments, the bench supply.')
    lab.devices.set([psu])
    lab.assets.set(Asset.objects.filter(kind__in=['tool', 'measuring', 'lab']))
    Order.objects.filter(pk=orders[3].pk).update(in_project=lab)
    Work.objects.create(code='TB-0', name='Old test bench', status='done', owner=user, description='The bench before the rack.')

    # pictures (the first of each is its preview) and files
    for number, shape, colour, holes in (('DSUB-9-PLUG', 'dsub', '#cbd5e1', 9), ('DSUB-9-PLUG-B', 'dsub', '#d6d3d1', 9),
                                         ('DSUB-9-RECEPT', 'dsub', '#94a3b8', 9), ('DSUB-25-PLUG', 'dsub', '#cbd5e1', 25),
                                         ('DSUB-25-RECEPT', 'dsub', '#94a3b8', 25), ('M12-5-F', 'round', '#cbd5e1', 0),
                                         ('WIRE-22-RED', 'wire', '#ef4444', 0), ('WIRE-22-BLK', 'wire', '#1f2937', 0),
                                         ('WIRE-24-TP', 'wire', '#22c55e', 0)):
        _attach(parts[number], f'{number}.png', _picture(shape, colour, holes), user, preview=True)
    _attach(parts['DSUB-9-PLUG'], 'DSUB-9 datasheet.pdf', PDF, user)
    _attach(parts['DSUB-25-PLUG'], 'DSUB-25 datasheet.pdf', PDF, user)
    for number, device in devices.items():
        _attach(device, f'{number}.png', _picture('rack' if number == 'HUB-500' else 'box', device.colour), user, preview=True)
    _attach(psu, 'PSU-24.png', _picture('box', '#4b5563'), user, preview=True)
    for tool in tools:
        _attach(tool, f'{tool.number}.png', _picture('tool', '#f59e0b'), user, preview=True)
    _attach(burn, 'Burn-in rack.png', _picture('rack', '#3b7dd8'), user, preview=True)
    _attach(burn, 'Rack layout.pdf', PDF, user)
    _attach(orders[0], 'Quote from Acme.pdf', PDF, user)

    # documentation
    start = _page('Getting started', '<p>Osmia keeps the lab\'s <b>parts</b>, <b>orders</b>, <b>devices</b>, <b>wire diagrams</b> '
                  'and <b>assets</b> together, grouped by <b>project</b>.</p><h2>Where to look</h2><ul><li>Projects: what the work is for</li>'
                  '<li>Parts and orders: what is in stock and what is coming</li><li>Wire diagrams: how the devices are wired</li></ul>', user)
    _page('Crimping D-sub contacts', '<h2>Tools</h2><p>Use the <a href="/assets/">D-sub crimp tool</a> (T-001) for 20-24 AWG.</p>'
          '<h2>Steps</h2><ol><li>Strip 3 mm.</li><li>Crimp the contact in the 22 AWG nest.</li><li>Pull test: it must hold 20 N.</li></ol>',
          user, parent=start)
    overview = _page('Overview', '<p>The rack holds the <b>controller</b>, two <b>load boards</b> and the <b>rack hub</b>, which feeds '
                     'five devices over D-sub 25 to D-sub 9 harnesses.</p><table><thead><tr><th>Part</th><th>What</th></tr></thead>'
                     '<tbody><tr><td>CTRL-100</td><td>Rack controller</td></tr><tr><td>HUB-500</td><td>Rack hub</td></tr></tbody></table>',
                     user, owner=burn)
    _page('Test procedure', '<ol><li>Power the rack with the lab supply (24 V, 5 A).</li><li>Check every load board answers on CAN.</li>'
          '<li>Run the burn-in for 48 hours.</li></ol>', user, parent=overview)
    _page('Assembly', '<p>Gold plated contacts only. Tighten the jack screws to 0.3 Nm.</p>', user, owner=parts['DSUB-9-PLUG'])
    _page('Wiring notes', '<p>Each D-sub 9 gets two power wires and one shielded data set. The motor driver\'s power is spliced '
          'from the sensor\'s.</p>', user, owner=devices['HUB-500'])

def _harness(project, name, ends, wires, parts, user):
    h = Harness.objects.create(project=project, name=name, status='released')
    made = []
    for position, (designator, part, device, connector) in enumerate(ends):   # a part, or a family
        end = HarnessEnd(harness=h, designator=designator, position=position, connector=device.connectors.get(designator=connector))
        end.used = part_or_family(part) if part else None
        end.save()
        made.append(end)
    named = {e.designator: e for e in made}
    for a, b, colour, part, wire_set, set_type in wires:   # from the first end to the second, or 'P2:7' to 'P7:1'
        start, a = (named[a.split(':')[0]], a.split(':')[1]) if ':' in a else (made[0], a)
        to, b = (named[b.split(':')[0]], b.split(':')[1]) if ':' in b else (made[1], b)
        signal = start.connector.pins.get(number=a).signal
        Wire.objects.create(harness=h, from_end=start, from_pin=a, to_end=to, to_pin=b, signal=signal, colour=colour,
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
    """Take away every row the demo made. What real data uses now (a real order line of a demo part; a demo part real
    stock movements went in or out of, with its stock) stays: returns those, as text."""
    from django.apps import apps
    from django.db.models import ProtectedError, RestrictedError

    from .models import DemoRecord
    from inventory.models import Movement
    left = {}
    for record in DemoRecord.objects.all():
        left.setdefault(record.model, set()).add(record.object_id)
    moved = set(Movement.objects.exclude(pk__in=left.get('inventory.Movement', ())).values_list('part_id', flat=True))
    stays = {('inventory.Part', pk) for pk in moved} | {
        ('inventory.Stock', pk) for pk in apps.get_model('inventory.Stock').objects.filter(part_id__in=moved).values_list('pk', flat=True)}
    for _ in range(20):   # deleting a row can free another (an order line, then its part)
        progress = False
        for label, ids in list(left.items()):
            model = apps.get_model(label)
            for pk in list(ids):
                if (label, pk) in stays:
                    continue
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
