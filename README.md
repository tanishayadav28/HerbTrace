# HerbTrace: Blockchain-Based Geo-Tagged Traceability System for Ayurvedic Herbs

B.Tech (CSE) major project. A Django web application that follows every batch of an Ayurvedic herb from the
field to the finished formulation. Collectors record a GPS location, the laboratory records a PASS/FAIL result,
processors and manufacturers add their steps, and every event is written to an application-level SHA-256
hash-linked ledger. A QR code on the final product opens a public page (no login) showing the whole story.

## Features
* **Roles:** Administrator, Farmer / Wild Collector, Laboratory, Processor, Manufacturer. Consumers/regulators need no account (public QR page).
* **Access control:** custom user model, role decorators, 403 for another role's URLs, farmers can only open their own batches.
* **Farmer approval:** public registration creates a *PENDING* farmer. The administrator approves or rejects it under *Users & roles*. Only after approval can the farmer log in. Staff roles are created by the administrator only.
* **Collection + GPS:** browser Geolocation API, click/drag on a Leaflet map, or type coordinates manually (saved as "entered manually").
* **Region verification:** admin-managed circular approved regions (centre + radius, optional herb list). Inside -> straight to the lab queue. Outside, no GPS, or wild collection without a permit -> *Pending review*; the admin approves or rejects with a note.
* **Workflow:** collection -> lab (PASS/FAIL) -> processing (many steps) -> manufacturing -> final formulation + QR. FAIL = rejected, can never be processed or manufactured. Rules are enforced in the service layer inside database transactions, not only in forms.
* **Ledger:** SHA-256 over a canonical JSON of (sequence, batch id, event type, actor, UTC timestamp, event data, previous hash). Hashes are computed on the server only. Appends lock a single head row (`SELECT ... FOR UPDATE`). *Verify integrity* detects modified data, broken links, deleted/missing records, a truncated tail, and ordinary table rows edited without a ledger entry.
* **Public verification:** `/verify/<uuid>/` shows product, manufacturer, batches, herb, GPS map, region, lab results, processing, timeline and a clear WARNING banner if integrity fails. Only a first name + last initial of collectors is shown (no usernames, e-mails, phones).
* **Admin:** dashboard statistics, users, herbs, regions, region reviews, all batches (search by Batch ID/herb, filter by status/date, pagination), ledger page, reports and CSV export.

## Technology
Python 3.11+, Django 5.2, MySQL 8 (PyMySQL driver, pure Python so no C compiler is needed on Windows), HTML5/CSS3/Bootstrap 5/JavaScript, Leaflet + OpenStreetMap, `qrcode` + Pillow, `hashlib`.
No React, Node.js, Firebase, Ethereum, IPFS or smart contracts.

## Prerequisites (Windows)
1. Python 3.11 or newer (tick "Add python.exe to PATH" in the installer).
2. MySQL Server 8.x (MySQL Installer) and its `root` password.
3. Internet access in the browser (Bootstrap, icons, fonts, Leaflet and map tiles load from CDNs / OpenStreetMap).

## Installation (Windows, Command Prompt or PowerShell)
```bat
cd path\to\herbtrace
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
copy .env.example .env
```
PowerShell users: if activation is blocked run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once.

### Create the MySQL database
```bat
mysql -u root -p
```
```sql
CREATE DATABASE herb_traceability CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'herb_user'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT ALL PRIVILEGES ON herb_traceability.* TO 'herb_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```
`ALL PRIVILEGES` on this database also lets Django create the temporary test database `test_herb_traceability`
(grant on `test_herb_traceability.*` too if your MySQL setup requires it).

### Configure `.env`
Open `.env` in a text editor and set:
```
DJANGO_SECRET_KEY=<run: python -c "from django.core.management.utils import get_random_secret_key as g; print(g())">
DJANGO_DEBUG=True
DB_ENGINE=mysql
DB_NAME=herb_traceability
DB_USER=herb_user
DB_PASSWORD=choose-a-strong-password
DB_HOST=127.0.0.1
DB_PORT=3306
PUBLIC_BASE_URL=http://127.0.0.1:8000
```
Nothing secret is hard-coded; `.env` is git-ignored. For a quick trial without MySQL set `DB_ENGINE=sqlite`.

### Migrate, seed, run
```bat
python manage.py migrate
python manage.py seed_demo
python manage.py runserver
```
Open http://127.0.0.1:8000/. To scan QR codes with a phone on the same Wi-Fi, set `PUBLIC_BASE_URL` to your PC's LAN address (e.g. `http://192.168.1.20:8000`), run `python manage.py runserver 0.0.0.0:8000`, then re-seed (`seed_demo --reset`) or create new products, because the URL is encoded when the QR image is generated. Add the IP to `DJANGO_ALLOWED_HOSTS`.

### Create your own administrator (optional)
```bat
python manage.py createsuperuser
```
Superusers are treated as Administrators.

## Demo data and logins (local development ONLY)
`python manage.py seed_demo` creates sample herbs, three approved regions and ten batches in every state
(a finished product, lab-passed, processing in progress, awaiting lab, **rejected by lab**, **outside region**, no GPS, admin-approved).
Everything is flagged `is_demo` and labelled "demonstration data" on public pages. It is **not** real collection or lab data.
`python manage.py seed_demo --reset` wipes all traceability data (including the ledger) and rebuilds it. The command refuses to run when `DJANGO_DEBUG=False`.

| Role | Username | Password |
|---|---|---|
| Administrator | `demo_admin` | `DemoPass#2026` |
| Farmer | `demo_farmer`, `demo_farmer2` | `DemoPass#2026` |
| Laboratory | `demo_lab` | `DemoPass#2026` |
| Processor | `demo_processor` | `DemoPass#2026` |
| Manufacturer | `demo_manufacturer` | `DemoPass#2026` |
| Farmer awaiting approval | `demo_pending` | cannot log in until approved |

Never use these credentials or run the seed command in production.
The seed command prints the public URL of the demo product; open it without logging in.

## Suggested demo walk-through
1. As `demo_farmer`: *New collection*, press **Use my current location** (or click the map), submit, note the Batch ID.
2. As `demo_admin`: approve the pending region review if shown; open *Ledger integrity* and press **Verify integrity**.
3. As `demo_lab`: test the batch (PASS). Try FAIL on another and see it stop.
4. As `demo_processor`: add steps, mark completed. As `demo_manufacturer`: create a formulation, download the QR.
5. Open the public page, then tamper: in `python manage.py shell` run
   `from apps.traceability.models import BlockchainRecord as B; B.objects.filter(sequence=2).update(event_data={"x":1})`
   and refresh the public page and the ledger page to see the WARNING.

## Tests
```bat
python manage.py test
```
71 tests cover: login and role permissions, registration and approval, collection creation, Batch ID format/uniqueness,
region verification, lab PASS/FAIL workflow, processing and manufacturing restrictions, SHA-256 generation, previous-hash linking,
integrity verification, tampering (edit / link / delete / truncate / table-row edits), QR URL and PNG generation, and the public page
(no login, no private data, warning on tamper).

## Project structure
```
herbtrace/
  manage.py  requirements.txt  .env.example  README.md
  config/                settings (env based), urls
  apps/
    core/                navigation, pagination, form mixin, test factories
    accounts/            custom User, roles, login, registration, approval, admin user mgmt
    herbs/               Herb, ApprovedRegion, geofence maths
    traceability/        Collection, Batch, ledger (LedgerState, BlockchainRecord), timeline, reports
    laboratory/          LaboratoryTest + PASS/FAIL service
    processing/          Processing steps + status service
    manufacturing/       Manufacturing, BatchManufacturing, FinalFormulation, QRCode
    verification/        Verification log, public lookup + product page
  templates/             base, landing, dashboards, forms, public pages, partials
  static/                css/theme.css, js/app.js, js/maps.js, img/
  media/                 generated QR PNGs
```

## Limitations (please read)
* **Ledger is not a distributed blockchain.** It gives record integrity and modification detection only. Someone with full database
  write access who knows the algorithm could rebuild the whole chain. It cannot prove the physical herbs match the records.
  The chain-head row detects deleted trailing records but is itself a database row.
* **Region verification** uses circles (centre + radius, haversine distance), not polygons, so borders are approximate. Browser GPS can be
  spoofed and is inaccurate indoors; manual coordinates are accepted but labelled as manual and are only as trustworthy as the collector.
  Approved regions do not know about real forest ranges or legal permits; the permit number is not checked against any authority.
* Dashboards and maps need internet (CDN assets, OSM tiles). Static files are served by Django's development server; for production use
  `collectstatic` plus a real web server, HTTPS and `DJANGO_DEBUG=False`.
* Demo botanical imagery is an inline/SVG illustration; add your own photographs under `static/img/` if you want photo backgrounds.
* The automated tests run on the configured database engine; the project was developed and tested against SQLite in a Linux container. MySQL is the target
  and uses standard Django ORM features only, but run `python manage.py test` on your own MySQL once to confirm.
