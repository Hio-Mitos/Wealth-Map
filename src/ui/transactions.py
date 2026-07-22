"""
WealthMap – Transactions Panel
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime

from src.models.database import TransactionType, CREDIT_TRANSACTION_TYPES
from src.ui.widgets import (
    SectionHeader, DataTable,
    make_entry, make_combo, fmt_money, fmt_money_base,
)
from src.ui.theme import theme
from src.ui.payslip_dialog import open_payslip_import_dialog, show_payslip_viewer
from src.ui.transaction_dialog import open_transaction_modal


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
                      "＋ New Transaction", lambda: self._open_tx_modal(),
                      extra_buttons=[("📄 Import Payslip", self._import_payslip)]).pack(fill="x")

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

        payslip = self.ctx.payslip.get_for_transaction(tx.id)
        if payslip:
            ctk.CTkButton(action_row, text="🧾 View Full Payslip", width=160, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.GOLD, font=("Segoe UI", 11),
                          command=lambda: show_payslip_viewer(self, payslip, ctx=self.ctx, app=self.app)
                          ).pack(side="left", padx=6)

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

    def _import_payslip(self):
        def _after():
            self.app.refresh()
            self._load_transactions()
        open_payslip_import_dialog(self, self.ctx, on_done=_after)

    def _open_tx_modal(self, tx=None):
        open_transaction_modal(self, self.ctx, self.app, tx,
                               on_saved=self._on_tx_saved, on_deleted=self._on_tx_deleted)

    def _on_tx_saved(self, saved_tx, was_edit):
        self.app.refresh()
        self._load_transactions()
        if was_edit:
            self._show_detail(saved_tx)

    def _on_tx_deleted(self):
        self._selected_tx = None
        self.app.refresh()
        self._load_transactions()
        for w in self._detail_frame.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._detail_frame, text="Select a transaction to view details",
                     text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=12)

    def on_resize(self, width: int):
        pass
