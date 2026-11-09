# Osmia

Tracks **parts** (counted in stock: small electronics, hardware, zip ties, tape…), **assets** (kept one by one with an
asset tag: tools, lab equipment, the devices and harnesses built or bought), orders for both, budgets, devices with their
connectors and pins, the harnesses between them, and wire diagrams: a tree of configurations, each drawn as its devices and
harnesses. Each part, asset, device, harness and wire diagram has a documentation page and a picture; parts and assets print
on label sheets.

## Quick start (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python serve.py
```

Open http://127.0.0.1:8000. The first time, Osmia asks for the administrator account. Everything Osmia keeps is in
`data\` (or `OSMIA_DATA_DIR`): the database and uploaded files. For real use set `OSMIA_DEBUG=0`,
`OSMIA_SECRET_KEY` and `OSMIA_ALLOWED_HOSTS`, and run `serve.py --host 0.0.0.0`. Password reset mails need
`OSMIA_EMAIL_HOST`, `OSMIA_EMAIL_USER`, `OSMIA_EMAIL_PASSWORD`, `OSMIA_EMAIL_FROM` (without them they're printed on
the console). Administrators add users, and can change anything in bulk, at `/admin/`.

**Demo data**: to try Osmia, an administrator switches the demo data on (their name, top right → Demo data, or
`.\.venv\Scripts\python manage.py demo`). It goes in next to your own data and every row it made is remembered, so
switching it off (`manage.py demo --off`) takes exactly those away again; a demo item your real data uses by then (a real
order of a demo part) is kept, and said. See `web/demo.py`.

**Moving the data** to another Osmia (or keeping a backup): an administrator exports everything to one .zip file — the
database and every uploaded file — on *their name → Export / import*, or with `manage.py export_data [file.zip]`.
Importing it elsewhere (same page, or `manage.py import_data file.zip`) replaces *all* the data there, users too; what
was there is first saved to `dataackups\`. An export from an older Osmia is brought up to date by the migrations; one
from a newer Osmia is refused until that one is updated. See `web/backup.py`.

**Updating Osmia**: an administrator downloads the code from GitHub (*Code → Download ZIP*) and uploads it on *their
name → Update Osmia*. Osmia checks it is its code and not older than the data, saves the data and the code it has now
in `dataackups\`, puts the new code in place, installs the requirements if they changed, runs the migrations and starts
again by itself (when run with `serve.py`, which watches over the server; otherwise start it again yourself). If any of
that fails, the old code and the data are put back. See `web/update.py`; the version is in `osmia/version.py`.

**Migrations**: each part's database changes are in its `migrations/` folder, in git; they run on every start of
`serve.py` and with each update, so new code brings its database changes with it.

## The parts

| Part | What it is |
|---|---|
| `inventory/` | **Parts** (number, description, category, manufacturer, vendor and their number, last price, minimum stock), **vendors**, **locations** (a tree: building → room → shelf → bin), how many of each part are in each location, and every movement of stock (added, moved, used, counted, received). Stock changes only through `inventory/stock.py`, and never goes below zero. A connector **family** is the one place its face is defined: in its **connector editor** (`inventory/faces.py`) it starts from a single row, two rows, a D-sub, a circle or a grid, and its contacts are then dragged into place, renumbered, added or taken away, in an outline (box, D-sub, round) fitted around them, or one of its own (its corners dragged, new ones pulled out of the middle of an edge); its pin and socket **genders** are made with it, and the socket side is drawn mirrored. A harness's page then draws its pinout, each connector's face on the far sides with its pins in place, the wires between columns of contact numbers, and picking a wire set lights up its contacts and pins. **Families** group parts that can take each other's place (the same D-sub 9 plug from other makers), split into **genders** (pin, socket, …): a harness end, wire or item, or a device connector, can name the family ("D-sub 9") or a gender of it ("D-sub 9 / socket") instead of one part; their stock counts together, building takes the most stocked first, and ordering what is missing orders the part of it last ordered. **Categories**: parts and assets each have their own tree. They hold **attributes** for what is in them, trickling down to the categories under them: text, whole numbers, numbers, a choice from a list, yes/no, an **auto number** (an ID: prefix and digits, given on saving, one count through its tree), **interacts with** parts of a category (named by you, e.g. "Mates with sockets"; the other side shows it under its own name, e.g. "Mates with pins") or a **link** to any part or an asset (e.g. "Crimped with"). Lists show and filter by them. See `inventory/attributes.py`. |
| `assets/` | **Assets**: everything kept one by one with an asset tag, of a kind from a list (tool, lab equipment, measuring instrument, electronics, device, harness, IT, other) and a category (its attributes): where it is kept, who looks after it, checked out and brought back, in use, away for calibration or repair, retired; calibration every so many months (Home lists those due within two weeks); bought with an order ("still to be bought" until it arrives); a device's or harness's design and the version it was built to (a harness built has a checklist of every wire, placed then verified); its history; what links to it. |
| `orders/` | **Orders** to vendors, of parts and assets: a draft with its lines, placed (with when it is expected), received line by line (parts into stock, assets made available; whoever made it hears what arrived), or cancelled. **Reorder** on a part puts it on the vendor's draft order. **＋ Add item** at the top of a draft opens a list of the parts (search it, or pick a category) and of the assets waiting to be ordered; it opens again after each one added. Or **ask someone to order**: describe what you need (with the budget, vendor and who should order it if you know); who is asked (else the administrators) hears of it, adds the lines and places it, and you hear when it is ordered: the Requests tab and Home show the open ones. Home lists what is still to come (late first) and the parts below their minimum. See `orders/service.py`. |
| `budgets/` | **Budgets**: a tree (FY2026 › Engineering › Test equipment), each with an amount, an owner, maybe a department, a wire diagram and a period. Orders are charged to a budget: planned while a draft, spent once placed (what arrived and what is still to come); **other costs** (services, travel) are added on the budget. What is spent rolls up through the budgets above; the owner hears when one is overspent, and an order's page says before placing it when it would overspend. Amounts show with `OSMIA_CURRENCY` (e.g. €) if set. See `budgets/money.py`. |
| `devices/` | **Devices**: designs, made in-house or bought (a power supply), with their **connectors** (designator, part) and each connector's **pins** (number, signal), edited as a table; saved as **versions** (seen, and restored: connectors kept by designator, so what plugs into them stays). Each one built or bought is an asset. |
| `harnesses/` | **Harnesses**, each in a wire diagram: their **ends** (a connector each, plugged into a device's connector), **pinout** (from an end's pin to another's: signal, set, set type, colour, gauge, length, wire part; a signal left empty comes from the device's pin) and other items, edited as tables; what is wrong (a pin the device hasn't, signals that don't match, two wires on a pin); the **parts list**; versions. Building one makes an asset with a checklist of its wires, and can take its parts out of stock. |
| `work/` | **Projects** (at `/projects/`): what the work is for, with a status and an owner; a wire diagram or an order is of one project, a device or an asset (a tool too) can be in several; each project's page lists them, its notes, files and documentation. |
| `projects/` | **Wire diagrams** (at `/wire-diagrams/`) and their **configurations**: a tree where each configuration is its parent with its own changes (a device or harness added, taken away, swapped, moved, plugged in differently; `projects/configs.py`), or a setup of its own. The project's page draws the selected configuration (drag the devices; what it added is green, changed orange, taken away faded), lists its changes (each can be undone), what is wrong (a harness not plugged in, plugged into the wrong device, two in one connector), and **what it needs** to be built (devices, harnesses, parts against stock; order what is missing). In the diagram each device is a box with its name; its connectors are squares on its outline, labelled, that slide along it (they start on the side facing what they are plugged into); each harness line has a handle that pins it where it is put (grey: free, blue: pinned). Someone can **ask for a harness** between two devices of a configuration (what is needed, who should make it): it shows as a dashed line in the diagram and on Home; drawing a harness between the two closes it, and who asked hears. |
| `web/` | The site itself: the first run, Home, notifications; **documentation** (`web/pages.py`, at `/docs/`): pages like a wiki, general or of something (a project, part, device, …), under each other, written in an editor with a toolbar (headings, text styles, lists, links, tables, pictures; kept as cleaned HTML, `web/markup.py`), every save kept (history, bring an old version back), found by what they say; **files** of anything (`web/files.py`): a Files card on each page, files picked or dropped on it, pictures as thumbnails, one picture the **preview** (on its page and in lists); what they can belong to is `web/things.py`; **labels** (`web/labels.py`: one or many parts or assets on an A4 sheet of labels, in several sizes, showing what is chosen, kept as the default for parts or assets); versions (`web/versions.py`), editing rows as a table (`web/rows.py`), Excel export (`web/excel.py`), what every page shares (`web/shortcuts.py`), the shared styles, the `demo` command. |
| `accounts/` | Logging in, profile, passwords; **departments** (a tree, with a manager, its people, budgets and wire diagrams; everyone sees them) and, for administrators, the **users** page: making people, changing them, making them administrators or stopping their log-in, putting them in a department. |

**Excel**: the ⬇ Excel buttons on the parts, a location, the orders, the assets, the budgets, a budget, the users, the
devices, a device, a harness and what a configuration needs download what the page shows as an .xlsx file.

**Labels**: tick parts or assets in their list and press 🏷 Labels (none ticked: all those listed), or 🏷 Label on one.

The ☰ menu at the top left leads to the apps (parts, orders, locations, wire diagrams, devices, assets); what belongs to one is reached from inside it (categories and vendors from the parts, budgets and vendors from the orders, harnesses from the wire diagrams). Administrators find the users under their name, top right.

## Developing

```powershell
.\.venv\Scripts\python manage.py migrate
.\.venv\Scripts\python manage.py runserver
.\.venv\Scripts\python manage.py test                 # every processor (--parallel 1: one at a time)
.\.venv\Scripts\python manage.py test --slowest 20    # one at a time, then the 20 slowest tests and set-ups
```

Tests make their users with a quick password hash (see `osmia/settings.py`) and run spread over every processor
(`osmia/testrunner.py`). Browser tests (`--tag browser`) use `web/tests/browser.py` and need Playwright
(`pip install -r requirements-dev.txt`) and Edge, Chrome or `playwright install chromium`.
