"""What a wire is for (its label in the drawing: PWR, GND, TX+, …), to pick from as a tree; and the label at a
loopback's other end, as a send's receive (TX: RX)."""

PURPOSES = [
    ('Power', ['PWR', 'VCC', 'VIN', '+3.3V', '+5V', '+12V', '+24V', '+48V', 'VBAT', 'VBUS']),
    ('Ground', ['GND', '0V', 'AGND', 'DGND', 'PE', 'SHIELD']),
    ('Communication', [
        ('Serial', ['TX', 'RX', 'RTS', 'CTS', 'DTR', 'DSR']),
        ('RS-422 / RS-485', ['TX+', 'TX-', 'RX+', 'RX-', 'A', 'B']),
        ('CAN', ['CAN_H', 'CAN_L']),
        ('SPI', ['SCK', 'MOSI', 'MISO', 'CS']),
        ('I²C', ['SCL', 'SDA']),
        ('USB', ['D+', 'D-']),
        ('Ethernet', ['TD+', 'TD-', 'RD+', 'RD-']),
    ]),
    ('I/O', ['IN', 'OUT', 'AIN', 'AOUT', 'SIG', 'EN', 'RESET']),
]

_PAIRS = [('TX', 'RX'), ('RTS', 'CTS'), ('DTR', 'DSR'), ('TX+', 'RX+'), ('TX-', 'RX-'), ('MOSI', 'MISO'),
          ('TD+', 'RD+'), ('TD-', 'RD-'), ('OUT', 'IN'), ('AOUT', 'AIN')]
MATES = {**dict(_PAIRS), **{b: a for a, b in _PAIRS}}


def mate(label):
    """What the other end of a loopback is, when this end is ``label``: a send's receive, else the same."""
    return MATES.get(label.upper(), label)


def tree():
    """The purposes as the drawing's popup takes them: each node with its depth and its groups of labels (a node with
    branches: theirs)."""
    out = []
    for name, below in PURPOSES:
        if below and isinstance(below[0], tuple):
            out.append({'name': name, 'depth': 0, 'groups': [[n, items] for n, items in below]})
            out.extend({'name': n, 'depth': 1, 'groups': [[n, items]]} for n, items in below)
        else:
            out.append({'name': name, 'depth': 0, 'groups': [[name, below]]})
    return out
