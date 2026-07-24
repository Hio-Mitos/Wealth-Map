"""
WealthMap – Utility Bill Import

Parses a utility/statement PDF (electricity, water, internet, etc.) into a
plain structured dict so the Bills tab "Import Bill" action can show an
editable preview before anything is written to the database — the same
"review before it's filled in" pattern as src/services/payslip_import.py.

Layout notes: unlike the payslip parser (which needs word-level bounding
boxes because two amount columns interleave), a bill statement's raw text
layer already contains every value we need somewhere in the linear text —
it's just that two-column sections (e.g. "Customer Account Number (CAN)" /
"Due Date") get flattened so labels and values from neighboring columns
land on the same or a nearby line in an inconsistent order. Rather than
require a strict "label immediately followed by its value" match, each
field below is found with a small search window or a globally distinctive
value pattern (dates, "X to Y" billing-period pairs, amounts as
"1,234.56") that reliably identifies the right value wherever it lands in
the flattened text.

Different providers use genuinely different statement layouts, so this
module detects the provider and dispatches to a provider-specific parser
(currently Meralco electric bills, Converge internet bills, and Philippine
condo/HOA "association dues" invoices), falling back to a best-effort
generic parser for anything else. Every parser returns the same dict
shape; any field a given layout doesn't have (e.g. kWh consumption on an
internet bill, or a due date that a scanned/OCR'd document simply doesn't
render legibly) is simply left blank/None for the user to fill in on the
review screen, so a partial match is never a hard failure.

This module only *reads* the PDF and returns data — it never touches the
DB or the app's services.
"""

import re
import calendar
from datetime import datetime
from typing import Optional, Dict, Any, List


class BillParseError(Exception):
    pass


DATE_RE_LONG = r"\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"          # "21 Jan 2026"
DATE_RE_SLASH = r"\d{1,2}/\d{1,2}/\d{4}"                    # "06/10/2026"
AMOUNT_RE = r"[\d,]+\.\d{2}"

KNOWN_PROVIDERS = [
    ("MANILA ELECTRIC COMPANY", "Manila Electric Company (Meralco)"),
    ("MERALCO", "Manila Electric Company (Meralco)"),
    ("MAYNILAD", "Maynilad Water Services"),
    ("MANILA WATER", "Manila Water Company"),
    ("CONVERGE", "Converge ICT"),
    ("PLDT", "PLDT"),
    ("GLOBE TELECOM", "Globe Telecom"),
    ("COMMUNITY PROPERTY MANAGERS GROUP", "Community Property Managers Group Inc."),
]


def _parse_date(text: Optional[str]) -> Optional[datetime]:
    if not text:
        return None
    text = text.strip()
    for fmt in ("%d %b %Y", "%d %B %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _num(text: Optional[str]) -> Optional[float]:
    if not text:
        return None
    try:
        return float(text.replace(",", "").strip())
    except ValueError:
        return None


def _find(pattern: str, text: str, flags=re.MULTILINE) -> Optional[re.Match]:
    return re.search(pattern, text, flags)


def _detect_provider(text: str) -> str:
    upper = text.upper()
    upper_nospace = re.sub(r"\s+", "", upper)
    for needle, label in KNOWN_PROVIDERS:
        if needle in upper or needle.replace(" ", "") in upper_nospace:
            return label
    return ""


def _empty_result() -> Dict[str, Any]:
    return {
        "provider": "", "account_number": "", "meter_number": "",
        "service_address": "", "reference_no": "",
        "due_date": None, "bill_date": None,
        "period_start": None, "period_end": None,
        "total_amount_due": None, "remaining_balance_previous": 0.0,
        "period_charges": None, "rate_per_unit": None,
        "consumption": None, "consumption_unit": "",
        "currency_code": "", "charges_breakdown": {},
        "payment_history": [], "unpaid_history": [],
        # Free-text lines a parser wants surfaced in the bill's Notes field
        # that don't fit the structured fields above (e.g. a caveat about
        # an estimated value). Appended verbatim by the review dialog.
        "extra_notes": [],
    }


# ─── Meralco (electric bill) ────────────────────────────────────────────────

def _meralco_charge_breakdown(page1_text: str) -> Dict[str, float]:
    labels = [
        "Generation", "Transmission", "System Loss", "Distribution (Meralco)",
        "Subsidies", "Government Taxes", "Universal Charges", "FiT-All (Renewable)",
    ]
    out = {}
    for label in labels:
        m = _find(re.escape(label) + r"\s+(" + AMOUNT_RE + r")", page1_text)
        if m:
            out[label] = _num(m.group(1))
    return out


def _meralco_service_address(page2_text: str) -> str:
    lines = page2_text.splitlines()
    for i, line in enumerate(lines):
        if "Service Address:" in line:
            first = line.split("Service Address:", 1)[1]
            for junk in ("Total Energy Amount", "Charges for this"):
                if junk in first:
                    first = first.split(junk, 1)[0]
            first = first.strip()
            parts = [first] if first else []
            if i + 1 < len(lines):
                nxt = lines[i + 1].strip()
                if nxt and ":" not in nxt and not re.match(r"^[A-Z][a-z]+ ", nxt):
                    parts.append(nxt)
            return ", ".join(parts)
    return ""


def _meralco_payment_history(page2_text: str) -> List[Dict[str, Any]]:
    pattern = re.compile(
        r"(\d{2}\s+[A-Za-z]{3}-\d{2}\s+[A-Za-z]{3}\s+\d{4})\s*"   # billing period
        r"(\d{2}\s+[A-Za-z]{3}\s+\d{4})"                          # posting date
        r"(Meralco Online|Meralco Headquarters|[A-Za-z][A-Za-z .]{2,30}?)\s*"
        r"[^\d]{0,3}(" + AMOUNT_RE + r")"
    )
    rows = []
    for m in pattern.finditer(page2_text):
        period, posting, channel, amount = m.groups()
        channel = channel.strip()
        if channel.lower().startswith("please"):
            continue  # that's the "what remains unpaid" row, not a payment
        rows.append({
            "period": period.strip(), "posting_date": _parse_date(posting),
            "channel": channel, "amount": _num(amount),
        })
    return rows


def _meralco_unpaid_history(page2_text: str) -> List[Dict[str, Any]]:
    pattern = re.compile(
        r"(\d{2}\s+[A-Za-z]{3}-\d{2}\s+[A-Za-z]{3}\s+\d{4})\s*"
        r"(\d{2}\s+[A-Za-z]{3}\s+\d{4})"
        r"(Please pay[A-Za-z ]*?)\s*"
        r"[^\d]{0,3}(" + AMOUNT_RE + r")"
    )
    rows = []
    for m in pattern.finditer(page2_text):
        period, due, remarks, amount = m.groups()
        rows.append({
            "period": period.strip(), "due_date": _parse_date(due),
            "remarks": remarks.strip(), "amount": _num(amount),
        })
    return rows


def _parse_meralco(pages: List[str]) -> Dict[str, Any]:
    page1 = pages[0] if pages else ""
    page2 = pages[1] if len(pages) > 1 else ""
    full_text = page1 + "\n" + page2
    r = _empty_result()

    can_m = _find(r"\b(\d{10})\b", page1)
    r["account_number"] = can_m.group(1) if can_m else ""

    meter_m = _find(r"Meter No\.:\s*([A-Z0-9]+)", page1)
    r["meter_number"] = meter_m.group(1) if meter_m else ""

    due_m = _find(r"Due Date[\s\S]{0,80}?(" + DATE_RE_LONG + r")", page1)
    r["due_date"] = _parse_date(due_m.group(1)) if due_m else None

    period_m = _find(r"(" + DATE_RE_LONG + r")\s+to\s+(" + DATE_RE_LONG + r")\s+(" + DATE_RE_LONG + r")", page1)
    if period_m:
        r["period_start"] = _parse_date(period_m.group(1))
        r["period_end"] = _parse_date(period_m.group(2))
        r["bill_date"] = _parse_date(period_m.group(3))

    total_m = _find(r"Total Amount Due\s*[^\d]{0,3}(" + AMOUNT_RE + r")", page1)
    r["total_amount_due"] = _num(total_m.group(1)) if total_m else None

    prev_balance_m = _find(r"Remaining Balance from previous bill\s*(" + AMOUNT_RE + r")", page1)
    r["remaining_balance_previous"] = _num(prev_balance_m.group(1)) if prev_balance_m else 0.0

    period_charges_m = _find(r"Charges for this billing period\s*(" + AMOUNT_RE + r")", page1)
    r["period_charges"] = _num(period_charges_m.group(1)) if period_charges_m else None

    rate_m = _find(r"(" + AMOUNT_RE + r")\s*per\s*kWh", page1)
    r["rate_per_unit"] = _num(rate_m.group(1)) if rate_m else None

    consumption_m = _find(r"Actual Consumption[\s\S]{0,80}?(\d{1,6})\s*kWh", page1)
    r["consumption"] = _num(consumption_m.group(1)) if consumption_m else None
    r["consumption_unit"] = "kWh" if r["consumption"] is not None else ""

    invoice_m = _find(r"Billing Invoice\s*[\r\n]+No\.\s*(\d{6,20})", full_text) or \
                _find(r"No\.\s*(\d{6,20})", page1)
    r["reference_no"] = invoice_m.group(1) if invoice_m else ""

    r["service_address"] = _meralco_service_address(page2)
    r["charges_breakdown"] = _meralco_charge_breakdown(page1)
    r["payment_history"] = _meralco_payment_history(page2)
    r["unpaid_history"] = _meralco_unpaid_history(page2)
    r["currency_code"] = "PHP"
    return r


# ─── Converge (internet bill) ───────────────────────────────────────────────

def _converge_address(page1_text: str) -> str:
    m = _find(r"ADDRESS:\s*([\s\S]*?)TIN:", page1_text)
    if not m:
        return ""
    block = m.group(1)
    noise_patterns = [
        r"INVOICE DATE:\s*" + DATE_RE_SLASH,
        r"INVOICE NUMBER:\s*\d+",
        r"INVOICE PERIOD:", r"\(MONTHLY\)", r"\(WEEKLY\)",
        r"\d{7,15}\s*NUMBER:",
        r"ACCOUNT",
        r"NUMBER:",
    ]
    for pat in noise_patterns:
        block = re.sub(pat, " ", block)
    lines = [l.strip(" ,") for l in block.splitlines()]
    lines = [l for l in lines if l]
    return ", ".join(lines)


def _converge_plan_line(page2_text: str) -> Optional[Dict[str, Any]]:
    m = _find(r"^(.+?)\s+(" + DATE_RE_SLASH + r")\s+(" + DATE_RE_SLASH + r")\s+(" + AMOUNT_RE + r")$",
              page2_text)
    if not m:
        return None
    label, _f, _t, amount = m.groups()
    return {"label": label.strip(), "amount": _num(amount)}


def _converge_payment_history(page2_text: str) -> List[Dict[str, Any]]:
    pattern = re.compile(
        r"Payment\s+(\w+)\s+(\d+)\s+(" + DATE_RE_SLASH + r")\s+(" + AMOUNT_RE + r")"
    )
    rows = []
    for m in pattern.finditer(page2_text):
        method, receipt, date, amount = m.groups()
        rows.append({
            "period": "", "posting_date": _parse_date(date),
            "channel": f"{method.title()} (Receipt #{receipt})",
            "amount": _num(amount),
        })
    return rows


def _parse_converge(pages: List[str]) -> Dict[str, Any]:
    page1 = pages[0] if pages else ""
    page2 = pages[1] if len(pages) > 1 else ""
    r = _empty_result()

    acc_m = _find(r"ACCOUNT[\s\S]{0,15}?(\d{7,15})[\s\S]{0,15}?NUMBER:", page1)
    r["account_number"] = acc_m.group(1) if acc_m else ""

    inv_m = _find(r"INVOICE NUMBER:\s*(\d+)", page1)
    r["reference_no"] = inv_m.group(1) if inv_m else ""

    bill_date_m = _find(r"INVOICE DATE:\s*(" + DATE_RE_SLASH + r")", page1)
    r["bill_date"] = _parse_date(bill_date_m.group(1)) if bill_date_m else None

    period_m = _find(r"(" + DATE_RE_SLASH + r")\s*-\s*(" + DATE_RE_SLASH + r")", page1)
    if period_m:
        r["period_start"] = _parse_date(period_m.group(1))
        r["period_end"] = _parse_date(period_m.group(2))

    due_m = _find(r"Pay By\s*(" + DATE_RE_SLASH + r")", page1) or \
            _find(r"pay on \(or\) before\s*(" + DATE_RE_SLASH + r")", page1, re.IGNORECASE)
    r["due_date"] = _parse_date(due_m.group(1)) if due_m else None

    total_m = _find(r"TOTAL DUE \(OVERDUE \+ CURRENT\)\s*(" + AMOUNT_RE + r")", page1) or \
              _find(r"TOTAL DUE AMOUNT:\s*[\r\n]*\s*PHP\s*(" + AMOUNT_RE + r")", page1)
    r["total_amount_due"] = _num(total_m.group(1)) if total_m else None

    prev_balance_m = _find(r"Previous Balance \(Due Immediately\)\s*(-?" + AMOUNT_RE + r")", page1)
    r["remaining_balance_previous"] = _num(prev_balance_m.group(1)) if prev_balance_m else 0.0

    current_m = _find(r"TOTAL CURRENT CHARGES\s+(" + AMOUNT_RE + r")\s*$", page1)
    r["period_charges"] = _num(current_m.group(1)) if current_m else None

    r["service_address"] = _converge_address(page1)

    charges: Dict[str, float] = {}
    plan = _converge_plan_line(page2)
    recurring_m = _find(r"Recurring Charges\s*(" + AMOUNT_RE + r")", page1)
    if plan:
        charges[plan["label"]] = plan["amount"]
    elif recurring_m:
        charges["Recurring Charges"] = _num(recurring_m.group(1))
    vat_m = _find(r"\+\s*VAT[\s\S]{0,30}?(" + AMOUNT_RE + r")", page1)
    if vat_m:
        charges["VAT"] = _num(vat_m.group(1))
    r["charges_breakdown"] = charges

    r["payment_history"] = _converge_payment_history(page2)
    r["currency_code"] = "PHP"
    return r


def _estimate_due_16th(reference_date: datetime) -> datetime:
    """Arezzo Place Pasig's property management invoices (condo dues, water)
    consistently fall due on the 16th of the billing month regardless of
    the exact day the statement itself was printed — confirmed against two
    real statements (billed 02 Jun / due 16 Jun, and billed 04 Jun / due
    16 Jun). Used as a fallback whenever a scan's own printed due date
    can't be read reliably."""
    return reference_date.replace(day=16)


# ─── Condo / HOA "association dues" invoice ─────────────────────────────────
# These are typically scanned point-of-sale-style service invoices (one line
# item: "<ASSOCIATION> DUES BILL - MonYY"), often low-quality OCR, so only
# fields with an unambiguous, distinctively-formatted match are trusted.

def _parse_association_dues(pages: List[str]) -> Dict[str, Any]:
    page1 = pages[0] if pages else ""
    r = _empty_result()

    lines = [l for l in page1.splitlines() if l.strip()]
    if lines:
        r["provider"] = lines[0].strip()

    inv_m = _find(r"Invoice No\.?:?\s*(\d{4,12})", page1)
    r["reference_no"] = inv_m.group(1) if inv_m else ""

    unit_m = _find(r"UNIT\s*NO\.?:?\s*(\d+)", page1, re.IGNORECASE)
    r["account_number"] = unit_m.group(1) if unit_m else ""

    sold_to_m = _find(r"(\d{4,6})-([A-Z][A-Za-z,\. ]+?)\s*Invoice No", page1)
    customer = sold_to_m.group(2).strip(" .,") if sold_to_m else ""

    bill_m = _find(r"BILL\s*-\s*([A-Za-z]{3})(\d{2})\s+(" + AMOUNT_RE + r")", page1, re.IGNORECASE)
    amount = None
    if bill_m:
        mon_txt, yr_txt, amt_txt = bill_m.groups()
        amount = _num(amt_txt)
        try:
            period_start = datetime.strptime(f"01 {mon_txt} 20{yr_txt}", "%d %b %Y")
        except ValueError:
            period_start = None
        if period_start:
            r["period_start"] = period_start
            last_day = calendar.monthrange(period_start.year, period_start.month)[1]
            r["period_end"] = period_start.replace(day=last_day)
    r["total_amount_due"] = amount
    r["period_charges"] = amount

    # A "MonthDD,YYYY" run (e.g. "June02,2026") is the one date on this
    # layout that consistently survives OCR intact — it's the statement
    # date. The printed due date sits right next to garbled label text and
    # isn't reliably recoverable, so it's estimated instead (14 days after
    # the statement date is the standard grace period on these invoices)
    # and flagged for the user to double check.
    stmt_m = _find(r"([A-Za-z]{3,9})(\d{1,2}),(\d{4})", page1)
    statement_date = None
    if stmt_m:
        mon_txt, day_txt, yr_txt = stmt_m.groups()
        statement_date = _parse_date(f"{day_txt} {mon_txt[:3]} {yr_txt}")
    r["bill_date"] = statement_date
    if statement_date:
        r["due_date"] = _estimate_due_16th(statement_date)
        r["extra_notes"].append(
            "Due date estimated as the 16th of the billing month (this property's usual "
            "due-date policy) — the printed due date wasn't reliably readable on this "
            "scanned document. Please check the original and correct it above if needed."
        )

    ref_m = _find(r"PAYMENT\s*REFERENCE\s*NO\.?:?\s*(\d+)", page1, re.IGNORECASE)
    if ref_m:
        r["extra_notes"].append(f"Payment Reference No.: {ref_m.group(1)}")
    if customer:
        r["extra_notes"].append(f"Billed to: {customer}")

    if amount is not None:
        r["charges_breakdown"] = {"Condo/Association Dues": amount}

    r["currency_code"] = "PHP"
    return r


# ─── Community Property Managers Group (water billing) ─────────────────────
# Another Arezzo Place Pasig scanned service invoice, from the same family
# of templates as the condo dues one above but with a noticeably worse OCR
# text layer on this particular scan — most labels and their values land
# nowhere near each other, or are corrupted past safe recovery. Only a
# handful of fields have an unambiguous enough match to trust; everything
# else is deliberately left blank rather than guessed, and the user is
# told exactly that in the notes.

def _parse_community_property_bill(pages: List[str]) -> Dict[str, Any]:
    page1 = pages[0] if pages else ""
    r = _empty_result()
    r["provider"] = "Community Property Managers Group Inc."

    meter_m = _find(r"METERNO\s*([\dA-Za-z\^]{6,20})", page1, re.IGNORECASE)
    if meter_m:
        cleaned = re.sub(r"[^A-Za-z0-9]", "", meter_m.group(1))
        if cleaned:
            r["meter_number"] = cleaned
            r["extra_notes"].append(
                "Meter number read with low confidence from a poor scan — please verify "
                "it against the original document."
            )

    # "Total Sales (VAT Inclusive)" is printed as a bare digit run with no
    # decimal point surviving OCR on this template (e.g. "46809"); the last
    # two digits are always centavos. This is the one amount that matched
    # the actual printed total on a real statement, so it's preferred over
    # other, more visibly garbled amount fragments elsewhere on the page.
    total_m = _find(r"TotalSales\s*\(?\s*VAT\s*Inclusive\s*\)?\s*:?\s*(\d{3,7})", page1, re.IGNORECASE)
    if total_m:
        digits = total_m.group(1)
        amount = _num(f"{digits[:-2]}.{digits[-2:]}")
        r["total_amount_due"] = amount
        r["period_charges"] = amount
        if amount:
            r["charges_breakdown"] = {"Water Billing": amount}

    r["currency_code"] = "PHP"
    r["extra_notes"].append(
        "This scan's text layer was low quality — invoice date, due date, unit number, "
        "meter reading, and consumption figures couldn't be read reliably and were left "
        "blank. Please fill them in from the original document before saving."
    )
    return r


# ─── Generic fallback (unrecognized layout) ─────────────────────────────────

def _parse_generic(pages: List[str]) -> Dict[str, Any]:
    """Best-effort extraction for a layout we don't have a dedicated parser
    for — tries a handful of label patterns common across many bills.
    Never raises; missing fields are simply left blank for the review
    screen. `parse_utility_bill_pdf` itself still raises if nothing at all
    useful (an amount) could be found."""
    full_text = "\n".join(pages)
    r = _empty_result()

    acc_m = (_find(r"Account\s*(?:No\.?|Number)\s*[:\-]?\s*(\w[\w\-]{4,20})", full_text, re.IGNORECASE)
             or _find(r"\b(\d{9,13})\b", full_text))
    r["account_number"] = acc_m.group(1) if acc_m else ""

    ref_m = _find(r"(?:Invoice|Reference|Statement)\s*(?:No\.?|Number)\s*[:\-]?\s*(\w[\w\-]{4,20})",
                  full_text, re.IGNORECASE)
    r["reference_no"] = ref_m.group(1) if ref_m else ""

    for pat in (r"Due Date\s*[:\-]?\s*(" + DATE_RE_LONG + r")",
                r"Due Date\s*[:\-]?\s*(" + DATE_RE_SLASH + r")",
                r"Pay By\s*[:\-]?\s*(" + DATE_RE_SLASH + r")"):
        m = _find(pat, full_text, re.IGNORECASE)
        if m:
            r["due_date"] = _parse_date(m.group(1))
            break

    for pat in (r"(" + DATE_RE_LONG + r")\s+to\s+(" + DATE_RE_LONG + r")",
                r"(" + DATE_RE_SLASH + r")\s*-\s*(" + DATE_RE_SLASH + r")"):
        m = _find(pat, full_text)
        if m:
            r["period_start"] = _parse_date(m.group(1))
            r["period_end"] = _parse_date(m.group(2))
            break

    for pat in (r"Total\s*(?:Amount)?\s*Due\s*[:\-]?\s*[^\d]{0,4}(" + AMOUNT_RE + r")",
                r"Please\s*Pay\s*[:\-]?\s*[^\d]{0,4}(" + AMOUNT_RE + r")",
                r"Amount\s*Due\s*[:\-]?\s*[^\d]{0,4}(" + AMOUNT_RE + r")"):
        m = _find(pat, full_text, re.IGNORECASE)
        if m:
            r["total_amount_due"] = _num(m.group(1))
            break

    if "PHP" in full_text.upper() or "₱" in full_text:
        r["currency_code"] = "PHP"
    elif "$" in full_text or "USD" in full_text.upper():
        r["currency_code"] = "USD"

    return r


def parse_utility_bill_pdf(path: str) -> Dict[str, Any]:
    try:
        import pdfplumber
    except ImportError:
        raise BillParseError(
            "PDF parsing requires the 'pdfplumber' package. Install it with: "
            "pip install pdfplumber"
        ) from None

    try:
        with pdfplumber.open(path) as pdf:
            if not pdf.pages:
                raise BillParseError("This PDF has no pages.")
            pages = [(page.extract_text() or "") for page in pdf.pages]
    except BillParseError:
        raise
    except Exception as e:
        raise BillParseError(f"Couldn't read this PDF: {e}") from e

    full_text = "\n".join(pages)
    provider = _detect_provider(full_text)
    upper = full_text.upper()
    upper_nospace = re.sub(r"\s+", "", upper)

    is_association_dues = bool(re.search(
        r"CONDOMINIUM\s*CORPORATION|HOMEOWNERS\s*ASSOCIATION|"
        r"ASSOCIATION\s*DUES|CONDO\s*DUES", upper))
    is_community_property = "COMMUNITYPROPERTYMANAGERSGROUP" in upper_nospace

    if "MERALCO" in upper or "MANILA ELECTRIC COMPANY" in upper:
        result = _parse_meralco(pages)
    elif "CONVERGE" in upper:
        result = _parse_converge(pages)
    elif is_community_property:
        result = _parse_community_property_bill(pages)
    elif is_association_dues:
        result = _parse_association_dues(pages)
    else:
        result = _parse_generic(pages)

    # The static KNOWN_PROVIDERS lookup only covers a fixed list of
    # nationwide utilities — a per-building condo/HOA corporation isn't in
    # it, so only overwrite a parser's own (dynamically extracted) provider
    # name when the static lookup actually matched something.
    if provider:
        result["provider"] = provider
    result["source_file"] = path

    if result["total_amount_due"] is None and result["period_charges"] is None:
        raise BillParseError(
            "Couldn't find a total amount due or billing charges on this PDF — "
            "it may not be a recognized bill/statement layout. You can still add "
            "this bill manually with \"New Bill\"."
        )

    return result
