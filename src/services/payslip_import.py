"""
WealthMap – Payslip Import
Parses a WTW-style computer-generated payslip PDF (the "Payslip For : <period>"
layout with Taxable Earnings / Non-Taxable Earnings / Deductions / Loan
Balances / Year-To-Date Summary / Total Net Pay Summary tables) into a plain
structured dict, so the Settings/Transactions "Import Payslip" action can show
an editable preview before anything is written to the database.

This module only *reads* the PDF and returns data — it never touches the DB
or the app's services. The caller (UI layer) is responsible for turning the
parsed dict into a Transaction + TransactionCharge rows + LoanRepayment rows
after the user has reviewed/edited the preview.

Layout notes (why the parsing works the way it does):
The PDF has two side-by-side "amount" tables per row-band (Taxable Earnings /
Non-Taxable Earnings / Deductions, then lower down Loan Balances /
Year-To-Date Summary / Total Net Pay Summary). Naive text extraction
interleaves the two columns' wrapped lines, so we instead read word-level
bounding boxes (pdfplumber `extract_words`) and bucket each word into a
column by its x-position, then group words into logical rows by vertical
gap: wrapped label continuation lines sit close (~5pt) to the row's amount
line, while the gap between two different rows is consistently larger
(~10-11pt) in this template.
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, Any
from collections import defaultdict


class PayslipParseError(Exception):
    pass


AMOUNT_RE = re.compile(r"^-?[\d,]+\.\d{2}$")
HOURS_RE = re.compile(r"^-?\d+(\.\d+)?$")

# Column x-ranges (points), shared between the top table (Taxable Earnings /
# Non-Taxable Earnings / Deductions) and the bottom table (Loan Balances /
# Year-To-Date Summary / Total Net Pay Summary) — both tables use the same
# three-column grid.
COL_A_LABEL  = (0, 150)
COL_A_HOURS  = (150, 186)
COL_A_AMOUNT = (186, 235)
COL_B_LABEL  = (230, 350)
COL_B_AMOUNT = (350, 410)
COL_C_LABEL  = (405, 520)
COL_C_AMOUNT = (520, 580)

ROW_GAP_THRESHOLD = 7.5   # pt; bigger gap = new row, smaller = wrapped label continuation
LINE_CLUSTER_TOL   = 3    # pt; words within this many pts of 'top' are the same physical line

# Deduction labels that represent loan/insurance repayments rather than plain
# statutory or company deductions — these are offered for Loans-tab linking.
LOAN_DEDUCTION_LABELS = {"CRITICAL ILLNESS", "COMPANY EMERGENCY LOAN"}

# Deduction labels that are actual taxes (withholding tax) — imported as
# Tax transactions and surfaced in the Taxes tab.
STATUTORY_DEDUCTION_LABELS = {
    "WTAX", "WTAX VARIABLE",
}

# Deduction labels that are recurring contributions/bills rather than taxes
# — imported as expense transactions linked to a Bill record in the Bills
# tab (auto-created on first import), so each keeps its payment history.
BILL_DEDUCTION_LABELS = {
    "SSS CONTRIBUTION", "PHILHEALTH CONTRIBUTION", "SSS WISP", "HDMF",
}

# Deduction labels that fund an employee stock purchase (ESPP) — money that
# went toward buying company shares, not a bill or a tax. Imported as an
# Investment transaction and flagged for the Portfolio tab rather than
# Bills, since it represents a contribution toward an asset the employee
# now (partly) owns.
INVESTMENT_DEDUCTION_LABELS = {"ESPP DEDUCTION"}


def _num(text: Optional[str]) -> float:
    if not text:
        return 0.0
    return float(text.replace(",", ""))


def _cluster_lines(words, tol=LINE_CLUSTER_TOL):
    lines = defaultdict(list)
    keys = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        placed = False
        for k in keys:
            if abs(k - w["top"]) <= tol:
                lines[k].append(w)
                placed = True
                break
        if not placed:
            keys.append(w["top"])
            lines[w["top"]].append(w)
    return [(k, lines[k]) for k in sorted(lines.keys())]


def _in_range(x, rng):
    return rng[0] <= x < rng[1]


def _extract_rows(words, label_x, hours_x, amount_x, y_min, y_max,
                   gap_thresh=ROW_GAP_THRESHOLD):
    """Returns a list of (label, hours_or_None, amount_str_or_None) for one
    column of one table band, reconstructing rows whose label wraps across
    multiple lines (see module docstring)."""
    section = [w for w in words if y_min <= w["top"] <= y_max]
    lines = _cluster_lines(section)

    groups: List[list] = []
    cur: list = []
    prev_top = None
    for top, line_words in lines:
        if prev_top is not None and (top - prev_top) > gap_thresh:
            groups.append(cur)
            cur = []
        cur.append((top, line_words))
        prev_top = top
    if cur:
        groups.append(cur)

    rows = []
    for group in groups:
        label_words, amount, hours = [], None, None
        for _top, line_words in group:
            for w in sorted(line_words, key=lambda w: w["x0"]):
                txt = w["text"]
                if _in_range(w["x0"], amount_x) and AMOUNT_RE.match(txt):
                    amount = txt
                elif hours_x and _in_range(w["x0"], hours_x) and HOURS_RE.match(txt):
                    hours = txt
                elif _in_range(w["x0"], label_x):
                    label_words.append(txt)
        label = " ".join(label_words).strip()
        if label:
            rows.append((label, hours, amount))
    return rows


def _find_words(words, y0, y1, x0=None, x1=None):
    out = []
    for w in words:
        if y0 <= w["top"] <= y1:
            if x0 is not None and w["x0"] < x0:
                continue
            if x1 is not None and w["x0"] > x1:
                continue
            out.append(w)
    return sorted(out, key=lambda w: (w["top"], w["x0"]))


def parse_payslip_pdf(path) -> Dict[str, Any]:
    """Parses the given payslip PDF and returns a structured dict:

    {
      "employee": {code, name, location, team, sss_number, hdmf_number,
                   tin_number, philhealth_number, segment, date_hired},
      "company": str,
      "currency": str,                      # e.g. "PHP"
      "period_start": datetime | None,
      "period_end": datetime | None,
      "taxable_earnings": [{"label", "hours", "amount"}, ...],
      "non_taxable_earnings": [...],
      "deductions": [{"label", "amount", "is_loan", "is_statutory",
                      "is_bill", "is_investment"}, ...],
      "totals": {"taxable": float, "non_taxable": float, "deductions": float},
      "loan_balances": [{"label", "amount"}, ...],
      "ytd_summary": [{"label", "amount"}, ...],
      "net_pay": float,
      "gross_pay": float,                   # taxable + non-taxable
    }

    Raises PayslipParseError if the PDF doesn't look like this payslip
    template (so the caller can fall back to manual entry).
    """
    try:
        import pdfplumber
    except ImportError as e:
        raise PayslipParseError(
            "Payslip import needs the 'pdfplumber' Python package. "
            "Install it with:  pip install -r requirements.txt"
        ) from e

    with pdfplumber.open(str(path)) as pdf:
        if not pdf.pages:
            raise PayslipParseError("The PDF has no pages.")
        page = pdf.pages[0]
        words = page.extract_words(use_text_flow=False, keep_blank_chars=False)
        tables = page.extract_tables()

    if not words:
        raise PayslipParseError("No readable text found in this PDF (is it a scanned image?).")

    full_text = " ".join(w["text"] for w in words)
    if "Payslip" not in full_text or "TOTAL" not in full_text.upper():
        raise PayslipParseError("This doesn't look like a recognized payslip layout.")

    # ── Header: company name + pay period ───────────────────────────────
    header_words = _find_words(words, 0, 90)
    company_words = [w["text"] for w in header_words if w["x0"] < 430 and w["top"] < 70]
    company = " ".join(company_words).replace(" Company", "").strip() or "Company"

    period_words = [w["text"] for w in header_words if w["x0"] > 430]
    period_text = " ".join(period_words)
    period_match = re.search(
        r"(\d{1,2}\s+\w+\s+\d{4})\s+TO\s+(\d{1,2})\s+(\w+)\s+(\d{4})",
        period_text
    )
    period_start = period_end = None
    if period_match:
        try:
            period_start = datetime.strptime(period_match.group(1), "%d %b %Y")
        except ValueError:
            pass
        try:
            period_end = datetime.strptime(
                f"{period_match.group(2)} {period_match.group(3)} {period_match.group(4)}",
                "%d %b %Y"
            )
        except ValueError:
            pass

    currency_match = re.search(r"Amount in ([A-Z]{3})", full_text)
    currency = currency_match.group(1) if currency_match else "PHP"

    # ── Employee info block (this table renders cleanly via extract_tables) ──
    employee = {}
    if tables:
        emp_table = tables[0]
        label_map = {
            "Employee Code": "code", "Employee Name": "name",
            "Location": "location", "Team Description": "team",
            "SSS Number": "sss_number", "HDMF Number": "hdmf_number",
            "TIN Number": "tin_number", "Philhealth Number": "philhealth_number",
            "Segment": "segment", "Date Hired": "date_hired",
        }
        for row in emp_table:
            cells = [c.strip() if c else "" for c in row]
            for i in range(0, len(cells) - 1, 2):
                label, value = cells[i], cells[i + 1]
                key = label_map.get(label)
                if key:
                    employee[key] = value

    # ── Taxable / Non-taxable / Deductions (top table band) ────────────
    top_rows = _extract_rows(words, COL_A_LABEL, COL_A_HOURS, COL_A_AMOUNT, 215, 382)
    taxable_earnings = [
        {"label": lbl, "hours": _num(hrs) if hrs else None, "amount": _num(amt)}
        for lbl, hrs, amt in top_rows if amt is not None
    ]
    non_taxable_earnings = [
        {"label": lbl, "amount": _num(amt)}
        for lbl, _hrs, amt in _extract_rows(words, COL_B_LABEL, None, COL_B_AMOUNT, 215, 382)
        if amt is not None and "TOTAL" not in lbl.upper()
    ]
    deduction_rows = [
        (lbl, amt) for lbl, _hrs, amt in
        _extract_rows(words, COL_C_LABEL, None, COL_C_AMOUNT, 215, 382)
        if amt is not None
    ]
    deductions = []
    for lbl, amt in deduction_rows:
        norm = re.sub(r"\s+", " ", lbl).strip().upper()
        deductions.append({
            "label": re.sub(r"\s+", " ", lbl).strip(),
            "amount": _num(amt),
            "is_loan": norm in LOAN_DEDUCTION_LABELS,
            "is_statutory": norm in STATUTORY_DEDUCTION_LABELS,
            "is_bill": norm in BILL_DEDUCTION_LABELS,
            "is_investment": norm in INVESTMENT_DEDUCTION_LABELS,
        })

    # ── Totals row for the top table band ───────────────────────────────
    totals = {"taxable": 0.0, "non_taxable": 0.0, "deductions": 0.0}
    for _lbl, _hrs, amt in _extract_rows(words, COL_A_LABEL, None, COL_A_AMOUNT, 383, 393):
        if amt is not None:
            totals["taxable"] = _num(amt)
    for _lbl, _hrs, amt in _extract_rows(words, COL_B_LABEL, None, COL_B_AMOUNT, 383, 393):
        if amt is not None:
            totals["non_taxable"] = _num(amt)
    for _lbl, _hrs, amt in _extract_rows(words, COL_C_LABEL, None, COL_C_AMOUNT, 383, 393):
        if amt is not None:
            totals["deductions"] = _num(amt)

    # Fall back to summing line items if the totals row wasn't found for
    # some reason (still gives a correct, just independently-derived, total).
    if not totals["taxable"] and taxable_earnings:
        totals["taxable"] = round(sum(r["amount"] for r in taxable_earnings), 2)
    if not totals["deductions"] and deductions:
        totals["deductions"] = round(sum(r["amount"] for r in deductions), 2)

    # ── Loan Balances / Year-To-Date / Net Pay Summary (bottom table band) ──
    loan_balances = [
        {"label": re.sub(r"\s+", " ", lbl).strip(), "amount": _num(amt)}
        for lbl, _hrs, amt in _extract_rows(words, COL_A_LABEL, None, COL_A_AMOUNT, 438, 567)
        if amt is not None
    ]
    ytd_summary = [
        {"label": re.sub(r"\s+", " ", lbl).strip(), "amount": _num(amt)}
        for lbl, _hrs, amt in _extract_rows(words, COL_B_LABEL, None, COL_B_AMOUNT, 438, 567)
        if amt is not None
    ]
    net_pay = 0.0
    for lbl, _hrs, amt in _extract_rows(words, COL_C_LABEL, None, COL_C_AMOUNT, 438, 567):
        if amt is not None and "NET SALARY" in lbl.upper():
            net_pay = _num(amt)

    if not net_pay:
        net_pay = round(totals["taxable"] + totals["non_taxable"] - totals["deductions"], 2)

    return {
        "employee": employee,
        "company": company,
        "currency": currency,
        "period_start": period_start,
        "period_end": period_end,
        "taxable_earnings": taxable_earnings,
        "non_taxable_earnings": non_taxable_earnings,
        "deductions": deductions,
        "totals": totals,
        "loan_balances": loan_balances,
        "ytd_summary": ytd_summary,
        "net_pay": net_pay,
        "gross_pay": round(totals["taxable"] + totals["non_taxable"], 2),
        "source_file": str(path),
    }


def build_earnings_notes(parsed: Dict[str, Any]) -> str:
    """A human-readable itemized breakdown of the earnings side, meant to
    go in the created Transaction's notes field (there's no per-line-item
    storage for earnings in the data model, unlike deductions which become
    TransactionCharge rows)."""
    lines = ["Payslip earnings breakdown:"]
    for row in parsed.get("taxable_earnings", []):
        hrs = f"  ({row['hours']} hrs)" if row.get("hours") else ""
        lines.append(f"  • {row['label']}: {row['amount']:,.2f}{hrs}")
    for row in parsed.get("non_taxable_earnings", []):
        lines.append(f"  • {row['label']} (non-taxable): {row['amount']:,.2f}")
    period = ""
    if parsed.get("period_start") and parsed.get("period_end"):
        period = (f"\nPay period: {parsed['period_start'].strftime('%d %b %Y')} – "
                  f"{parsed['period_end'].strftime('%d %b %Y')}")
    return "\n".join(lines) + period
