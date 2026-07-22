"""
WealthMap – Import Payslip dialog

Lets the user pick a payslip PDF, shows a fully editable preview of
everything that was read from it (account to deposit into, date, and one
editable row per taxable earning, non-taxable earning, and deduction —
each of which becomes its own individual transaction), and only writes
anything to the database once the user clicks "Import" — matching the
"review before it's filled in" requirement.

Each taxable/non-taxable earning line is imported as its own SALARY
transaction; each deduction line becomes its own TAX or FEE transaction
(loan-linked deductions also record a loan repayment). The transactions
are created sequentially, in the order they appear on the payslip, and
every one is tagged with the Payslip it came from so the new Taxes and
Payslip tabs can find them.

Used from both the Transactions panel toolbar and Settings > Data
Management, so it lives in its own module rather than inside either.
"""

from datetime import datetime as _dt
from tkinter import messagebox, filedialog
import customtkinter as ctk

from src.models.database import TransactionType
from src.services.payslip_import import parse_payslip_pdf, PayslipParseError
from src.ui.widgets import (
    Modal, make_entry, make_combo, attach_currency_tooltip, CurrencySearchEntry
)
from src.ui.theme import theme

CREATE_NEW_LOAN = "＋ Create new loan"
DONT_LINK_LOAN = "Don't link (deduction line only)"


def open_payslip_import_dialog(parent, ctx, on_done=None):
    """Opens a file picker, parses the chosen PDF, then shows the
    review/edit modal. `on_done` (optional) is called with no args after a
    successful import, so callers can refresh whatever list is on screen."""
    path = filedialog.askopenfilename(
        title="Select Payslip PDF",
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
    )
    if not path:
        return

    try:
        parsed = parse_payslip_pdf(path)
    except PayslipParseError as e:
        messagebox.showerror("Couldn't Read Payslip", str(e), parent=parent)
        return
    except Exception as e:
        messagebox.showerror("Couldn't Read Payslip",
                              f"Unexpected error reading this PDF:\n{e}", parent=parent)
        return

    _show_review_modal(parent, ctx, parsed, on_done=on_done)


def _show_review_modal(parent, ctx, parsed, on_done=None):
    accounts = ctx.account.get_all()
    if not accounts:
        messagebox.showerror("No Accounts", "Create an account first.", parent=parent)
        return
    acc_names = [a.name for a in accounts]
    currencies = [c.code for c in ctx.currency.get_all()]
    loans = ctx.loan.get_all(include_settled=False)
    loan_names = [l.contact_name for l in loans]

    modal = Modal(parent, "Import Payslip — Review & Confirm", width=720, height=860)

    emp = parsed.get("employee", {})
    period_txt = ""
    if parsed.get("period_start") and parsed.get("period_end"):
        period_txt = (f"{parsed['period_start'].strftime('%d %b %Y')} – "
                       f"{parsed['period_end'].strftime('%d %b %Y')}")
    info_lines = [
        f"{parsed.get('company', 'Company')}" + (f"  •  {period_txt}" if period_txt else ""),
        f"{emp.get('name', '')}" + (f"  (Employee Code {emp['code']})" if emp.get("code") else ""),
    ]
    ctk.CTkLabel(modal.body, text="\n".join(l for l in info_lines if l.strip()),
                 font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                 justify="left", anchor="w").pack(fill="x", pady=(0, 12))

    # ── Import mode ──────────────────────────────────────────────────────
    # Available every time — including when a payslip for this period was
    # already imported before — so re-imports or corrections aren't blocked.
    MODE_FULL = "Full Import"
    MODE_ARCHIVE = "Payslip Only"
    ctk.CTkLabel(modal.body, text="Import Mode", font=("Segoe UI", 12),
                 text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")
    mode_seg = ctk.CTkSegmentedButton(modal.body, values=[MODE_FULL, MODE_ARCHIVE])
    mode_seg.set(MODE_FULL)
    mode_seg.pack(fill="x", pady=(2, 4))
    mode_note = ctk.CTkLabel(modal.body, text="", font=("Segoe UI", 11),
                             text_color=theme.TEXT_SEC, wraplength=660,
                             justify="left", anchor="w")
    mode_note.pack(fill="x", pady=(0, 10))

    def _update_mode_note(*_a):
        if mode_seg.get() == MODE_FULL:
            mode_note.configure(
                text="Each earning and deduction line below becomes its own individual "
                     "transaction (Salary, Tax, Fee, or a Bill payment), in the order shown — "
                     "and shows up in Transactions, Taxes, and Bills. Loan-linked deductions "
                     "also record a repayment.")
        else:
            mode_note.configure(
                text="Only archives the payslip itself (visible in the Payslips tab, with its "
                     "full breakdown) — no transactions, tax records, bill payments, or loan "
                     "repayments are created anywhere else in the app.")
    mode_seg.configure(command=_update_mode_note)
    _update_mode_note()

    acc_c = modal.add_field("Deposit Into Account", lambda p: make_combo(p, acc_names))
    acc_c.set(acc_names[0])

    default_currency = parsed.get("currency") if parsed.get("currency") in currencies else (
        currencies[0] if currencies else None)
    cur_c = modal.add_field("Currency", lambda p: CurrencySearchEntry(
        p, ctx, width=120, initial_code=default_currency))
    attach_currency_tooltip(cur_c, ctx)

    default_date = (parsed.get("period_end") or parsed.get("period_start"))
    date_e = modal.add_field("Date (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
    if default_date:
        date_e.insert(0, default_date.strftime("%Y-%m-%d"))

    period_label = ""
    if parsed.get("period_start") and parsed.get("period_end"):
        period_label = f"{parsed['period_start'].strftime('%b %Y')}"

    payee_e = modal.add_field("Payee / Employer", lambda p: make_entry(p, "Employer"))
    payee_e.insert(0, parsed.get("company", ""))

    # ── Generic editable line-item section builder ─────────────────────────
    all_rows = {"taxable_earning": [], "non_taxable_earning": [], "deduction": []}

    def add_section(title, section_key, source_rows, show_kind=False, show_loan=False):
        ctk.CTkLabel(modal.body, text=title, font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(10, 6))
        container = ctk.CTkFrame(modal.body, fg_color="transparent")
        container.pack(fill="x", pady=(0, 4))
        rows_list = all_rows[section_key]

        def add_row(d):
            row = ctk.CTkFrame(container, fg_color=theme.BG_HOVER, corner_radius=8)
            row.pack(fill="x", pady=2)

            top_row = ctk.CTkFrame(row, fg_color="transparent")
            top_row.pack(fill="x", padx=6, pady=(6, 2))

            desc_e2 = make_entry(top_row, "Description")
            desc_e2.insert(0, d.get("label", ""))
            desc_e2.pack(side="left", fill="x", expand=True, padx=(0, 4))

            kind_c2 = None
            if show_kind:
                kind_c2 = make_combo(top_row, ["Fee", "Tax", "Bill", "Investment"], width=90)
                if d.get("is_investment"):
                    kind_c2.set("Investment")
                elif d.get("is_bill"):
                    kind_c2.set("Bill")
                elif d.get("is_statutory"):
                    kind_c2.set("Tax")
                else:
                    kind_c2.set("Fee")
                kind_c2.pack(side="left", padx=4)

            amt_e2 = make_entry(top_row, "Amount", width=100)
            amt_e2.insert(0, f"{d.get('amount', 0.0):.2f}")
            amt_e2.pack(side="left", padx=4)

            entry = {"row": row, "description": desc_e2, "kind": kind_c2,
                     "amount": amt_e2, "loan_combo": None, "source": d}

            def remove_row():
                entry["row"].destroy()
                if entry in rows_list:
                    rows_list.remove(entry)

            ctk.CTkButton(top_row, text="✕", width=28, height=28,
                          fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 12),
                          command=remove_row).pack(side="left", padx=(4, 0))

            if show_loan and d.get("is_loan"):
                loan_row = ctk.CTkFrame(row, fg_color="transparent")
                loan_row.pack(fill="x", padx=6, pady=(0, 6))
                ctk.CTkLabel(loan_row, text="Link to Loan:", font=("Segoe UI", 11),
                             text_color=theme.TEXT_SEC).pack(side="left", padx=(0, 6))
                options = [CREATE_NEW_LOAN] + loan_names + [DONT_LINK_LOAN]
                loan_c = make_combo(loan_row, options, width=280)
                match = next((n for n in loan_names
                              if n.strip().lower() == d.get("label", "").strip().lower()), None)
                loan_c.set(match if match else CREATE_NEW_LOAN)
                loan_c.pack(side="left", fill="x", expand=True)
                entry["loan_combo"] = loan_c

                bal = next((lb["amount"] for lb in parsed.get("loan_balances", [])
                            if lb["label"].strip().lower() == d.get("label", "").strip().lower()), None)
                if bal is not None:
                    ctk.CTkLabel(row, text=f"Payslip shows remaining balance: {bal:,.2f}",
                                 font=("Segoe UI", 10), text_color=theme.TEXT_SEC
                                 ).pack(anchor="w", padx=6, pady=(0, 6))

            rows_list.append(entry)
            return entry

        for d in source_rows:
            add_row(d)

        if not source_rows:
            ctk.CTkLabel(container, text="(none found on this payslip)",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w", pady=2)

    add_section("💰 Taxable Earnings (each becomes its own Salary transaction)",
                "taxable_earning", parsed.get("taxable_earnings", []))
    add_section("🧾 Non-Taxable Earnings (each becomes its own Salary transaction)",
                "non_taxable_earning", parsed.get("non_taxable_earnings", []))
    add_section("💸 Deductions (each becomes its own transaction — Fee, Tax, Bill, or "
                "Investment; Bill-kind ones link to the Bills tab, Investment-kind ones are "
                "for share purchases like ESPP, loan-linked ones also record a repayment)",
                "deduction", parsed.get("deductions", []), show_kind=True, show_loan=True)

    total_earn = sum(d["amount"] for d in parsed.get("taxable_earnings", [])) + \
                 sum(d["amount"] for d in parsed.get("non_taxable_earnings", []))
    total_ded = sum(d["amount"] for d in parsed.get("deductions", []))
    net_lbl = ctk.CTkLabel(
        modal.body,
        text=f"Net pay (from payslip): {parsed.get('net_pay', 0.0):,.2f}   "
             f"(earnings {total_earn:,.2f} − deductions {total_ded:,.2f})",
        font=("Segoe UI", 11), text_color=theme.TEXT_SEC, anchor="w"
    )
    net_lbl.pack(fill="x", pady=(4, 10))

    attach_var = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(modal.body, text="Attach the original payslip PDF to this import",
                     variable=attach_var, font=("Segoe UI", 12),
                     text_color=theme.TEXT_PRI).pack(anchor="w", pady=(4, 8))

    def do_import():
        try:
            account = next((a for a in accounts if a.name == acc_c.get()), None)
            if not account:
                messagebox.showerror("Missing Account", "Choose an account to deposit into.", parent=modal)
                return
            try:
                tx_date = _dt.strptime(date_e.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid Date", "Use the format YYYY-MM-DD.", parent=modal)
                return
            cur_c.resolve()
            currency_code = cur_c.get()
            payee = payee_e.get().strip()
            archive_only = mode_seg.get() == MODE_ARCHIVE

            # 1) Payslip header first — every transaction/line item created
            #    below is tagged back to it. Available every time, even if
            #    a payslip for this period was already imported before.
            payslip = ctx.payslip.create_header(parsed, account=account)

            # 2) Taxable + non-taxable earnings. In Full Import mode, each
            #    becomes its own Salary transaction, created sequentially in
            #    payslip order. In Payslip Only mode, only the line item is
            #    archived — no transaction is created anywhere else.
            for section, label_prefix in (
                ("taxable_earning", "Salary"),
                ("non_taxable_earning", "Salary (Non-Taxable)"),
            ):
                for entry in all_rows[section]:
                    try:
                        amt = float(entry["amount"].get().replace(",", ""))
                    except ValueError:
                        amt = 0.0
                    if amt == 0:
                        continue
                    desc = entry["description"].get().strip() or entry["source"].get("label", label_prefix)
                    hours = entry["source"].get("hours")
                    tx = None
                    if not archive_only:
                        tx = ctx.transaction.add(
                            account, TransactionType.SALARY, amt,
                            description=desc, category="Salary / Income",
                            payee=payee, transaction_date=tx_date,
                            currency_code=currency_code,
                            notes=(f"{hours:g} hrs" if hours else ""),
                            payslip_id=payslip.id,
                        )
                    ctx.payslip.add_item(payslip, section, desc, amt, hours=hours, transaction=tx)

            # 3) Deductions. In Full Import mode, each becomes its own
            #    transaction: Tax → TAX (Taxes tab), Bill → EXPENSE linked to
            #    a Bill record (Bills tab, auto-created on first import so it
            #    accumulates payment history), anything else → FEE.
            #    Loan-linked ones also record a repayment against Loans. In
            #    Payslip Only mode, only the line item is archived — nothing
            #    is created in Transactions, Taxes, Bills, or Loans.
            bills_cache = {b.name.strip().lower(): b
                           for b in ctx.bill.get_all(include_inactive=True)}
            for entry in all_rows["deduction"]:
                try:
                    amt = float(entry["amount"].get().replace(",", ""))
                except ValueError:
                    amt = 0.0
                if amt == 0:
                    continue
                desc = entry["description"].get().strip() or entry["source"].get("label", "Deduction")
                kind = entry["kind"].get() if entry["kind"] is not None else "Fee"

                if archive_only:
                    ctx.payslip.add_item(payslip, "deduction", desc, amt)
                    continue

                bill = None
                if kind == "Bill":
                    tx_type, category = TransactionType.EXPENSE, "Bills & Utilities"
                    bill = bills_cache.get(desc.strip().lower())
                    if bill is None:
                        bill = ctx.bill.create(
                            name=desc, amount=amt, currency_code=currency_code,
                            frequency="monthly", account=account,
                            payee=parsed.get("company", ""),
                            category="Payroll Contribution",
                            notes=f"Auto-created from payslip import ({period_label})",
                            payslip_id=payslip.id,
                        )
                        bills_cache[desc.strip().lower()] = bill
                    category = bill.category or category
                elif kind == "Tax":
                    tx_type, category = TransactionType.TAX, "Payroll Deduction"
                elif kind == "Investment":
                    # Money that funded an employee stock purchase (ESPP) —
                    # this app can't record the actual share trade from a
                    # payslip alone (no price/quantity), so it's recorded
                    # as an Investment transaction and left for the user to
                    # match against the resulting purchase in Portfolio.
                    tx_type, category = TransactionType.INVESTMENT, "Portfolio / ESPP Contribution"
                else:
                    tx_type, category = TransactionType.FEE, "Payroll Deduction"

                ded_tx = ctx.transaction.add(
                    account, tx_type, amt,
                    description=desc, category=category,
                    payee=payee, transaction_date=tx_date,
                    currency_code=currency_code,
                    payslip_id=payslip.id,
                    bill_id=bill.id if bill else None,
                    notes=("Funded an employee stock purchase — record the resulting share "
                           "trade in Portfolio once you know the purchase price/quantity."
                           if kind == "Investment" else ""),
                )
                ctx.payslip.add_item(payslip, "deduction", desc, amt, transaction=ded_tx)
                if bill is not None:
                    ctx.bill.record_payment(bill, paid_on=tx_date)

                if entry["loan_combo"] is not None:
                    choice = entry["loan_combo"].get()
                    if choice == DONT_LINK_LOAN:
                        continue
                    if choice == CREATE_NEW_LOAN:
                        balance = next(
                            (lb["amount"] for lb in parsed.get("loan_balances", [])
                             if lb["label"].strip().lower() == entry["source"].get("label", "").strip().lower()),
                            None
                        )
                        principal = (balance + amt) if balance is not None else amt
                        loan = ctx.loan.create(
                            contact_name=desc, direction="i_owe",
                            principal=principal, currency_code=currency_code,
                            description=f"Auto-created from payslip import ({period_label})",
                            contact_info=parsed.get("company", ""),
                            payslip_id=payslip.id,
                        )
                    else:
                        loan = next((l for l in loans if l.contact_name == choice), None)
                    if loan:
                        ctx.loan.record_repayment(
                            loan, amt, repaid_on=tx_date,
                            payslip_id=payslip.id,
                            notes=f"Payslip deduction — {period_label}".strip(" —")
                        )

            # 4) Informational-only rows — loan balances and the Year-To-Date
            #    summary don't affect any account, so they're archived as
            #    line items with no transaction attached.
            for lb in parsed.get("loan_balances", []):
                ctx.payslip.add_item(payslip, "loan_balance", lb.get("label", ""), lb.get("amount", 0.0))
            for row in parsed.get("ytd_summary", []):
                ctx.payslip.add_item(payslip, "ytd_summary", row.get("label", ""), row.get("amount", 0.0))

            if attach_var.get():
                try:
                    ctx.attachment.save_file(
                        parsed["source_file"], ctx.session, "payslip", payslip.id,
                        description="Payslip"
                    )
                except Exception:
                    pass  # non-fatal — the transactions themselves already succeeded

            modal.destroy()
            if archive_only:
                summary_msg = (f"Net pay {parsed.get('net_pay', 0.0):,.2f} {currency_code} — "
                               "archived to the Payslips tab only. No transactions, tax "
                               "records, bill payments, or loan repayments were created.")
            else:
                summary_msg = (f"Net pay {parsed.get('net_pay', 0.0):,.2f} {currency_code} — "
                               "each earning and deduction line was added as its own transaction.")
            messagebox.showinfo("Payslip Imported", summary_msg, parent=parent)
            if on_done:
                on_done()
        except Exception as e:
            messagebox.showerror("Import Failed", str(e), parent=modal)

    modal.add_buttons("Import", do_import, cancel_text="Cancel")


# ── Viewing saved payslips ─────────────────────────────────────────────────

SECTION_TITLES = {
    "taxable_earning":     "💰 Taxable Earnings",
    "non_taxable_earning": "🧾 Non-Taxable Earnings",
    "deduction":           "💸 Deductions",
    "loan_balance":        "🏦 Loan Balances",
    "ytd_summary":         "📅 Year-To-Date Summary (as printed on this payslip)",
}


# Keyword → how to compute the real (calculated) year-to-date figure that
# corresponds to a given "as printed" YTD summary label. Matched against
# the printed label (uppercased) as a substring test, in order — first
# match wins. Anything not matched here (e.g. "PREV EMPLOYER INCOME",
# which this app doesn't track) is shown as printed-only.
_YTD_LABEL_MATCHERS = [
    ("NET PAY",         lambda ytd: ytd["totals"]["net"]),
    ("NON TAXABLE",     lambda ytd: ytd["totals"]["non_taxable"]),
    ("TAXABLE",         lambda ytd: ytd["totals"]["taxable"]),
    ("PHILHEALTH",      lambda ytd: sum(b["total"] for lbl, b in ytd["sections"]["deduction"].items()
                                        if "PHILHEALTH" in lbl.upper())),
    ("HDMF",            lambda ytd: sum(b["total"] for lbl, b in ytd["sections"]["deduction"].items()
                                        if "HDMF" in lbl.upper())),
    ("WTAX",            lambda ytd: sum(b["total"] for lbl, b in ytd["sections"]["deduction"].items()
                                        if "WTAX" in lbl.upper())),
    ("SSS",             lambda ytd: sum(b["total"] for lbl, b in ytd["sections"]["deduction"].items()
                                        if "SSS" in lbl.upper())),
]


def _calculated_ytd_value(ctx, payslip, label: str):
    """The real, calculated year-to-date figure matching a printed YTD
    summary label — computed live from every payslip imported for that
    year (see PayslipService.ytd_summary), not just what's printed on this
    one document. Returns None when this label isn't something the app
    tracks a computed equivalent for (e.g. "Prev Employer" figures)."""
    if ctx is None:
        return None
    upper = (label or "").upper()
    for keyword, fn in _YTD_LABEL_MATCHERS:
        if keyword in upper:
            year = (payslip.period_end or payslip.period_start or payslip.created_at)
            if year is None:
                return None
            ytd = ctx.payslip.ytd_summary(year.year)
            try:
                return fn(ytd)
            except Exception:
                return None
    return None


def _render_payslip_sections(container, payslip, on_open_transaction=None, ctx=None):
    for section, title in SECTION_TITLES.items():
        items = payslip.items_in(section)
        if not items:
            continue
        ctk.CTkLabel(container, text=title, font=("Segoe UI", 13, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(10, 4))
        if section == "ytd_summary" and ctx is not None:
            ctk.CTkLabel(container,
                         text="Bigger figure = calculated from every payslip imported for the "
                              "year so far. Smaller figure below = exactly what this payslip prints.",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC,
                         wraplength=520, justify="left", anchor="w").pack(fill="x", pady=(0, 4))
        card = ctk.CTkFrame(container, fg_color=theme.BG_HOVER, corner_radius=8)
        card.pack(fill="x", pady=(0, 4))
        total = 0.0
        for it in items:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=3)
            label_txt = it.label
            if it.hours:
                label_txt += f"  ({it.hours:g} hrs)"
            if on_open_transaction and it.transaction_id:
                ctk.CTkButton(row, text=label_txt, font=("Segoe UI", 12),
                              fg_color="transparent", hover_color=theme.BG_SELECTED,
                              text_color=theme.ACCENT, anchor="w",
                              command=lambda tid=it.transaction_id: on_open_transaction(tid)
                              ).pack(side="left", fill="x", expand=True)
            else:
                ctk.CTkLabel(row, text=label_txt, font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI, anchor="w").pack(side="left", fill="x", expand=True)

            if section == "ytd_summary":
                calc = _calculated_ytd_value(ctx, payslip, it.label)
                vals = ctk.CTkFrame(row, fg_color="transparent")
                vals.pack(side="right")
                if calc is not None:
                    ctk.CTkLabel(vals, text=f"{calc:,.2f}", font=("Segoe UI", 13, "bold"),
                                 text_color=theme.GOLD, anchor="e").pack(anchor="e")
                    ctk.CTkLabel(vals, text=f"as printed: {it.amount:,.2f}",
                                 font=("Segoe UI", 9), text_color=theme.TEXT_SEC,
                                 anchor="e").pack(anchor="e")
                else:
                    ctk.CTkLabel(vals, text=f"{it.amount:,.2f}", font=("Segoe UI", 12),
                                 text_color=theme.TEXT_PRI, anchor="e").pack(anchor="e")
                    ctk.CTkLabel(vals, text="printed only — not tracked",
                                 font=("Segoe UI", 9), text_color=theme.TEXT_SEC,
                                 anchor="e").pack(anchor="e")
            else:
                ctk.CTkLabel(row, text=f"{it.amount:,.2f}", font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="right")
            total += it.amount
        if len(items) > 1 and section != "ytd_summary":
            total_row = ctk.CTkFrame(card, fg_color="transparent")
            total_row.pack(fill="x", padx=10, pady=(2, 6))
            ctk.CTkLabel(total_row, text="Total", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_SEC, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(total_row, text=f"{total:,.2f}", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_SEC).pack(side="right")


def show_payslip_viewer(parent, payslip, ctx=None, app=None):
    """Read-only breakdown of a saved Payslip — every taxable/non-taxable
    earning, deduction, loan balance, and YTD summary figure exactly as
    imported. If `ctx`/`app` are given, earning and deduction rows that
    produced a transaction are clickable and open that transaction's full
    edit dialog."""
    modal = Modal(parent, "Payslip Details", width=620, height=760)

    period = ""
    if payslip.period_start and payslip.period_end:
        period = (f"{payslip.period_start.strftime('%d %b %Y')} – "
                  f"{payslip.period_end.strftime('%d %b %Y')}")
    header_lines = [
        payslip.company or "",
        f"{payslip.employee_name}" + (f"  (Code {payslip.employee_code})" if payslip.employee_code else ""),
        period,
        f"Gross {payslip.gross_pay:,.2f}  −  Deductions {payslip.total_deductions:,.2f}  =  "
        f"Net {payslip.net_pay:,.2f} {payslip.currency_code}",
    ]
    ctk.CTkLabel(modal.body, text="\n".join(l for l in header_lines if l.strip()),
                 font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                 justify="left", anchor="w").pack(fill="x", pady=(0, 4))

    on_open_tx = None
    if ctx is not None and app is not None:
        from src.models.database import Transaction as _Tx
        from src.ui.transaction_dialog import open_transaction_modal

        def on_open_tx(tid):
            tx = ctx.session.query(_Tx).get(tid)
            if tx:
                open_transaction_modal(modal, ctx, app, tx)

    _render_payslip_sections(modal.body, payslip, on_open_transaction=on_open_tx, ctx=ctx)

    if ctx is not None:
        def _export_pdf():
            from tkinter import filedialog, messagebox as _mb
            from datetime import datetime as _dt2
            from src.services.report_generators import PayslipDocument
            ts = _dt2.now().strftime("%Y%m%d_%H%M%S")
            safe_name = (payslip.employee_name or "Payslip").replace(" ", "_")
            path = filedialog.asksaveasfilename(
                title="Save payslip as…", defaultextension=".pdf",
                initialfile=f"Payslip_{safe_name}_{ts}.pdf",
                filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")], parent=modal)
            if not path:
                return
            try:
                out = PayslipDocument().generate(ctx, payslip, path)
            except Exception as e:
                _mb.showerror("Export Failed", str(e), parent=modal)
                return
            if _mb.askyesno("Payslip Ready", f"Saved to:\n{out}\n\nOpen it now?", parent=modal):
                try:
                    import os as _os
                    _os.startfile(out)  # Windows
                except Exception:
                    import webbrowser
                    webbrowser.open(f"file://{out}")

        ctk.CTkButton(
            modal.footer, text="📄 Export PDF", command=_export_pdf,
            fg_color="transparent", border_color=theme.BORDER, border_width=1,
            text_color=theme.ACCENT, font=("Segoe UI", 12), height=36, width=130
        ).pack(side="left", padx=(16, 6), pady=12)

    ctk.CTkButton(
        modal.footer, text="Close", command=modal.destroy,
        fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
        text_color="#fff", font=("Segoe UI", 13, "bold"), height=36, width=140
    ).pack(side="right", padx=16, pady=12)


def open_payslip_history(parent, ctx, app=None):
    """Lists every saved payslip (company, period, net pay) — click one to
    open its full breakdown via show_payslip_viewer."""
    payslips = ctx.payslip.get_all()
    modal = Modal(parent, "Payslip History", width=560, height=620)

    if not payslips:
        ctk.CTkLabel(modal.body, text="No payslips imported yet.",
                     font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(pady=20)
    else:
        for p in payslips:
            period = ""
            if p.period_start and p.period_end:
                period = f"{p.period_start.strftime('%b %Y')}"
            row = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
            row.pack(fill="x", pady=4)
            text = f"{period}  •  {p.company}".strip(" •")
            ctk.CTkLabel(row, text=text, font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_PRI, anchor="w").pack(side="left", padx=10, pady=10, fill="x", expand=True)
            ctk.CTkLabel(row, text=f"Net {p.net_pay:,.2f} {p.currency_code}",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(side="left", padx=(0, 10))
            ctk.CTkButton(row, text="View", width=70, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=lambda p=p: show_payslip_viewer(modal, p, ctx=ctx, app=app)
                          ).pack(side="right", padx=10)

    modal.add_buttons("Close", modal.destroy, cancel_text="")
    for child in list(modal.footer.winfo_children()):
        if child.cget("text") == "":
            child.destroy()
