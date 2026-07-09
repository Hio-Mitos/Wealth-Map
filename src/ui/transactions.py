"""
WealthMap – Transactions Panel
"""

import os
import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime, timezone

from src.models.database import (TransactionType, TransactionStatus,
                                 CREDIT_TRANSACTION_TYPES, DEBIT_TRANSACTION_TYPES)
from src.services.profiles import list_remote_accounts
from src.ui.widgets import (
    SectionHeader, DataTable, Modal,
    make_entry, make_combo, make_textbox, fmt_money, fmt_money_base,
    color_for_amount, attach_currency_tooltip, AttachmentSection
)
from src.ui.theme import theme


class TransactionsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app, initial_account: str = None, initial_type: str = None):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._filter_account = initial_account or "All Accounts"
        self._filter_type    = initial_type or "All Types"
        self._selected_tx    = None
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        self._sym = base_cur.symbol if base_cur else ""
        self._base = base

        # Header
        hdr = ctk.CTkFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        hdr.pack(fill="x", padx=24, pady=(16, 8))

        subtitle = "Complete financial ledger"
        if self._filter_account != "All Accounts":
            subtitle = f"Filtered to: {self._filter_account}"
        SectionHeader(hdr, "Transactions", subtitle,
                      "＋ New Transaction", lambda: self._open_tx_modal()).pack(fill="x")

        # Filter bar
        filter_bar = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=10,
                                  border_width=1, border_color=theme.BORDER)
        filter_bar.pack(fill="x", padx=24, pady=(0, 8))

        ctk.CTkLabel(filter_bar, text="Filter:", text_color=theme.TEXT_SEC,
                     font=("Segoe UI", 12)).pack(side="left", padx=(12, 8), pady=10)

        accounts = ["All Accounts"] + [a.name for a in self.ctx.account.get_all()]
        self._acc_filter = make_combo(filter_bar, accounts, width=180, command=self._apply_filter)
        self._acc_filter.set(self._filter_account if self._filter_account in accounts else "All Accounts")
        self._acc_filter.pack(side="left", padx=4, pady=8)

        custom_type_names = [ct.name for ct in self.ctx.customization.get_custom_types()]
        types = ["All Types"] + [t.value for t in TransactionType
                if t not in (TransactionType.CUSTOM_CREDIT, TransactionType.CUSTOM_DEBIT)] + custom_type_names
        self._type_filter = make_combo(filter_bar, types, width=160, command=self._apply_filter)
        self._type_filter.set(self._filter_type if self._filter_type in types else "All Types")
        self._type_filter.pack(side="left", padx=4, pady=8)

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *a: self._apply_filter())
        search = make_entry(filter_bar, "Search description, payee…", width=200)
        search.configure(textvariable=self._search_var)
        search.pack(side="left", padx=4, pady=8)

        ctk.CTkButton(filter_bar, text="Clear", width=70, height=32,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=self._clear_filter).pack(side="left", padx=4)

        self._count_label = ctk.CTkLabel(filter_bar, text="",
                                          text_color=theme.TEXT_SEC, font=("Segoe UI", 11))
        self._count_label.pack(side="right", padx=12)

        # Table
        cols = [
            {"key": "date",       "label": "Date",        "width": 90,  "anchor": "w"},
            {"key": "account",    "label": "Account",     "width": 130, "anchor": "w"},
            {"key": "type",       "label": "Type",        "width": 100, "anchor": "w"},
            {"key": "description","label": "Description", "width": 180, "anchor": "w"},
            {"key": "category",   "label": "Category",    "width": 120, "anchor": "w"},
            {"key": "payee",      "label": "Payee",        "width": 110, "anchor": "w"},
            {"key": "amount",     "label": "Amount",       "width": 100, "anchor": "e"},
            {"key": "currency",   "label": "CCY",          "width": 50,  "anchor": "w"},
            {"key": "fees_taxes", "label": "Fees/Taxes",   "width": 90,  "anchor": "e"},
            {"key": "status",     "label": "Status",       "width": 90,  "anchor": "w"},
        ]
        self._table = DataTable(self, cols, height=400)
        self._table.pack(fill="both", expand=True, padx=24, pady=(0, 16))

        # Detail + attachments panel
        self._detail_frame = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=10,
                                          border_width=1, border_color=theme.BORDER)
        self._detail_frame.pack(fill="x", padx=24, pady=(0, 16))
        ctk.CTkLabel(self._detail_frame, text="Select a transaction to view details",
                     text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=12)

        self._load_transactions()

    # ── Filtering ─────────────────────────────────────────────────────────────

    def _get_transactions(self):
        acc_name = self._acc_filter.get() if hasattr(self, "_acc_filter") else "All Accounts"
        type_val = self._type_filter.get() if hasattr(self, "_type_filter") else "All Types"
        search   = self._search_var.get().lower() if hasattr(self, "_search_var") else ""

        txs = self.ctx.transaction.get_recent(500)
        result = []
        for tx in txs:
            if acc_name != "All Accounts" and tx.account.name != acc_name:
                continue
            if type_val != "All Types" and tx.display_type != type_val:
                continue
            if search:
                haystack = f"{tx.description} {tx.payee} {tx.category} {tx.reference}".lower()
                if search not in haystack:
                    continue
            result.append(tx)
        return result

    def _load_transactions(self):
        from src.models.database import TransactionType as TT
        txs = self._get_transactions()
        rows = []
        for tx in txs:
            is_credit = tx.transaction_type in CREDIT_TRANSACTION_TYPES or (
                tx.transaction_type == TT.ADJUSTMENT and tx.amount >= 0)
            color = theme.GREEN if is_credit else theme.RED
            sign  = "+" if is_credit else "−"
            cur   = tx.currency
            sym   = cur.symbol if cur else ""
            ft    = tx.total_fees_taxes
            ft_sym = (tx.fee_currency or tx.tax_currency or cur)
            ft_sym = ft_sym.symbol if ft_sym else ""
            amt_str = fmt_money_base(self.ctx, abs(tx.amount), cur.code if cur else self._base)
            rows.append({
                "date":        tx.transaction_date.strftime("%d %b %Y"),
                "account":     tx.account.name if tx.account else "—",
                "type":        tx.display_type,
                "description": tx.description or "—",
                "category":    tx.category or "—",
                "payee":       tx.payee or "—",
                "amount":      f"{sign}{amt_str}",
                "currency":    cur.code if cur else "—",
                "fees_taxes":  f"{ft_sym}{ft:,.2f}" if ft else "—",
                "status":      tx.status.value,
                "_color_amount": color,
                "_color_fees_taxes": theme.GOLD if ft else theme.TEXT_SEC,
                "_tx_obj":     tx,
                # Raw values for inline editing
                "_raw_date":        tx.transaction_date.strftime("%Y-%m-%d"),
                "_raw_description": tx.description or "",
                "_raw_category":    tx.category or "",
                "_raw_payee":       tx.payee or "",
                "_raw_amount":      f"{tx.amount:g}",
            })
        editable_cols = [
            {"key": "date", "editor": "entry"},
            {"key": "description", "editor": "entry"},
            {"key": "category", "editor": "combo", "options": self.ctx.customization.get_categories()},
            {"key": "payee", "editor": "entry"},
            {"key": "amount", "editor": "entry"},
        ]
        self._table.set_rows(rows, on_select=self._on_tx_select,
                             editable_cols=editable_cols, on_row_save=self._on_row_save)
        self._count_label.configure(text=f"{len(rows)} transactions")

    def _on_row_save(self, row, new_values):
        tx = row.get("_tx_obj")
        if not tx:
            return
        try:
            new_date = datetime.strptime(new_values["date"].strip(), "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        amt_text = new_values["amount"].strip().replace(",", "")
        try:
            new_amount = float(amt_text)
        except ValueError:
            raise ValueError("Amount must be a number")
        if tx.transaction_type != TransactionType.ADJUSTMENT and new_amount <= 0:
            raise ValueError("Amount must be positive")
        if new_amount == 0:
            raise ValueError("Amount cannot be zero")

        self.ctx.transaction.update(
            tx,
            transaction_date=new_date,
            description=new_values["description"].strip(),
            category=new_values["category"].strip() or "Other",
            payee=new_values["payee"].strip(),
            amount=new_amount,
        )
        self.app.refresh()
        self._load_transactions()
        if self._selected_tx and self._selected_tx.id == tx.id:
            self._show_detail(tx)

    def _apply_filter(self, *_):
        self._load_transactions()

    def _clear_filter(self):
        self._acc_filter.set("All Accounts")
        self._type_filter.set("All Types")
        self._search_var.set("")
        self._load_transactions()

    # ── Detail view ───────────────────────────────────────────────────────────

    def _on_tx_select(self, row):
        tx = row.get("_tx_obj")
        if not tx:
            return
        self._selected_tx = tx
        self._show_detail(tx)

    def _show_detail(self, tx):
        for w in self._detail_frame.winfo_children():
            w.destroy()

        cur = tx.currency
        sym = cur.symbol if cur else ""

        top = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=(12, 4))

        info = [
            ("ID",          f"#{tx.id}"),
            ("Account",     tx.account.name if tx.account else "—"),
            ("Type",        tx.display_type),
            ("Category",    tx.category),
            ("Date",        tx.transaction_date.strftime("%d %B %Y %H:%M")),
            ("Amount",      fmt_money(tx.amount, sym)),
            ("Currency",    cur.code if cur else "—"),
            ("Status",      tx.status.value),
            ("Payee",       tx.payee or "—"),
            ("Reference",   tx.reference or "—"),
        ]
        if tx.linked_account:
            info.insert(2, ("Linked Account", tx.linked_account.name))
        elif tx.linked_account_label:
            info.insert(2, ("Linked Account", f"🔗 {tx.linked_account_label} (linked profile)"))
        if tx.notes:
            info.append(("Notes", tx.notes))

        for i, (lbl, val) in enumerate(info):
            col = i % 4
            rw  = i // 4
            cell = ctk.CTkFrame(top, fg_color="transparent")
            cell.grid(row=rw, column=col, padx=12, pady=4, sticky="w")
            ctk.CTkLabel(cell, text=lbl, font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="w")
            ctk.CTkLabel(cell, text=val, font=("Segoe UI", 12), text_color=theme.TEXT_PRI).pack(anchor="w")

        # Fees & taxes row
        if tx.total_fees_taxes:
            ft_frame = ctk.CTkFrame(self._detail_frame, fg_color=theme.BG_HOVER, corner_radius=8)
            ft_frame.pack(fill="x", padx=16, pady=(4, 8))
            parts = []
            if tx.fee_amount:
                fcur = tx.fee_currency or cur
                parts.append(f"Fee: {fmt_money(tx.fee_amount, fcur.symbol if fcur else '')}"
                            f"{' — ' + tx.fee_description if tx.fee_description else ''}")
            if tx.tax_amount:
                tcur = tx.tax_currency or cur
                parts.append(f"Tax: {fmt_money(tx.tax_amount, tcur.symbol if tcur else '')}"
                            f"{' — ' + tx.tax_description if tx.tax_description else ''}")
            ctk.CTkLabel(ft_frame, text="  •  ".join(parts), font=("Segoe UI", 11, "bold"),
                         text_color=theme.GOLD).pack(anchor="w", padx=12, pady=8)

        # Action buttons
        action_row = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        action_row.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkButton(action_row, text="✎ Edit", width=90, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=lambda: self._open_tx_modal(tx)).pack(side="left")
        ctk.CTkButton(action_row, text="🗑 Delete", width=90, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.RED, font=("Segoe UI", 11),
                      command=lambda: self._delete_tx(tx)).pack(side="left", padx=6)

        # Attachments section
        att_frame = ctk.CTkFrame(self._detail_frame, fg_color="transparent")
        att_frame.pack(fill="x", padx=16, pady=(0, 4))
        ctk.CTkLabel(att_frame, text="Attachments",
                     font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_SEC).pack(side="left")
        ctk.CTkButton(att_frame, text="＋ Attach File", width=110, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=lambda: self._attach_file(tx)).pack(side="left", padx=8)

        for att in tx.attachments:
            row = ctk.CTkFrame(self._detail_frame, fg_color=theme.BG_DARK, corner_radius=6)
            row.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(row, text=f"📎 {att.original_filename}",
                         font=("Segoe UI", 11), text_color=theme.ACCENT).pack(side="left", padx=8, pady=4)
            size_kb = att.file_size // 1024
            ctk.CTkLabel(row, text=f"{size_kb} KB",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(side="left", padx=4)
            ctk.CTkButton(row, text="Open", width=60, height=24,
                          fg_color="transparent", text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=lambda a=att: self.ctx.attachment.open_file(a)).pack(side="right", padx=4)
            ctk.CTkButton(row, text="✕", width=28, height=24,
                          fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                          command=lambda a=att: self._delete_attachment(a, tx)).pack(side="right")

        if not tx.attachments:
            ctk.CTkLabel(self._detail_frame, text="No attachments",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(padx=16, pady=(0, 8))

    def _attach_file(self, tx):
        path = filedialog.askopenfilename(
            title="Attach file to transaction",
            filetypes=[("All files", "*.*"),
                       ("Documents & images", "*.pdf *.png *.jpg *.jpeg *.gif *.doc *.docx *.xls *.xlsx *.csv *.txt")]
        )
        if not path:
            return
        try:
            self.ctx.attachment.save_file(path, self.ctx.session, "transaction", tx.id)
            self.ctx.session.refresh(tx)
            self._show_detail(tx)
        except Exception as e:
            messagebox.showerror("Attach Error", str(e))

    def _delete_attachment(self, att, tx):
        if messagebox.askyesno("Delete Attachment", f"Remove '{att.original_filename}'?"):
            self.ctx.attachment.delete_file(att, self.ctx.session)
            self.ctx.session.refresh(tx)
            self._show_detail(tx)

    def _delete_tx(self, tx):
        msg = f"Delete this {tx.display_type} transaction?"
        if tx.transfer_group_id:
            msg += "\n\nThis is one leg of a transfer — both legs will be deleted."
        if messagebox.askyesno("Delete Transaction", msg):
            self.ctx.transaction.delete(tx)
            self._selected_tx = None
            self.app.refresh()
            self._load_transactions()
            for w in self._detail_frame.winfo_children():
                w.destroy()
            ctk.CTkLabel(self._detail_frame, text="Select a transaction to view details",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=12)

    # ── New / Edit transaction modal ────────────────────────────────────────

    def _open_tx_modal(self, tx=None):
        is_edit = tx is not None
        modal = Modal(self, "Edit Transaction" if is_edit else "New Transaction",
                      width=560, height=820)

        accounts  = self.ctx.account.get_all()
        acc_names = [a.name for a in accounts]
        custom_types = self.ctx.customization.get_custom_types()
        # Internal-only generic buckets aren't shown directly; custom type
        # names (backed by those buckets) are shown instead.
        tx_types  = [t.value for t in TransactionType
                    if t not in (TransactionType.CUSTOM_CREDIT, TransactionType.CUSTOM_DEBIT)]
        tx_types += [ct.name for ct in custom_types]
        tx_status = [s.value for s in TransactionStatus]
        currencies= [c.code for c in self.ctx.currency.get_all()]

        if not acc_names:
            messagebox.showerror("No Accounts", "Create an account first.", parent=modal)
            modal.destroy()
            return

        acc_c   = modal.add_field("Account",          lambda p: make_combo(p, acc_names))
        type_c  = modal.add_field("Transaction Type", lambda p: make_combo(p, tx_types,
                                  command=lambda v: self._toggle_transfer_field(transfer_lbl, v)))
        amt_e   = modal.add_field("Amount",           lambda p: make_entry(p, "0.00"))
        cur_c   = modal.add_field("Currency",         lambda p: make_combo(p, currencies))
        attach_currency_tooltip(cur_c, self.ctx)

        # Accounts in linked profiles of the same type (for cross-profile transfers)
        remote_account_map = {}  # label -> {profile_id, profile_name, account_id, account_name, currency_code}
        if self.ctx.registry:
            for lp in self.ctx.registry.linked_profiles(self.ctx.profile["id"]):
                for ra in list_remote_accounts(self.ctx.registry.db_path(lp["id"])):
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
                        converted = self.ctx.currency.convert(amt, from_code, to_code)
                        if converted is not None:
                            cur_obj = self.ctx.currency.get_by_code(to_code)
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
        cur_c.configure(command=lambda v: update_preview())

        NEW_CATEGORY_OPTION = "＋ New Category..."

        def on_category_pick(value):
            if value != NEW_CATEGORY_OPTION:
                return
            from tkinter import simpledialog
            name = simpledialog.askstring("New Category", "Category name:", parent=modal)
            if name and name.strip():
                try:
                    self.ctx.customization.add_category(name.strip())
                    cat_c.configure(values=self.ctx.customization.get_categories() + [NEW_CATEGORY_OPTION])
                    cat_c.set(name.strip())
                except Exception as e:
                    messagebox.showerror("Error", str(e), parent=modal)
                    cat_c.set("Other")
            else:
                cat_c.set("Other")

        desc_e  = modal.add_field("Description",      lambda p: make_entry(p, "What was this for?"))
        cat_c   = modal.add_field("Category",         lambda p: make_combo(
            p, self.ctx.customization.get_categories() + [NEW_CATEGORY_OPTION],
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
        fee_cur_c = make_combo(fee_row, currencies, width=90)
        fee_cur_c.pack(side="left")
        attach_currency_tooltip(fee_cur_c, self.ctx)
        fee_desc_e = make_entry(modal.body, "Fee description (e.g. wire fee, ATM fee)")
        fee_desc_e.pack(fill="x", pady=(2, 8))

        tax_row = ctk.CTkFrame(modal.body, fg_color="transparent")
        tax_row.pack(fill="x", pady=(0, 4))
        tax_amt_e = make_entry(tax_row, "Tax amount")
        tax_amt_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
        tax_cur_c = make_combo(tax_row, currencies, width=90)
        tax_cur_c.pack(side="left")
        attach_currency_tooltip(tax_cur_c, self.ctx)
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
            cur_c2 = make_combo(row, currencies, width=80)
            default_code = (prefill.currency.code if (prefill and prefill.currency) else cur_c.get())
            cur_c2.set(default_code)
            cur_c2.pack(side="left", padx=4, pady=4)
            attach_currency_tooltip(cur_c2, self.ctx)
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
        if self.ctx.is_business:
            departments = self.ctx.department.get_all()
            dept_options = ["(none)"] + [d.name for d in departments]
            dept_c = modal.add_field("Department", lambda p: make_combo(p, dept_options))
            dept_c.set("(none)")
            if is_edit and tx.department:
                dept_c.set(tx.department.name)

        att_section = AttachmentSection(modal.body, self.ctx, "transaction",
                                        entity=tx if is_edit else None)
        att_section.pack(fill="x")

        # ── Defaults / prefill ──────────────────────────────────────────────
        if is_edit:
            acc_c.set(tx.account.name if tx.account else acc_names[0])
            type_c.set(tx.display_type)
            self._toggle_transfer_field(transfer_lbl, tx.transaction_type.value)
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
            self._toggle_transfer_field(transfer_lbl, tx_types[0])
            stat_c.set("Cleared")
            cat_c.set("Other")
            date_e.insert(0, datetime.now().strftime("%Y-%m-%d"))
            fee_cur_c.set(accounts[0].currency.code)
            tax_cur_c.set(accounts[0].currency.code)

        def save():
            try:
                acc_name = acc_c.get()
                acc = next((a for a in accounts if a.name == acc_name), None)
                if not acc:
                    raise ValueError("Select a valid account")
                amount = float(amt_e.get().replace(",", ""))
                tx_type, custom_label = self.ctx.customization.resolve_type(type_c.get())
                if tx_type == TransactionType.ADJUSTMENT:
                    if amount == 0:
                        raise ValueError("Adjustment amount cannot be zero")
                elif amount <= 0:
                    raise ValueError("Amount must be positive")
                status  = next(s for s in TransactionStatus if s.value == stat_c.get())
                notes   = notes_t.get("1.0", "end").strip()

                try:
                    tx_date = datetime.strptime(date_e.get().strip(), "%Y-%m-%d")
                except ValueError:
                    raise ValueError("Date must be in YYYY-MM-DD format")

                fee_amount = self._parse_float(fee_amt_e.get()) or 0.0
                tax_amount = self._parse_float(tax_amt_e.get()) or 0.0

                charges_list = []
                for entry in charge_rows:
                    c_amt = self._parse_float(entry["amount"].get())
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
                    dept = next((d for d in self.ctx.department.get_all() if d.name == dept_c.get()), None)
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
                    self.ctx.transaction.update(tx, **fields)
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
                        new_tx = self.ctx.cross_profile_transfer(
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
                        new_tx = self.ctx.transaction.add(
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
                modal.destroy()
                self.app.refresh()
                self._load_transactions()
                if is_edit:
                    self._show_detail(tx)
            except ValueError as e:
                messagebox.showerror("Validation Error", str(e), parent=modal)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        extra = None
        if is_edit:
            extra = [("Delete Transaction", lambda: self._delete_from_modal(modal, tx), theme.RED)]

        modal.add_buttons("Save Changes" if is_edit else "Add Transaction", save, extra=extra)

    def _delete_from_modal(self, modal, tx):
        msg = f"Delete this {tx.display_type} transaction?"
        if tx.transfer_group_id:
            msg += "\n\nThis is one leg of a transfer — both legs will be deleted."
        if messagebox.askyesno("Delete Transaction", msg, parent=modal):
            self.ctx.transaction.delete(tx)
            modal.destroy()
            self._selected_tx = None
            self.app.refresh()
            self._load_transactions()
            for w in self._detail_frame.winfo_children():
                w.destroy()
            ctk.CTkLabel(self._detail_frame, text="Select a transaction to view details",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=12)

    def _toggle_transfer_field(self, transfer_lbl, value):
        if value == TransactionType.TRANSFER.value:
            transfer_lbl.configure(text="Transfer To Account (required)")
        else:
            transfer_lbl.configure(text="Also Affects Account (optional)")

    @staticmethod
    def _parse_float(text):
        text = (text or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def on_resize(self, width: int):
        pass
