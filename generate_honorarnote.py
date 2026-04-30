#!/usr/bin/env python3
"""Generate a compact Austrian Honorarnote as AsciiDoc, optionally as PDF.

Default usage:
  python3 generate_honorarnote.py
  python3 generate_honorarnote.py --pdf

Use a different monthly invoice folder:
  python3 generate_honorarnote.py --invoice data/2026-05/invoice.json --pdf

Inputs:
  data/profile.json                 fixed data: issuer, bank, defaults
  data/items.json                   billable item definitions and hourly rates
  data/<YYYY-MM>/invoice.json       per-invoice data: invoice number, client, period
  data/<YYYY-MM>/appointments.csv   per-invoice rows: date/from/to/item/description

Output:
  build/<YYYY-MM>/<invoice_no>.adoc
  build/<YYYY-MM>/<invoice_no>.pdf when --pdf is used and asciidoctor-pdf is installed
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent


def money(value: Decimal | float | int, currency: str = "EUR") -> str:
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    s = f"{d:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} {currency}"


def hourly(value: Decimal | float | int) -> str:
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{d:.2f}".replace(".", ",")


def hours(value: Decimal | float | int) -> str:
    d = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{d:.2f}".replace(".", ",")


def parse_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def format_date(value: str) -> str:
    return parse_date(value).strftime("%d.%m.%Y")


def format_due_date(invoice_date: str, days: int) -> str:
    return (parse_date(invoice_date) + timedelta(days=days)).strftime("%d.%m.%Y")


def parse_time(value: str) -> datetime:
    return datetime.strptime(value, "%H:%M")


def compute_duration(start: str, end: str) -> Decimal:
    a = parse_time(start)
    b = parse_time(end)
    if b < a:
        raise ValueError(f"End time {end} is before start time {start}")
    minutes = Decimal(str((b - a).total_seconds() / 60))
    return (minutes / Decimal("60")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def esc(text: Any) -> str:
    """Minimal AsciiDoc-safe escaping for table cells."""
    return str(text).replace("|", "\\|").replace("\n", " + ")


def strip_empty(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    if text.lower().startswith("optional"):
        return ""
    return text


@dataclass
class Item:
    code: str
    label: str
    hourly_rate: Decimal


@dataclass
class Appointment:
    date: str
    start: str
    end: str
    duration: Decimal
    item: Item
    description: str
    amount: Decimal


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_items(path: Path) -> dict[str, Item]:
    raw = read_json(path)
    raw_items = raw.get("items", raw)  # supports either {"code": {...}} or {"items": {"code": {...}}}
    items: dict[str, Item] = {}
    for code, cfg in raw_items.items():
        if not isinstance(cfg, dict):
            raise ValueError(f"Item {code!r} in {path} must be an object")
        if "hourly_rate" not in cfg:
            raise ValueError(f"Item {code!r} in {path} has no hourly_rate")
        items[code] = Item(
            code=code,
            label=str(cfg.get("label", code)),
            hourly_rate=Decimal(str(cfg["hourly_rate"])),
        )
    if not items:
        raise ValueError(f"No items defined in {path}")
    return items


def load_appointments(csv_path: Path, items: dict[str, Item]) -> list[Appointment]:
    rows: list[Appointment] = []
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        required = {"date", "from", "to", "duration_hours", "item", "description"}
        missing = required - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f"Missing columns in {csv_path}: {', '.join(sorted(missing))}")
        for row in reader:
            item_code = (row.get("item") or "").strip()
            if item_code not in items:
                known = ", ".join(sorted(items))
                raise ValueError(f"Unknown item {item_code!r} in {csv_path}. Known items: {known}")
            item = items[item_code]
            duration_raw = (row.get("duration_hours") or "").strip()
            duration = Decimal(duration_raw.replace(",", ".")) if duration_raw else compute_duration(row["from"], row["to"])
            amount = (duration * item.hourly_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            rows.append(
                Appointment(
                    date=row["date"],
                    start=row["from"],
                    end=row["to"],
                    duration=duration,
                    item=item,
                    description=row["description"],
                    amount=amount,
                )
            )
    return rows


def address_block(person: dict[str, Any]) -> str:
    lines = [strip_empty(person.get("name", ""))]
    lines.extend(strip_empty(x) for x in person.get("address_lines", []))
    contact = strip_empty(person.get("contact"))
    if contact:
        lines.append(f"z.H. {contact}")
    return " +\n".join(esc(x) for x in lines if x)


def contact_line(issuer: dict[str, Any]) -> str:
    items = []
    email = strip_empty(issuer.get("email"))
    phone = strip_empty(issuer.get("phone"))
    tax_number = strip_empty(issuer.get("tax_number"))
    uid = strip_empty(issuer.get("uid"))
    if email:
        items.append(f"Kontakt: {email}")
    if phone:
        items.append(phone)
    if tax_number:
        items.append(f"Steuernummer: {tax_number}")
    if uid:
        items.append(f"UID: {uid}")
    return " · ".join(items)


def resolve_invoice_data(
    profile_path: Path,
    items_path: Path,
    invoice_path: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Item], str, int, dict[str, Any], Path, str]:
    profile = read_json(profile_path)
    invoice = read_json(invoice_path)
    items = load_items(items_path)
    defaults = profile.get("defaults", {})

    currency = invoice.get("currency", defaults.get("currency", "EUR"))
    payment_due_days = int(invoice.get("payment_due_days", defaults.get("payment_due_days", 14)))
    vat = invoice.get("vat", defaults.get("vat", {"mode": "kleinunternehmer", "percent": 0}))

    appointments_file = invoice.get("appointments_file", "appointments.csv")
    appointments_path = (invoice_path.parent / appointments_file).resolve()
    if not appointments_path.exists():
        raise FileNotFoundError(f"Appointments file not found: {appointments_path}")

    month_key = invoice_path.parent.name
    return profile, invoice, items, currency, payment_due_days, vat, appointments_path, month_key


def make_adoc(
    profile: dict[str, Any],
    invoice: dict[str, Any],
    appointments: list[Appointment],
    currency: str,
    payment_due_days: int,
    vat_cfg: dict[str, Any],
) -> str:
    invoice_no = invoice["invoice_no"]
    invoice_date = invoice["invoice_date"]
    service_period = invoice.get("service_period", "")
    due_date = format_due_date(invoice_date, payment_due_days)

    issuer = profile["issuer"]
    customer = invoice["customer"]
    bank = profile["bank"]
    defaults = profile.get("defaults", {})

    total_hours = sum((a.duration for a in appointments), Decimal("0"))
    net_total = sum((a.amount for a in appointments), Decimal("0"))
    vat_mode = vat_cfg.get("mode", "kleinunternehmer")
    vat_percent = Decimal(str(vat_cfg.get("percent", 0)))
    vat_amount = (net_total * vat_percent / Decimal("100")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    gross_total = net_total + vat_amount

    parts: list[str] = [
        f"= Honorarnote {esc(invoice_no)}",
        ":doctype: article",
        ":pdf-page-size: A4",
        ":sectnums!:",
        ":toc!:",
        ":notitle:",
        ":icons: font",
        "",
        "[cols=\"3.5,2\", frame=none, grid=none]",
        "|===",
        f"a|[.invoice-title]#Honorarnote {esc(invoice_no)}# +\nLeistungszeitraum: *{esc(service_period)}*",
        f"a|Ausgestellt: *{format_date(invoice_date)}* +\nZahlbar bis: *{due_date}*",
        "|===",
        "",
        "[cols=\"1,1\", frame=none, grid=none]",
        "|===",
        f"a|*Aussteller/in* +\n{address_block(issuer)}",
        f"a|*Empfänger/in* +\n{address_block(customer)}",
        "|===",
        "",
        "*Leistungsaufstellung*",
        "",
        "[cols=\"0.74,0.42,0.42,0.38,3.8,0.62,0.78\", options=\"header\"]",
        "|===",
        "^|Datum ^|Von ^|Bis ^|h |Leistung / Beschreibung >|€/h >|Betrag",
    ]

    for a in appointments:
        service_text = f"{a.item.label}: {a.description}" if a.description else a.item.label
        parts.append(
            f"^|{format_date(a.date)} ^|{esc(a.start)} ^|{esc(a.end)} ^|{hours(a.duration)} |{esc(service_text)} >|{hourly(a.item.hourly_rate)} >|{money(a.amount, currency)}"
        )

    parts.extend([
        "|===",
        "",
        "[cols=\"4.8,1.25\", frame=none, grid=rows]",
        "|===",
        f">|Summe Stunden >|*{hours(total_hours)} h*",
        f">|Zwischensumme >|*{money(net_total, currency)}*",
    ])

    if vat_mode == "kleinunternehmer" or vat_percent == 0:
        parts.append(f">|Umsatzsteuer >|*0,00 {currency}*")
        parts.append(f">|Gesamtbetrag >|*{money(net_total, currency)}*")
    else:
        parts.append(f">|Umsatzsteuer {hours(vat_percent)} % >|{money(vat_amount, currency)}")
        parts.append(f">|Gesamtbetrag >|*{money(gross_total, currency)}*")

    parts.extend([
        "|===",
        "",
    ])

    compact_notes: list[str] = []
    if vat_cfg.get("note"):
        compact_notes.append(str(vat_cfg["note"]))
    c = contact_line(issuer)
    if c:
        compact_notes.append(c)
    if compact_notes:
        parts.append("[.small]")
        parts.append("--")
        parts.append(esc(" ".join(compact_notes)))
        parts.append("--")
        parts.append("")

    parts.extend([
        "*Zahlungsinformationen*",
        "",
        "[cols=\"1.05,2.7,1.15,2.2\", frame=none, grid=rows]",
        "|===",
        f"|Kontoinhaber/in |{esc(bank['account_holder'])} |Verwendungszweck |Honorarnote {esc(invoice_no)}",
        f"|IBAN |{esc(bank['iban'])} |BIC |{esc(bank.get('bic', ''))}",
        f"|Bank |{esc(bank.get('bank_name', ''))} |Fällig am |{due_date}",
        "|===",
        "",
    ])

    notes = invoice.get("notes", [])
    if notes:
        parts.append("[.small]")
        parts.append("--")
        parts.append(" ".join(f"• {esc(note)}" for note in notes))
        parts.append("--")
        parts.append("")

    thank_you = invoice.get("thank_you", defaults.get("thank_you", "Vielen Dank."))
    if thank_you:
        parts.append(f"[.small]#{esc(thank_you)}#")
        parts.append("")

    return "\n".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", default="data/profile.json", help="fixed issuer/bank/default data JSON")
    parser.add_argument("--items", default="data/items.json", help="billable item definitions and hourly rates JSON")
    parser.add_argument("--invoice", default="data/2026-04/invoice.json", help="monthly per-invoice JSON")
    parser.add_argument("--theme", default="templates/compact-theme.yml", help="asciidoctor-pdf theme YAML")
    parser.add_argument("--out-dir", default="build", help="base output directory")
    parser.add_argument("--pdf", action="store_true", help="also build PDF using asciidoctor-pdf")
    args = parser.parse_args()

    profile_path = (ROOT / args.profile).resolve()
    items_path = (ROOT / args.items).resolve()
    invoice_path = (ROOT / args.invoice).resolve()
    theme_path = (ROOT / args.theme).resolve()
    out_base_dir = (ROOT / args.out_dir).resolve()

    profile, invoice, items, currency, payment_due_days, vat, appointments_path, month_key = resolve_invoice_data(
        profile_path,
        items_path,
        invoice_path,
    )
    appointments = load_appointments(appointments_path, items)

    out_dir = out_base_dir / month_key
    out_dir.mkdir(parents=True, exist_ok=True)
    invoice_no = invoice["invoice_no"].replace("/", "-")
    adoc_path = out_dir / f"{invoice_no}.adoc"
    adoc_path.write_text(
        make_adoc(profile, invoice, appointments, currency, payment_due_days, vat),
        encoding="utf-8",
    )
    print(f"Wrote {adoc_path.relative_to(ROOT)}")

    if args.pdf:
        exe = shutil.which("asciidoctor-pdf")
        if not exe:
            raise SystemExit("asciidoctor-pdf not found. Install with: gem install asciidoctor-pdf")
        if not theme_path.exists():
            raise FileNotFoundError(f"Theme file not found: {theme_path}")
        subprocess.run(
            [exe, "-a", f"pdf-theme={theme_path}", "-o", str(adoc_path.with_suffix(".pdf")), str(adoc_path)],
            check=True,
            cwd=ROOT,
        )
        print(f"Wrote {adoc_path.with_suffix('.pdf').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
