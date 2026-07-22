"""
WealthMap – Transaction editor dialog

The full "New/Edit Transaction" modal, extracted out of TransactionsPanel so
any panel can open/edit a transaction without needing a full
TransactionsPanel instance — e.g. the Taxes tab opens a tax-typed
transaction here directly, and Transactions itself is now a thin wrapper
around `open_transaction_modal`.
"""

from tkinter import messagebox, simpledialog
import customtkinter as ctk

from src.models.database import (TransactionType, TransactionStatus,
                                 CREDIT_TRANSACTION_TYPES, DEBIT_TRANSACTION_TYPES)
from src.services.profiles import list_remote_accounts
from src.ui.widgets import (
    Modal, make_entry, make_combo, make_textbox,
    attach_currency_tooltip, AttachmentSection, CurrencySearchEntry
)
from src.ui.theme import theme


def _toggle_transfer_field(transfer_lbl, value):
    if value == TransactionType.TRANSFER.value:
        transfer_lbl.configure(text="Transfer To Account (required)")
    else:
        transfer_lbl.configure(text="Also Affects Account (optional)")


def _parse_float(text):
    text = (text or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def open_transaction_modal(parent, ctx, app, tx=None, on_saved=None, on_deleted=None):
    """Opens the New/Edit Transaction modal.

    `on_saved(saved_tx, was_edit)` is called after a successful create or
    update; `on_deleted()` after a successful delete. Both are optional —
    callers use them to refresh whatever list/detail view they're showing."""
    is_edit = tx is not None
    modal = Modal(parent, "Edit Transaction" if is_edit else "New Transaction",
                  width=560, height=820)

    accounts  = ctx.account.get_all()
    acc_names = [a.name for a in accounts]
    custom_types = ctx.customization.get_custom_types()
    # Internal-only generic buckets aren't shown directly; custom type
    # names (backed by those buckets) are shown instead.
    tx_types  = [t.value for t in TransactionType
                if t not in (TransactionType.CUSTOM_CREDIT, TransactionType.CUSTOM_DEBIT)]
    tx_types += [ct.name for ct in custom_types]
    tx_status = [s.value for s in TransactionStatus]

    if not acc_names:
        messagebox.showerror("No Accounts", "Create an account first.", parent=modal)
        modal.destroy()
        return

    acc_c   = modal.add_field("Account",          lambda p: make_combo(p, acc_names))
    type_c  = modal.add_field("Transaction Type", lambda p: make_combo(p, tx_types,
                              command=lambda v: _toggle_transfer_field(transfer_lbl, v)))
    amt_e   = modal.add_field("Amount",           lambda p: make_entry(p, "0.00"))
    cur_c   = modal.add_field("Currency",         lambda p: CurrencySearchEntry(p, ctx))
    attach_currency_tooltip(cur_c, ctx)

    # Accounts in linked profiles of the same type (for cross-profile transfers)
    remote_account_map = {}  # label -> {profile_id, profile_name, account_id, account_name, currency_code}
    if ctx.registry:
        for lp in ctx.registry.linked_profiles(ctx.profile["id"]):
            for ra in list_remote_accounts(ctx.registry.db_path(lp["id"])):
                label = f"[{lp['name']}] {ra['name']}"
                remote_account_map[label] = {
                    "profile_id": lp["id"], "profile_name": lp["name"],
                    "account_id": ra["id"], "account_name": ra["name"],
                    "currency_code": ra["currency_code"],
                }

    # Second account — used for Transfers (required) and, optionally,
    # for any other type to record that the transaction also affects
    # another account (e.g. funding an investment from a bank account,
    # or a cash withdrawal landing in a wallet account). Accounts in
    # linked profiles appear too, enabling cross-profile transfers.
    transfer_frame = ctk.CTkFrame(modal.body, fg_color="transparent")
    transfer_frame.pack(fill="x", pady=(0, 8))
    transfer_lbl = ctk.CTkLabel(transfer_frame, text="Also Affects Account (optional)",
                                font=("Segoe UI", 12), text_color=theme.TEXT_SEC, anchor="w")
    transfer_lbl.pack(fill="x")
    to_acc_c = make_combo(transfer_frame, ["(none)"] + acc_names + list(remote_account_map.keys()))
    to_acc_c.set("(none)")
    to_acc_c.pack(fill="x", pady=(2, 4))
    preview_lbl = ctk.CTkLabel(transfer_frame, text="", font=("Segoe UI", 11),
                               text_color=theme.GOLD, anchor="w")
    preview_lbl.pack(fill="x", pady=(0, 8))

    def update_preview(*_):
        try:
            from_acc = next((a for a in accounts if a.name == acc_c.get()), None)
            to_name = to_acc_c.get()
            amt = float(amt_e.get().replace(",", "") or 0)
            remote = remote_account_map.get(to_name)
            to_acc = None if remote else next((a for a in accounts if a.name == to_name), None)
            if from_acc and amt > 0 and (to_acc or remote):
                from_code = cur_c.get()
                to_code = remote["currency_code"] if remote else to_acc.currency.code
                to_display = to_name if remote else to_acc.name
                if from_code != to_code:
                    converted = ctx.currency.convert(amt, from_code, to_code)
                    if converted is not None:
                        cur_obj = ctx.currency.get_by_code(to_code)
                        csym = cur_obj.symbol if cur_obj else ""
                        preview_lbl.configure(
                            text=f"≈ converts to {csym}{converted:,.2f} {to_code} "
                                 f"in {to_display}")
                    else:
                        preview_lbl.configure(text="(no exchange rate available — will store as-is)")
                else:
                    preview_lbl.configure(text="")
            else:
                preview_lbl.configure(text="")
        except Exception:
            preview_lbl.configure(text="")

    amt_e.bind("<KeyRelease>", update_preview)
    to_acc_c.configure(command=lambda v: update_preview())
    cur_c.set_on_pick(lambda v: update_preview())

    NEW_CATEGORY_OPTION = "＋ New Category..."

    def on_category_pick(value):
        if value != NEW_CATEGORY_OPTION:
            return
        name = simpledialog.askstring("New Category", "Category name:", parent=modal)
        if name and name.strip():
            try:
                ctx.customization.add_category(name.strip())
                cat_c.configure(values=ctx.customization.get_categories() + [NEW_CATEGORY_OPTION])
                cat_c.set(name.strip())
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)
                cat_c.set("Other")
        else:
            cat_c.set("Other")

    desc_e  = modal.add_field("Description",      lambda p: make_entry(p, "What was this for?"))
    cat_c   = modal.add_field("Category",         lambda p: make_combo(
        p, ctx.customization.get_categories() + [NEW_CATEGORY_OPTION],
        command=on_category_pick))
    payee_e = modal.add_field("Payee / From",     lambda p: make_entry(p, "Person or merchant"))
    ref_e   = modal.add_field("Reference",        lambda p: make_entry(p, "Bank ref, cheque #…"))
    date_e  = modal.add_field("Date (YYYY-MM-DD)",lambda p: make_entry(p, "YYYY-MM-DD"))
    stat_c  = modal.add_field("Status",           lambda p: make_combo(p, tx_status))

    # ── Fees & Taxes ──────────────────────────────────────────────────
    ctk.CTkLabel(modal.body, text="💰 Fees & Taxes (optional)", font=("Segoe UI", 12, "bold"),
                 text_color=theme.ACCENT).pack(anchor="w", pady=(8, 4))

    fee_row = ctk.CTkFrame(modal.body, fg_color="transparent")
    fee_row.pack(fill="x", pady=(0, 4))
    fee_amt_e = make_entry(fee_row, "Fee amount")
    fee_amt_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
    fee_cur_c = CurrencySearchEntry(fee_row, ctx, width=90)
    fee_cur_c.pack(side="left")
    attach_currency_tooltip(fee_cur_c, ctx)
    fee_desc_e = make_entry(modal.body, "Fee description (e.g. wire fee, ATM fee)")
    fee_desc_e.pack(fill="x", pady=(2, 8))

    tax_row = ctk.CTkFrame(modal.body, fg_color="transparent")
    tax_row.pack(fill="x", pady=(0, 4))
    tax_amt_e = make_entry(tax_row, "Tax amount")
    tax_amt_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
    tax_cur_c = CurrencySearchEntry(tax_row, ctx, width=90)
    tax_cur_c.pack(side="left")
    attach_currency_tooltip(tax_cur_c, ctx)
    tax_desc_e = make_entry(modal.body, "Tax description (e.g. sales tax, withholding)")
    tax_desc_e.pack(fill="x", pady=(2, 8))

    # ── Additional charges (unlimited fees/taxes) ───────────────────────
    ctk.CTkLabel(modal.body, text="➕ Additional Fees / Taxes", font=("Segoe UI", 12, "bold"),
                 text_color=theme.ACCENT).pack(anchor="w", pady=(4, 4))
    charges_container = ctk.CTkFrame(modal.body, fg_color="transparent")
    charges_container.pack(fill="x", pady=(0, 2))
    charge_rows = []

    def add_charge_row(prefill=None):
        row = ctk.CTkFrame(charges_container, fg_color=theme.BG_HOVER, corner_radius=8)
        row.pack(fill="x", pady=2)
        kind_c2 = make_combo(row, ["Fee", "Tax"], width=70)
        kind_c2.set("Tax" if (prefill and prefill.kind == "tax") else "Fee")
        kind_c2.pack(side="left", padx=(6, 4), pady=4)
        amt_e2 = make_entry(row, "Amount", width=90)
        if prefill:
            amt_e2.insert(0, f"{prefill.amount:g}")
        amt_e2.pack(side="left", padx=4, pady=4)
        default_code = (prefill.currency.code if (prefill and prefill.currency) else cur_c.get())
        cur_c2 = CurrencySearchEntry(row, ctx, width=80, initial_code=default_code)
        cur_c2.pack(side="left", padx=4, pady=4)
        attach_currency_tooltip(cur_c2, ctx)
        desc_e2 = make_entry(row, "Description")
        if prefill:
            desc_e2.insert(0, prefill.description or "")
        desc_e2.pack(side="left", fill="x", expand=True, padx=4, pady=4)

        entry = {"row": row, "kind": kind_c2, "amount": amt_e2,
                "currency": cur_c2, "description": desc_e2}

        def remove_row():
            entry["row"].destroy()
            if entry in charge_rows:
                charge_rows.remove(entry)

        ctk.CTkButton(row, text="✕", width=28, height=28,
                      fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 12),
                      command=remove_row).pack(side="left", padx=(4, 6), pady=4)
        charge_rows.append(entry)
        return entry

    ctk.CTkButton(modal.body, text="＋ Add Another Fee / Tax", height=30, font=("Segoe UI", 11),
                  fg_color="transparent", border_color=theme.BORDER, border_width=1,
                  text_color=theme.ACCENT,
                  command=lambda: add_charge_row()).pack(anchor="w", pady=(2, 8))

    notes_t = modal.add_field("Notes", lambda p: make_textbox(p, height=50))

    dept_c = None
    if ctx.is_business:
        departments = ctx.department.get_all()
        dept_options = ["(none)"] + [d.name for d in departments]
        dept_c = modal.add_field("Department", lambda p: make_combo(p, dept_options))
        dept_c.set("(none)")
        if is_edit and tx.department:
            dept_c.set(tx.department.name)

    att_section = AttachmentSection(modal.body, ctx, "transaction",
                                    entity=tx if is_edit else None)
    att_section.pack(fill="x")

    # ── Defaults / prefill ──────────────────────────────────────────────
    if is_edit:
        acc_c.set(tx.account.name if tx.account else acc_names[0])
        type_c.set(tx.display_type)
        _toggle_transfer_field(transfer_lbl, tx.transaction_type.value)
        amt_e.insert(0, f"{tx.amount:g}")
        cur_c.set(tx.currency.code)
        desc_e.insert(0, tx.description or "")
        cat_c.set(tx.category or "Other")
        payee_e.insert(0, tx.payee or "")
        ref_e.insert(0, tx.reference or "")
        date_e.insert(0, tx.transaction_date.strftime("%Y-%m-%d"))
        stat_c.set(tx.status.value)
        if tx.fee_amount:
            fee_amt_e.insert(0, f"{tx.fee_amount:g}")
        fee_cur_c.set((tx.fee_currency or tx.currency).code)
        fee_desc_e.insert(0, tx.fee_description or "")
        if tx.tax_amount:
            tax_amt_e.insert(0, f"{tx.tax_amount:g}")
        tax_cur_c.set((tx.tax_currency or tx.currency).code)
        tax_desc_e.insert(0, tx.tax_description or "")
        for charge in tx.charges:
            add_charge_row(prefill=charge)
        notes_t.insert("1.0", tx.notes or "")
        if tx.linked_account:
            to_acc_c.set(tx.linked_account.name)
            # Editing the linked-account selection of an existing
            # dual-leg transaction isn't supported (would require
            # recreating both legs) — keep it visible for context but
            # disabled.
            to_acc_c.configure(state="disabled")
        elif tx.linked_account_label:
            to_acc_c.configure(values=[f"🔗 {tx.linked_account_label}"])
            to_acc_c.set(f"🔗 {tx.linked_account_label}")
            to_acc_c.configure(state="disabled")
    else:
        acc_c.set(acc_names[0])
        cur_c.set(accounts[0].currency.code)
        type_c.set(tx_types[0])
        _toggle_transfer_field(transfer_lbl, tx_types[0])
        stat_c.set("Cleared")
        cat_c.set("Other")
        from datetime import datetime as _dt
        date_e.insert(0, _dt.now().strftime("%Y-%m-%d"))
        fee_cur_c.set(accounts[0].currency.code)
        tax_cur_c.set(accounts[0].currency.code)

    def save():
        cur_c.resolve()
        fee_cur_c.resolve()
        tax_cur_c.resolve()
        for entry in charge_rows:
            entry["currency"].resolve()
        try:
            acc_name = acc_c.get()
            acc = next((a for a in accounts if a.name == acc_name), None)
            if not acc:
                raise ValueError("Select a valid account")
            amount = float(amt_e.get().replace(",", ""))
            tx_type, custom_label = ctx.customization.resolve_type(type_c.get())
            if tx_type == TransactionType.ADJUSTMENT:
                if amount == 0:
                    raise ValueError("Adjustment amount cannot be zero")
            elif amount <= 0:
                raise ValueError("Amount must be positive")
            status  = next(s for s in TransactionStatus if s.value == stat_c.get())
            notes   = notes_t.get("1.0", "end").strip()

            from datetime import datetime as _dt
            try:
                tx_date = _dt.strptime(date_e.get().strip(), "%Y-%m-%d")
            except ValueError:
                raise ValueError("Date must be in YYYY-MM-DD format")

            fee_amount = _parse_float(fee_amt_e.get()) or 0.0
            tax_amount = _parse_float(tax_amt_e.get()) or 0.0

            charges_list = []
            for entry in charge_rows:
                c_amt = _parse_float(entry["amount"].get())
                if not c_amt:
                    continue
                charges_list.append({
                    "kind": "tax" if entry["kind"].get() == "Tax" else "fee",
                    "amount": c_amt,
                    "currency_code": entry["currency"].get(),
                    "description": entry["description"].get().strip(),
                })

            department_id = None
            if dept_c is not None and dept_c.get() != "(none)":
                dept = next((d for d in ctx.department.get_all() if d.name == dept_c.get()), None)
                department_id = dept.id if dept else None

            if is_edit:
                fields = dict(
                    account_id=acc.id,
                    transaction_type=tx_type,
                    custom_type_label=custom_label,
                    amount=amount,
                    currency_code=cur_c.get(),
                    description=desc_e.get().strip(),
                    category=cat_c.get(),
                    payee=payee_e.get().strip(),
                    reference=ref_e.get().strip(),
                    transaction_date=tx_date,
                    status=status,
                    notes=notes,
                    department_id=department_id,
                    fee_amount=fee_amount,
                    fee_currency_code=fee_cur_c.get() if fee_amount else None,
                    fee_description=fee_desc_e.get().strip(),
                    tax_amount=tax_amount,
                    tax_currency_code=tax_cur_c.get() if tax_amount else None,
                    tax_description=tax_desc_e.get().strip(),
                    charges=charges_list,
                )
                # account_id isn't a direct settable via update() helper —
                # reassign the relationship attribute directly if changed
                if acc.id != tx.account_id:
                    tx.account_id = acc.id
                fields.pop("account_id")
                ctx.transaction.update(tx, **fields)
                saved_tx = tx
            else:
                linked_account = None
                cross_profile_target = None
                to_name = to_acc_c.get()
                DUAL_LEG_TYPES = (CREDIT_TRANSACTION_TYPES | DEBIT_TRANSACTION_TYPES |
                                 {TransactionType.TRANSFER})

                if to_name in remote_account_map:
                    if tx_type not in DUAL_LEG_TYPES:
                        raise ValueError(
                            f"Cross-profile transfers aren't supported for '{type_c.get()}'. "
                            "Choose a different type, or set 'Also Affects Account' to (none).")
                    cross_profile_target = remote_account_map[to_name]
                elif tx_type == TransactionType.TRANSFER:
                    linked_account = next((a for a in accounts if a.name == to_name), None)
                    if not linked_account:
                        raise ValueError("Select a destination account for the transfer")
                    if linked_account.id == acc.id:
                        raise ValueError("Transfer destination must differ from source account")
                elif to_name and to_name != "(none)":
                    linked_account = next((a for a in accounts if a.name == to_name), None)
                    if linked_account and linked_account.id == acc.id:
                        raise ValueError("The other account must differ from the main account")

                if cross_profile_target:
                    new_tx = ctx.cross_profile_transfer(
                        account=acc, tx_type=tx_type, amount=amount,
                        description=desc_e.get().strip(), category=cat_c.get(),
                        target_profile_id=cross_profile_target["profile_id"],
                        target_account_id=cross_profile_target["account_id"],
                        transaction_date=tx_date, currency_code=cur_c.get(),
                        payee=payee_e.get().strip(), reference=ref_e.get().strip(), notes=notes,
                        status=status,
                        department_id=department_id,
                        fee_amount=fee_amount,
                        fee_currency_code=fee_cur_c.get() if fee_amount else None,
                        fee_description=fee_desc_e.get().strip(),
                        tax_amount=tax_amount,
                        tax_currency_code=tax_cur_c.get() if tax_amount else None,
                        tax_description=tax_desc_e.get().strip(),
                        charges=charges_list,
                        custom_type_label=custom_label,
                    )
                else:
                    new_tx = ctx.transaction.add(
                        account=acc, tx_type=tx_type, amount=amount,
                        description=desc_e.get().strip(),
                        category=cat_c.get(),
                        payee=payee_e.get().strip(),
                        reference=ref_e.get().strip(),
                        transaction_date=tx_date,
                        currency_code=cur_c.get(),
                        linked_account=linked_account,
                        status=status, notes=notes,
                        department_id=department_id,
                        fee_amount=fee_amount,
                        fee_currency_code=fee_cur_c.get() if fee_amount else None,
                        fee_description=fee_desc_e.get().strip(),
                        tax_amount=tax_amount,
                        tax_currency_code=tax_cur_c.get() if tax_amount else None,
                        tax_description=tax_desc_e.get().strip(),
                        charges=charges_list,
                        custom_type_label=custom_label,
                    )
                att_section.commit(new_tx.id)
                saved_tx = new_tx
            modal.destroy()
            if on_saved:
                on_saved(saved_tx, is_edit)
        except ValueError as e:
            messagebox.showerror("Validation Error", str(e), parent=modal)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=modal)

    def delete():
        msg = f"Delete this {tx.display_type} transaction?"
        if tx.transfer_group_id:
            msg += "\n\nThis is one leg of a transfer — both legs will be deleted."
        if messagebox.askyesno("Delete Transaction", msg, parent=modal):
            ctx.transaction.delete(tx)
            modal.destroy()
            if on_deleted:
                on_deleted()

    extra = None
    if is_edit:
        extra = [("Delete Transaction", delete, theme.RED)]

    modal.add_buttons("Save Changes" if is_edit else "Add Transaction", save, extra=extra)
