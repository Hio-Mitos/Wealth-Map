"""
WealthMap – Receipts Panel
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime, timezone

from src.models.database import Receipt
from src.ui.widgets import (
    SectionHeader, StatCard, DataTable, Modal,
    make_entry, make_combo, make_textbox, fmt_money, fmt_money_base,
    attach_currency_tooltip, AttachmentSection, CurrencySearchEntry
)
from src.ui.theme import theme

RECEIPT_CATEGORIES = ["Food & Dining", "Groceries", "Shopping", "Transport",
                       "Healthcare", "Utilities", "Entertainment", "Travel",
                       "Business", "Education", "Other"]


class ReceiptsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._selected = None
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        main = ctk.CTkFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        main.pack(fill="both", expand=True, padx=24, pady=16)
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(2, weight=1)

        SectionHeader(main, "Receipts", "Proof of purchase, organized and searchable",
                      "＋ New Receipt", self._open_new_receipt
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 16))

        # Summary cards
        receipts = self.ctx.session.query(Receipt).order_by(Receipt.created_at.desc()).all()
        total = 0.0
        files = 0
        for r in receipts:
            if r.amount:
                conv = self.ctx.currency.convert(r.amount, r.currency.code if r.currency else base, base)
                total += conv if conv is not None else r.amount
            files += len(r.attachments)

        cards = ctk.CTkFrame(main, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        for i in range(3):
            cards.grid_columnconfigure(i, weight=1)
        StatCard(cards, "Receipts Logged", str(len(receipts)), "", theme.ACCENT, "🧾"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(cards, "Total Spend Recorded", fmt_money(total, sym), base, theme.GOLD, "💵"
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        StatCard(cards, "Files Attached", str(files), "", theme.GREEN, "📎"
                 ).grid(row=0, column=2, sticky="ew")

        cols = [
            {"key": "date",     "label": "Date",     "width": 100, "anchor": "w"},
            {"key": "title",    "label": "Title",    "width": 200, "anchor": "w"},
            {"key": "merchant", "label": "Merchant", "width": 140, "anchor": "w"},
            {"key": "amount",   "label": "Amount",   "width": 100, "anchor": "e"},
            {"key": "category", "label": "Category", "width": 120, "anchor": "w"},
            {"key": "linked",   "label": "Linked Tx","width": 110, "anchor": "w"},
            {"key": "files",    "label": "Files",    "width": 60,  "anchor": "center"},
        ]
        self._table = DataTable(main, cols)
        self._table.grid(row=2, column=0, sticky="nsew", pady=(0, 12))

        self._detail = ctk.CTkFrame(main, fg_color=theme.BG_CARD, corner_radius=10,
                                    border_width=1, border_color=theme.BORDER, height=170)
        self._detail.grid(row=3, column=0, sticky="ew")
        ctk.CTkLabel(self._detail, text="Select a receipt to view details, link it to a "
                                         "transaction, or attach a scan/photo",
                     text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=24)

        self._load_receipts()

    def _load_receipts(self):
        receipts = self.ctx.session.query(Receipt).order_by(Receipt.created_at.desc()).all()
        rows = []
        for r in receipts:
            cur = r.currency
            sym = cur.symbol if cur else ""
            rows.append({
                "date":     r.receipt_date.strftime("%d %b %Y") if r.receipt_date else "—",
                "title":    r.title,
                "merchant": r.merchant or "—",
                "amount":   fmt_money_base(self.ctx, r.amount, cur.code if cur else "") if r.amount else "—",
                "category": r.category or "—",
                "linked":   (r.transaction.description or r.transaction.category) if r.transaction else "—",
                "files":    str(len(r.attachments)),
                "_color_linked": theme.ACCENT if r.transaction else theme.TEXT_SEC,
                "_receipt": r,
                # Raw values for inline editing
                "_raw_date":     r.receipt_date.strftime("%Y-%m-%d") if r.receipt_date else "",
                "_raw_title":    r.title,
                "_raw_merchant": r.merchant or "",
                "_raw_amount":   f"{r.amount:g}" if r.amount else "",
                "_raw_category": r.category or "",
            })
        editable_cols = [
            {"key": "date", "editor": "entry"},
            {"key": "title", "editor": "entry"},
            {"key": "merchant", "editor": "entry"},
            {"key": "amount", "editor": "entry"},
            {"key": "category", "editor": "combo", "options": RECEIPT_CATEGORIES},
        ]
        self._table.set_rows(rows, on_select=self._on_select,
                             editable_cols=editable_cols, on_row_save=self._on_row_save)
        if not rows:
            self._show_empty_state()

    def _show_empty_state(self):
        for w in self._detail.winfo_children():
            w.destroy()
        ctk.CTkLabel(self._detail,
                     text="No receipts yet. Log one with '＋ New Receipt' — you can attach a "
                          "photo or PDF scan and optionally link it to a transaction so your "
                          "spending always has a paper trail.",
                     text_color=theme.TEXT_SEC, font=("Segoe UI", 12),
                     wraplength=600, justify="left").pack(pady=24, padx=16)

    def _on_select(self, row):
        r = row.get("_receipt")
        if not r:
            return
        self._selected = r
        self._show_detail(r)

    def _on_row_save(self, row, new_values):
        r = row.get("_receipt")
        if not r:
            return
        try:
            new_date = datetime.strptime(new_values["date"].strip(), "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in YYYY-MM-DD format")
        title = new_values["title"].strip()
        if not title:
            raise ValueError("Title is required")
        amt_text = new_values["amount"].strip()
        amount = None
        if amt_text:
            try:
                amount = float(amt_text.replace(",", ""))
            except ValueError:
                raise ValueError("Amount must be a number")

        r.receipt_date = new_date
        r.title = title
        r.merchant = new_values["merchant"].strip()
        r.amount = amount
        r.category = new_values["category"].strip() or "Other"
        self.ctx.session.commit()
        self._load_receipts()
        if self._selected and self._selected.id == r.id:
            self._show_detail(r)

    def _show_detail(self, r):
        for w in self._detail.winfo_children():
            w.destroy()

        top = ctk.CTkFrame(self._detail, fg_color="transparent")
        top.pack(fill="x", padx=16, pady=12)

        left = ctk.CTkFrame(top, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text=r.title,
                     font=("Segoe UI", 14, "bold"), text_color=theme.TEXT_PRI).pack(anchor="w")
        sub_parts = []
        if r.merchant:
            sub_parts.append(r.merchant)
        if r.amount:
            cur = r.currency
            sub_parts.append(fmt_money(r.amount, cur.symbol if cur else ""))
        if r.receipt_date:
            sub_parts.append(r.receipt_date.strftime("%d %b %Y"))
        if sub_parts:
            ctk.CTkLabel(left, text="  •  ".join(sub_parts),
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w")
        if r.transaction:
            ctk.CTkLabel(left, text=f"🔗 Linked to: {r.transaction.description or r.transaction.category} "
                                     f"({r.transaction.transaction_date.strftime('%d %b %Y')})",
                         font=("Segoe UI", 11), text_color=theme.ACCENT).pack(anchor="w", pady=(2, 0))

        btn_row = ctk.CTkFrame(top, fg_color="transparent")
        btn_row.pack(side="right")
        ctk.CTkButton(btn_row, text="＋ Attach File", width=110, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=lambda: self._attach(r)).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="✎ Edit", width=70, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=lambda: self._edit_receipt(r)).pack(side="left", padx=2)
        ctk.CTkButton(btn_row, text="🗑", width=36, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.RED, font=("Segoe UI", 11),
                      command=lambda: self._delete_receipt(r)).pack(side="left", padx=2)

        if r.notes:
            ctk.CTkLabel(self._detail, text=r.notes,
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         wraplength=600, justify="left").pack(anchor="w", padx=16, pady=(0, 8))

        for att in r.attachments:
            row_f = ctk.CTkFrame(self._detail, fg_color=theme.ROW_ALT, corner_radius=6)
            row_f.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(row_f, text=f"📎 {att.original_filename}",
                         font=("Segoe UI", 11), text_color=theme.ACCENT).pack(side="left", padx=8, pady=4)
            ctk.CTkButton(row_f, text="Open", width=60, height=24,
                          fg_color="transparent", text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=lambda a=att: self.ctx.attachment.open_file(a)
                          ).pack(side="right", padx=4, pady=2)
            ctk.CTkButton(row_f, text="✕", width=28, height=24,
                          fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                          command=lambda a=att: self._delete_attachment(a, r)
                          ).pack(side="right", pady=2)
        if not r.attachments:
            ctk.CTkLabel(self._detail, text="No files attached yet",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 11)).pack(padx=16, pady=(0, 8))

    def _attach(self, r):
        path = filedialog.askopenfilename(title="Attach to receipt",
            filetypes=[("All files", "*.*"),
                       ("Documents & images", "*.pdf *.png *.jpg *.jpeg *.doc *.docx *.txt *.csv")])
        if not path:
            return
        try:
            self.ctx.attachment.save_file(path, self.ctx.session, "receipt", r.id)
            self.ctx.session.refresh(r)
            self._show_detail(r)
            self._load_receipts()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _delete_attachment(self, att, r):
        if messagebox.askyesno("Delete Attachment", f"Remove '{att.original_filename}'?"):
            self.ctx.attachment.delete_file(att, self.ctx.session)
            self.ctx.session.refresh(r)
            self._show_detail(r)
            self._load_receipts()

    def _delete_receipt(self, r):
        if messagebox.askyesno("Delete Receipt", f"Delete receipt '{r.title}'?"):
            self.ctx.session.delete(r)
            self.ctx.session.commit()
            self._selected = None
            self._load_receipts()
            self._show_empty_state()

    # ── New / edit receipt ───────────────────────────────────────────────────

    def _open_new_receipt(self):
        self._receipt_modal(None)

    def _edit_receipt(self, r):
        self._receipt_modal(r)

    def _receipt_modal(self, r):
        is_edit = r is not None
        modal = Modal(self, "Edit Receipt" if is_edit else "New Receipt", width=460, height=620)

        # Recent transactions for linking
        recent_txs = self.ctx.transaction.get_recent(100)
        tx_options = ["(none)"] + [
            f"#{tx.id} — {tx.transaction_date.strftime('%d %b')} — "
            f"{(tx.description or tx.category)[:30]}"
            for tx in recent_txs
        ]
        tx_by_label = {opt: tx for opt, tx in zip(tx_options[1:], recent_txs)}

        title_e  = modal.add_field("Title / Item",  lambda p: make_entry(p, "What did you buy?"))
        merch_e  = modal.add_field("Merchant",      lambda p: make_entry(p, "Store or vendor name"))
        amt_e    = modal.add_field("Amount",        lambda p: make_entry(p, "0.00"))
        cur_c    = modal.add_field("Currency",      lambda p: CurrencySearchEntry(p, self.ctx))
        attach_currency_tooltip(cur_c, self.ctx)
        date_e   = modal.add_field("Date (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
        cat_c    = modal.add_field("Category",      lambda p: make_combo(p, RECEIPT_CATEGORIES))
        tx_c     = modal.add_field("Link to Transaction (optional)", lambda p: make_combo(p, tx_options))
        notes_t  = modal.add_field("Notes",         lambda p: make_textbox(p, height=60))

        att_section = AttachmentSection(modal.body, self.ctx, "receipt",
                                        entity=r if is_edit else None)
        att_section.pack(fill="x")

        if is_edit:
            title_e.insert(0, r.title)
            merch_e.insert(0, r.merchant or "")
            if r.amount:
                amt_e.insert(0, f"{r.amount:g}")
            cur_c.set(r.currency.code if r.currency else "USD")
            date_e.insert(0, r.receipt_date.strftime("%Y-%m-%d") if r.receipt_date else
                         datetime.now().strftime("%Y-%m-%d"))
            cat_c.set(r.category or "Other")
            if r.transaction:
                label = next((lbl for lbl, tx in tx_by_label.items() if tx.id == r.transaction_id), "(none)")
                tx_c.set(label)
            else:
                tx_c.set("(none)")
            notes_t.insert("1.0", r.notes or "")
        else:
            cur_c.set("USD")
            cat_c.set("Shopping")
            tx_c.set("(none)")
            date_e.insert(0, datetime.now().strftime("%Y-%m-%d"))

        def save():
            cur_c.resolve()
            try:
                title = title_e.get().strip()
                if not title:
                    raise ValueError("Title is required")
                amt_str = amt_e.get().strip()
                amount  = float(amt_str.replace(",", "")) if amt_str else None
                cur = self.ctx.currency.get_by_code(cur_c.get())
                try:
                    rdate = datetime.strptime(date_e.get().strip(), "%Y-%m-%d")
                except ValueError:
                    rdate = datetime.now(timezone.utc)

                linked_tx = tx_by_label.get(tx_c.get())

                if is_edit:
                    r.title = title
                    r.merchant = merch_e.get().strip()
                    r.amount = amount
                    r.currency_id = cur.id if cur else None
                    r.receipt_date = rdate
                    r.category = cat_c.get()
                    r.transaction_id = linked_tx.id if linked_tx else None
                    r.notes = notes_t.get("1.0", "end").strip()
                else:
                    rec = Receipt(
                        title=title, merchant=merch_e.get().strip(),
                        amount=amount,
                        currency_id=cur.id if cur else None,
                        receipt_date=rdate,
                        category=cat_c.get(),
                        transaction_id=linked_tx.id if linked_tx else None,
                        notes=notes_t.get("1.0", "end").strip()
                    )
                    self.ctx.session.add(rec)
                    self.ctx.session.commit()
                    att_section.commit(rec.id)
                    modal.destroy()
                    self._load_receipts()
                    return
                self.ctx.session.commit()
                modal.destroy()
                self._load_receipts()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        extra = None
        if is_edit:
            extra = [("Delete Receipt", lambda: (modal.destroy(), self._delete_receipt(r)), theme.RED)]

        modal.add_buttons("Save Changes" if is_edit else "Save Receipt", save, extra=extra)
