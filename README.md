# Bill Creator for Kleinstunternehmer

Creates compact Austrian **Honorarnoten** from JSON/CSV data and generates AsciiDoc or PDF output.

Intended for small side-business / freelance work, for example monthly IT courses, workshops, and other hourly services.

> Note: The project name uses “Kleinstunternehmer”. The Austrian VAT term is **Kleinunternehmerregelung**.

## Features

- separates fixed personal data from invoice data
- supports item-specific hourly rates
- calculates durations and totals from appointment rows
- generates compact A4 PDFs with AsciiDoc / Asciidoctor PDF
- keeps private `data/` out of Git
- provides `data-example/` as a starter template
- can back up `data/` to `~/Documents/bill-creator/data`

## Requirements

```bash
python3 --version
ruby --version
gem install asciidoctor-pdf
```

Or with Bundler:

```bash
bundle install
```

## First setup

Create your private data folder from the example:

```bash
cp -r data-example data
```

Edit:

```text
data/profile.json      # your address, tax number, bank account, VAT settings
data/items.json        # billable items and hourly rates
data/2026-04/invoice.json
data/2026-04/appointments.csv
```

Make sure the backup script is executable:

```bash
chmod +x scripts/sync-data.sh
```

## Project structure

```text
data-example/          # committed starter data
data/                  # private real data, ignored by Git
scripts/sync-data.sh   # backs up data/
templates/             # PDF theme
build/                 # generated output
generate_honorarnote.py
Makefile
```

## Generate an invoice

Generate AsciiDoc:

```bash
make adoc
```

Generate PDF:

```bash
make pdf
```

Use another invoice file:

```bash
make pdf INVOICE=data/2026-05/invoice.json
```

By default, the Makefile uses:

```text
PROFILE = data/profile.json
ITEMS   = data/items.json
INVOICE = data/2026-04/invoice.json
```

Generated files are written to:

```text
build/<invoice-folder>/<invoice-number>.adoc
build/<invoice-folder>/<invoice-number>.pdf
```

## Appointment CSV

```csv
date,from,to,duration_hours,item,description
2026-04-03,15:00,17:00,,school-course,Scratch Grundlagen
2026-04-10,15:00,17:00,,school-course,Variablen und einfache Spiele
```

`duration_hours` can be empty. Then the duration is calculated from `from` and `to`.

The `item` value must exist in `data/items.json`:

```json
{
  "coding-course": {
    "label": "Coding Course",
    "hourly_rate": 0.0
  }
}
```

## Create a new month

```bash
cp -r data/2026-04 data/2026-05
```

Then edit:

```text
data/2026-05/invoice.json
data/2026-05/appointments.csv
```

Generate:

```bash
make pdf INVOICE=data/2026-05/invoice.json
```

## Multiple customers in one month

Each final Honorarnote needs a unique invoice number.

Recommended:

```text
HN-2026-001
HN-2026-002
HN-2026-003
```

Example monthly structure:

```text
data/2026-04/
  HN-2026-001-school.json
  HN-2026-001-school-appointments.csv
  HN-2026-002-school-abc.json
  HN-2026-002-school-abc-appointments.csv
```

Each invoice JSON points to its own CSV:

```json
{
  "invoice_no": "HN-2026-001",
  "invoice_date": "2026-04-30",
  "service_period": "April 2026",
  "appointments_file": "HN-2026-001-appointments.csv",
  "customer": {
    "name": "Unternehmen GmbH",
    "address": [
      "Example Street 1",
      "1010 Wien",
      "Austria"
    ]
  }
}
```

Generate separately:

```bash
make pdf INVOICE=data/2026-04/HN-2026-001.json
make pdf INVOICE=data/2026-04/HN-2026-002-school-abc.json
```

## Back up data

The project `data/` folder is the source of truth.

Create or update the backup:

```bash
make backup-data
```

This copies:

```text
./data -> ~/Documents/bill-creator/data
```

`make pdf` also runs the backup after generating the PDF.

The script does not touch `data-example/`.

## Git behavior

Commit `data-example/`, but not real private data:

```gitignore
/data/
!/data-example/
!/data-example/**
```

This keeps address, bank account, tax number, customers, and real invoices out of Git.

## Kleinunternehmer note

For Austrian Kleinunternehmer invoices, use a VAT note like:

```text
Umsatzsteuerfrei gemäß § 6 Abs. 1 Z 27 UStG (Kleinunternehmerregelung).
```

Do not show VAT percentages or VAT amounts when using the Kleinunternehmerregelung.

Example in `data/profile.json`:

```json
{
  "defaults": {
    "currency": "EUR",
    "payment_due_days": 14,
    "vat": {
      "mode": "kleinunternehmer",
      "percent": 0,
      "note": "Umsatzsteuerfrei gemäß § 6 Abs. 1 Z 27 UStG (Kleinunternehmerregelung)."
    }
  }
}
```

## Clean generated files

```bash
make clean
```
