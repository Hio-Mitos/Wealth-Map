"""
WealthMap – Import Bill dialog

Lets the user pick a utility/statement PDF (electric, water, internet,
etc.), shows a fully editable preview of everything that was read from it
(provider, account/meter number, amount due, due date, billing period,
charge breakdown, and any payment history printed on the statement), and
only writes anything to the database once the user clicks "Import" — the
same "review before it's filled in" pattern as the Payslip import dialog.

Re-importing a later statement for the same account number (CAN) updates
the SAME Bill record (found via BillService.get_by_account_number) rather
than creating a duplicate, so a bill's due date/amount always reflect the
latest statement while its full payment-history transactions accumulate
over time.
"""

from datetime import datetime as _dt
from tkinter import messagebox, filedialog
import customtkinter as ctk

from src.models.database import TransactionType
from src.services.bill_import import parse_utility_bill_pdf, BillParseError
from src.ui.widgets import (
    Modal, make_entry, make_combo, make_textbox, attach_currency_tooltip,
    CurrencySearchEntry
)
from src.ui.theme import theme

FREQ_LABELS = {
    "weekly": "Weekly", "monthly": "Monthly", "quarterly": "Quarterly",
    "yearly": "Yearly", "one_time": "One-time",
}
FREQ_BY_LABEL = {v: k for k, v in FREQ_LABELS.items()}


def open_bill_import_dialog(parent, ctx, on_done=None):
    """Opens a file picker, parses the chosen PDF, then shows the
    review/edit modal. `on_done` (optional) is called with no args after a
    successful import, so callers can refresh whatever list is on screen."""
    path = filedialog.askopenfilename(
        title="Select Bill / Statement PDF",
        filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")]
    )
    if not path:
        return

    try:
        parsed = parse_utility_bill_pdf(path)
    except BillParseError as e:
        messagebox.showerror("Couldn't Read Bill", str(e), parent=parent)
        return
    except Exception as e:
        messagebox.showerror("Couldn't Read Bill",
                              f"Unexpected error reading this PDF:\n{e}", parent=parent)
        return

    _show_review_modal(parent, ctx, parsed, on_done=on_done)


def _format_notes(parsed) -> str:
    lines = []
    if parsed.get("reference_no"):
        bd = parsed["bill_date"].strftime("%d %b %Y") if parsed.get("bill_date") else ""
        lines.append(f"Imported from statement — Invoice/Reference No. {parsed['reference_no']}"
                     + (f" ({bd})" if bd else ""))
    if parsed.get("period_start") and parsed.get("period_end"):
        lines.append(f"Billing period: {parsed['period_start'].strftime('%d %b %Y')} – "
                     f"{parsed['period_end'].strftime('%d %b %Y')}")
    if parsed.get("consumption"):
        rate = f" @ {parsed['rate_per_unit']:,.4f}/{parsed['consumption_unit']}" \
               if parsed.get("rate_per_unit") else ""
        lines.append(f"Consumption: {parsed['consumption']:,.2f} "
                     f"{parsed.get('consumption_unit', '')}{rate}")
    if parsed.get("period_charges") is not None:
        lines.append(f"Charges this period: {parsed['period_charges']:,.2f}")
        for label, amt in parsed.get("charges_breakdown", {}).items():
            lines.append(f"  {label}: {amt:,.2f}")
    if parsed.get("remaining_balance_previous"):
        lines.append(f"Remaining balance from previous bill: "
                     f"{parsed['remaining_balance_previous']:,.2f}")
    for u in parsed.get("unpaid_history", []):
        due = u["due_date"].strftime("%d %b %Y") if u.get("due_date") else "—"
        lines.append(f"Unpaid — {u['period']} (due {due}): {u['amount']:,.2f} — {u['remarks']}")
    for note in parsed.get("extra_notes", []):
        lines.append(note)
    return "\n".join(lines)


def _show_review_modal(parent, ctx, parsed, on_done=None):
    accounts = ctx.account.get_all()
    if not accounts:
        messagebox.showerror("No Accounts", "Create an account first.", parent=parent)
        return
    acc_names = [a.name for a in accounts]

    existing = ctx.bill.get_by_account_number(parsed.get("account_number", ""))
    is_new = existing is None

    modal = Modal(parent, "Import Bill — Review & Confirm", width=720, height=880)

    header_bits = [parsed.get("provider") or "Bill statement"]
    if parsed.get("service_address"):
        header_bits.append(parsed["service_address"])
    ctk.CTkLabel(modal.body, text="  •  ".join(header_bits),
                 font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                 wraplength=660, justify="left", anchor="w").pack(fill="x", pady=(0, 4))

    if not is_new:
        ctk.CTkLabel(modal.body,
                     text=f"⚠ An existing bill for account {parsed.get('account_number')} "
                          f"(\"{existing.name}\") will be UPDATED with this statement's figures, "
                          "not duplicated.",
                     font=("Segoe UI", 11), text_color=theme.GOLD,
                     wraplength=660, justify="left", anchor="w").pack(fill="x", pady=(0, 10))

    default_name = (existing.name if existing else
                    (f"{parsed.get('provider')} Bill" if parsed.get("provider") else "Utility Bill"))
    name_e = modal.add_field("Bill Name", lambda p: make_entry(p, "e.g. Electricity"))
    name_e.insert(0, default_name)

    payee_e = modal.add_field("Payee / Provider", lambda p: make_entry(p, "Company"))
    payee_e.insert(0, parsed.get("provider", ""))

    can_e = modal.add_field("Account Number (CAN)", lambda p: make_entry(p, "Customer Account No."))
    can_e.insert(0, parsed.get("account_number", ""))

    meter_e = modal.add_field("Meter / Reference Number", lambda p: make_entry(p, "Optional"))
    meter_e.insert(0, parsed.get("meter_number", ""))

    addr_e = modal.add_field("Service Address", lambda p: make_entry(p, "Optional"))
    addr_e.insert(0, parsed.get("service_address", ""))

    default_currency = parsed.get("currency_code") or ctx.settings.get("base_currency", "USD")
    cur_c = modal.add_field("Currency", lambda p: CurrencySearchEntry(
        p, ctx, width=120, initial_code=default_currency))
    attach_currency_tooltip(cur_c, ctx)

    amt_default = parsed.get("total_amount_due")
    if amt_default is None:
        amt_default = parsed.get("period_charges") or 0.0
    amt_e = modal.add_field("Amount Due (this bill)", lambda p: make_entry(p, "0.00"))
    amt_e.insert(0, f"{amt_default:.2f}")

    due_e = modal.add_field("Due Date (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
    if parsed.get("due_date"):
        due_e.insert(0, parsed["due_date"].strftime("%Y-%m-%d"))

    freq_c = modal.add_field("Frequency", lambda p: make_combo(p, list(FREQ_LABELS.values())))
    freq_c.set(FREQ_LABELS.get(existing.frequency, "Monthly") if existing else "Monthly")

    acc_c = modal.add_field("Default Pay-From Account", lambda p: make_combo(p, acc_names))
    acc_c.set(existing.account.name if existing and existing.account and
              existing.account.name in acc_names else acc_names[0])

    cat_e = modal.add_field("Category", lambda p: make_entry(p, "Bills & Utilities"))
    cat_e.insert(0, (existing.category if existing and existing.category else "Bills & Utilities"))

    notes_t = modal.add_field("Notes (charge breakdown, auto-filled)", lambda p: make_textbox(p, height=140))
    notes_t.insert("1.0", _format_notes(parsed))

    history = [h for h in parsed.get("payment_history", []) if h.get("posting_date")]
    hist_var = ctk.BooleanVar(value=is_new and bool(history))
    if history:
        ctk.CTkCheckBox(
            modal.body,
            text=f"Import {len(history)} past payment(s) shown on this statement as transactions",
            variable=hist_var, font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
        ).pack(anchor="w", pady=(6, 2))
        preview = "\n".join(
            f"  {h['posting_date'].strftime('%d %b %Y')} — {h['channel']} — {h['amount']:,.2f}"
            for h in history[:6]
        )
        ctk.CTkLabel(modal.body, text=preview, font=("Segoe UI", 10),
                     text_color=theme.TEXT_SEC, justify="left", anchor="w").pack(fill="x", pady=(0, 8))

    attach_var = ctk.BooleanVar(value=True)
    ctk.CTkCheckBox(modal.body, text="Attach the original statement PDF to this bill",
                     variable=attach_var, font=("Segoe UI", 12),
                     text_color=theme.TEXT_PRI).pack(anchor="w", pady=(4, 8))

    def do_import():
        try:
            name = name_e.get().strip()
            if not name:
                messagebox.showerror("Missing Name", "Give the bill a name.", parent=modal)
                return
            account = next((a for a in accounts if a.name == acc_c.get()), None)
            try:
                amount = float(amt_e.get().replace(",", ""))
            except ValueError:
                messagebox.showerror("Invalid Amount", "Amount must be a number.", parent=modal)
                return
            due_txt = due_e.get().strip()
            next_due = None
            if due_txt:
                try:
                    next_due = _dt.strptime(due_txt, "%Y-%m-%d")
                except ValueError:
                    messagebox.showerror("Invalid Date", "Due date must be YYYY-MM-DD.", parent=modal)
                    return
            cur_c.resolve()
            currency_code = cur_c.get()

            fields = dict(
                name=name, payee=payee_e.get().strip(), amount=amount,
                currency_code=currency_code,
                frequency=FREQ_BY_LABEL.get(freq_c.get(), "monthly"),
                next_due=next_due, category=cat_e.get().strip() or "Bills & Utilities",
                notes=notes_t.get("1.0", "end").strip(),
                account_number=can_e.get().strip(),
                meter_number=meter_e.get().strip(),
                service_address=addr_e.get().strip(),
                reference_no=parsed.get("reference_no", ""),
                billing_period_start=parsed.get("period_start"),
                billing_period_end=parsed.get("period_end"),
                consumption=parsed.get("consumption"),
                consumption_unit=parsed.get("consumption_unit", ""),
            )

            if existing:
                update_fields = dict(fields)
                update_fields["account_id"] = account.id if account else None
                bill = ctx.bill.update(existing, **update_fields)
            else:
                bill = ctx.bill.create(account=account, **fields)

            imported_count = 0
            latest_paid = None
            if hist_var.get() and account is not None:
                for h in sorted(history, key=lambda x: x["posting_date"]):
                    ctx.transaction.add(
                        account, TransactionType.EXPENSE, h["amount"],
                        description=f"Bill payment — {bill.name} ({h['period']})",
                        category=bill.category or "Bills & Utilities",
                        payee=bill.payee or bill.name,
                        transaction_date=h["posting_date"],
                        currency_code=currency_code,
                        notes=f"Paid via {h['channel']} (imported from statement)",
                        bill_id=bill.id,
                    )
                    imported_count += 1
                    latest_paid = h["posting_date"]
                if latest_paid and (bill.last_paid_on is None or latest_paid > bill.last_paid_on):
                    ctx.bill.update(bill, last_paid_on=latest_paid)

            if attach_var.get():
                try:
                    ctx.attachment.save_file(
                        parsed["source_file"], ctx.session, "bill", bill.id,
                        description="Utility bill statement"
                    )
                except Exception:
                    pass  # non-fatal — the bill itself already saved successfully

            modal.destroy()
            verb = "updated" if existing else "created"
            summary = (f"Bill \"{bill.name}\" {verb} — {amount:,.2f} {currency_code} due "
                      + (next_due.strftime("%d %b %Y") if next_due else "no date set"))
            if imported_count:
                summary += f"\n{imported_count} past payment(s) imported."
            messagebox.showinfo("Bill Imported", summary, parent=parent)
            if on_done:
                on_done()
        except Exception as e:
            messagebox.showerror("Import Failed", str(e), parent=modal)

    modal.add_buttons("Import", do_import, cancel_text="Cancel")
