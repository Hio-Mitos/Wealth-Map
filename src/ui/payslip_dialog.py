"""
WealthMap – Import Payslip dialog

Lets the user pick a payslip PDF, shows a fully editable preview of
everything that was read from it (account to deposit into, date,
description, gross amount, each deduction line with an option to include
it and whether it links to an existing/new entry in the Loans tab), and
only writes anything to the database once the user clicks "Import" —
matching the "review before it's filled in" requirement.

Used from both the Transactions panel toolbar and Settings > Data
Management, so it lives in its own module rather than inside either.
"""

from tkinter import messagebox, filedialog
import customtkinter as ctk

from src.models.database import TransactionType
from src.services.payslip_import import parse_payslip_pdf, build_earnings_notes, PayslipParseError
from src.ui.widgets import Modal, make_entry, make_combo, make_textbox, attach_currency_tooltip
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

    modal = Modal(parent, "Import Payslip — Review & Confirm", width=680, height=820)

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

    acc_c = modal.add_field("Deposit Into Account", lambda p: make_combo(p, acc_names))
    acc_c.set(acc_names[0])

    cur_c = modal.add_field("Currency", lambda p: make_combo(p, currencies, width=120))
    if parsed.get("currency") in currencies:
        cur_c.set(parsed["currency"])
    elif currencies:
        cur_c.set(currencies[0])
    attach_currency_tooltip(cur_c, ctx)

    default_date = (parsed.get("period_end") or parsed.get("period_start"))
    date_e = modal.add_field(
        "Date (YYYY-MM-DD)",
        lambda p: make_entry(p, "YYYY-MM-DD")
    )
    if default_date:
        date_e.insert(0, default_date.strftime("%Y-%m-%d"))

    period_label = ""
    if parsed.get("period_start") and parsed.get("period_end"):
        period_label = f"{parsed['period_start'].strftime('%b %Y')}"
    desc_e = modal.add_field("Description", lambda p: make_entry(p, "Salary"))
    desc_e.insert(0, f"Salary - {parsed.get('company', '')} - {period_label}".strip(" -"))

    payee_e = modal.add_field("Payee / Employer", lambda p: make_entry(p, "Employer"))
    payee_e.insert(0, parsed.get("company", ""))

    gross_e = modal.add_field(
        "Gross Pay (taxable + non-taxable earnings)",
        lambda p: make_entry(p, "0.00")
    )
    gross_e.insert(0, f"{parsed.get('gross_pay', 0.0):.2f}")

    # ── Deductions ───────────────────────────────────────────────────────
    ctk.CTkLabel(modal.body, text="💸 Deductions (each becomes a fee/tax line on the salary "
                                   "transaction; loan-linked ones also record a repayment)",
                 font=("Segoe UI", 12, "bold"), text_color=theme.ACCENT,
                 wraplength=600, justify="left").pack(anchor="w", pady=(8, 6))

    deductions_container = ctk.CTkFrame(modal.body, fg_color="transparent")
    deductions_container.pack(fill="x", pady=(0, 4))
    deduction_rows = []

    loan_names = [l.contact_name for l in loans]

    def add_deduction_row(d):
        row = ctk.CTkFrame(deductions_container, fg_color=theme.BG_HOVER, corner_radius=8)
        row.pack(fill="x", pady=2)

        top_row = ctk.CTkFrame(row, fg_color="transparent")
        top_row.pack(fill="x", padx=6, pady=(6, 2))

        desc_e2 = make_entry(top_row, "Description")
        desc_e2.insert(0, d["label"])
        desc_e2.pack(side="left", fill="x", expand=True, padx=(0, 4))

        kind_c2 = make_combo(top_row, ["Fee", "Tax"], width=70)
        kind_c2.set("Tax" if d.get("is_statutory") else "Fee")
        kind_c2.pack(side="left", padx=4)

        amt_e2 = make_entry(top_row, "Amount", width=100)
        amt_e2.insert(0, f"{d['amount']:.2f}")
        amt_e2.pack(side="left", padx=4)

        entry = {"row": row, "description": desc_e2, "kind": kind_c2,
                 "amount": amt_e2, "loan_combo": None, "source": d}

        def remove_row():
            entry["row"].destroy()
            if entry in deduction_rows:
                deduction_rows.remove(entry)

        ctk.CTkButton(top_row, text="✕", width=28, height=28,
                      fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 12),
                      command=remove_row).pack(side="left", padx=(4, 0))

        if d.get("is_loan"):
            loan_row = ctk.CTkFrame(row, fg_color="transparent")
            loan_row.pack(fill="x", padx=6, pady=(0, 6))
            ctk.CTkLabel(loan_row, text="Link to Loan:", font=("Segoe UI", 11),
                         text_color=theme.TEXT_SEC).pack(side="left", padx=(0, 6))
            options = [CREATE_NEW_LOAN] + loan_names + [DONT_LINK_LOAN]
            loan_c = make_combo(loan_row, options, width=280)
            # Default to a matching existing loan by name if one exists,
            # otherwise offer to create a new one.
            match = next((n for n in loan_names if n.strip().lower() == d["label"].strip().lower()), None)
            loan_c.set(match if match else CREATE_NEW_LOAN)
            loan_c.pack(side="left", fill="x", expand=True)
            entry["loan_combo"] = loan_c

            bal = next((lb["amount"] for lb in parsed.get("loan_balances", [])
                        if lb["label"].strip().lower() == d["label"].strip().lower()), None)
            if bal is not None:
                ctk.CTkLabel(row, text=f"Payslip shows remaining balance: {bal:,.2f}",
                             font=("Segoe UI", 10), text_color=theme.TEXT_SEC
                             ).pack(anchor="w", padx=6, pady=(0, 6))

        deduction_rows.append(entry)
        return entry

    for d in parsed.get("deductions", []):
        add_deduction_row(d)

    total_ded = sum(d["amount"] for d in parsed.get("deductions", []))
    net_lbl = ctk.CTkLabel(
        modal.body,
        text=f"Net pay (from payslip): {parsed.get('net_pay', 0.0):,.2f}   "
             f"(gross {parsed.get('gross_pay', 0.0):,.2f} − deductions {total_ded:,.2f})",
        font=("Segoe UI", 11), text_color=theme.TEXT_SEC, anchor="w"
    )
    net_lbl.pack(fill="x", pady=(4, 10))

    notes_t = modal.add_field("Notes (earnings breakdown — editable)",
                               lambda p: make_textbox(p, height=140))
    notes_t.insert("1.0", build_earnings_notes(parsed))

    attach_var = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(modal.body, text="Attach the original payslip PDF to this transaction",
                     variable=attach_var, font=("Segoe UI", 12),
                     text_color=theme.TEXT_PRI).pack(anchor="w", pady=(4, 8))

    def do_import():
        try:
            account = next((a for a in accounts if a.name == acc_c.get()), None)
            if not account:
                messagebox.showerror("Missing Account", "Choose an account to deposit into.", parent=modal)
                return
            try:
                gross = float(gross_e.get().replace(",", ""))
            except ValueError:
                messagebox.showerror("Invalid Amount", "Gross pay must be a number.", parent=modal)
                return
            try:
                from datetime import datetime as _dt
                tx_date = _dt.strptime(date_e.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid Date", "Use the format YYYY-MM-DD.", parent=modal)
                return
            currency_code = cur_c.get()

            charges = []
            loan_actions = []  # (loan_name_or_None, amount, description, is_new)
            for entry in deduction_rows:
                try:
                    amt = float(entry["amount"].get().replace(",", ""))
                except ValueError:
                    amt = 0.0
                if amt == 0:
                    continue
                desc = entry["description"].get().strip() or entry["source"]["label"]
                kind = "tax" if entry["kind"].get() == "Tax" else "fee"
                charges.append({"kind": kind, "amount": amt, "currency_code": currency_code,
                                 "description": desc})

                if entry["loan_combo"] is not None:
                    choice = entry["loan_combo"].get()
                    if choice == CREATE_NEW_LOAN:
                        loan_actions.append({"mode": "new", "name": desc, "amount": amt,
                                              "source": entry["source"]})
                    elif choice != DONT_LINK_LOAN:
                        loan_actions.append({"mode": "existing", "name": choice, "amount": amt,
                                              "source": entry["source"]})

            tx = ctx.transaction.add(
                account, TransactionType.SALARY, gross,
                description=desc_e.get().strip() or "Salary",
                category="Salary / Income",
                payee=payee_e.get().strip(),
                transaction_date=tx_date,
                currency_code=currency_code,
                notes=notes_t.get("1.0", "end").strip(),
                charges=charges,
            )

            for action in loan_actions:
                if action["mode"] == "new":
                    balance = next(
                        (lb["amount"] for lb in parsed.get("loan_balances", [])
                         if lb["label"].strip().lower() == action["source"]["label"].strip().lower()),
                        None
                    )
                    principal = (balance + action["amount"]) if balance is not None else action["amount"]
                    loan = ctx.loan.create(
                        contact_name=action["name"], direction="i_owe",
                        principal=principal, currency_code=currency_code,
                        description=f"Auto-created from payslip import ({period_label})",
                        contact_info=parsed.get("company", ""),
                    )
                else:
                    loan = next((l for l in loans if l.contact_name == action["name"]), None)
                if loan:
                    ctx.loan.record_repayment(
                        loan, action["amount"], repaid_on=tx_date,
                        notes=f"Payslip deduction — {period_label}".strip(" —")
                    )

            if attach_var.get():
                try:
                    ctx.attachment.save_file(
                        parsed["source_file"], ctx.session, "transaction", tx.id,
                        description="Payslip"
                    )
                except Exception:
                    pass  # non-fatal — the transaction itself already succeeded

            # Archive every individual figure from the payslip (each taxable/
            # non-taxable earning, each deduction, each loan balance, each
            # YTD summary row) as its own record — not just the lump salary
            # transaction — so the full document stays inspectable later.
            try:
                ctx.payslip.create_from_parsed(parsed, account=account, transaction=tx)
            except Exception:
                pass  # non-fatal — the transaction itself already succeeded

            modal.destroy()
            messagebox.showinfo("Payslip Imported",
                                 f"Salary transaction created: net {parsed.get('net_pay', 0.0):,.2f} "
                                 f"{currency_code}.", parent=parent)
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
    "ytd_summary":         "📅 Year-To-Date Summary",
}


def _render_payslip_sections(container, payslip):
    for section, title in SECTION_TITLES.items():
        items = payslip.items_in(section)
        if not items:
            continue
        ctk.CTkLabel(container, text=title, font=("Segoe UI", 13, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(10, 4))
        card = ctk.CTkFrame(container, fg_color=theme.BG_HOVER, corner_radius=8)
        card.pack(fill="x", pady=(0, 4))
        total = 0.0
        for it in items:
            row = ctk.CTkFrame(card, fg_color="transparent")
            row.pack(fill="x", padx=10, pady=2)
            label_txt = it.label
            if it.hours:
                label_txt += f"  ({it.hours:g} hrs)"
            ctk.CTkLabel(row, text=label_txt, font=("Segoe UI", 12),
                         text_color=theme.TEXT_PRI, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=f"{it.amount:,.2f}", font=("Segoe UI", 12),
                         text_color=theme.TEXT_PRI).pack(side="right")
            total += it.amount
        if len(items) > 1:
            total_row = ctk.CTkFrame(card, fg_color="transparent")
            total_row.pack(fill="x", padx=10, pady=(2, 6))
            ctk.CTkLabel(total_row, text="Total", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_SEC, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(total_row, text=f"{total:,.2f}", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_SEC).pack(side="right")


def show_payslip_viewer(parent, payslip):
    """Read-only breakdown of a saved Payslip — every taxable/non-taxable
    earning, deduction, loan balance, and YTD summary figure exactly as
    imported."""
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

    _render_payslip_sections(modal.body, payslip)

    ctk.CTkButton(
        modal.footer, text="Close", command=modal.destroy,
        fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
        text_color="#fff", font=("Segoe UI", 13, "bold"), height=36, width=140
    ).pack(side="right", padx=16, pady=12)


def open_payslip_history(parent, ctx):
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
                          command=lambda p=p: show_payslip_viewer(modal, p)).pack(side="right", padx=10)

    modal.add_buttons("Close", modal.destroy, cancel_text="")
    for child in list(modal.footer.winfo_children()):
        if child.cget("text") == "":
            child.destroy()
