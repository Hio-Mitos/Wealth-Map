"""
WealthMap – Accounts Panel
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime, timezone

from src.models.database import AccountType
from src.ui.widgets import (safe_rebuild,
    SectionHeader, StatCard, DataTable, Modal,
    make_entry, make_combo, make_textbox, fmt_money,
    attach_currency_tooltip, responsive_columns, CurrencySearchEntry
)
from src.ui.theme import theme

ACCOUNT_COLORS = ["#4A90D9", "#7ED321", "#9B59B6", "#F5A623", "#E74C3C",
                  "#1ABC9C", "#3498DB", "#E67E22", "#2ECC71", "#E91E63"]


class AccountsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._col_count = 3
        self._build()

    # ── Responsive ────────────────────────────────────────────────────────────

    def on_resize(self, width: int):
        new_cols = responsive_columns(width - 240, min_col_width=280, max_cols=4)
        if new_cols != self._col_count:
            self._col_count = new_cols
            self._rebuild()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        main = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        main.pack(fill="both", expand=True, padx=24, pady=16)
        main.grid_columnconfigure(0, weight=1)

        SectionHeader(main, "Accounts", "All your money containers",
                      "＋ New Account", self._open_new_account
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 20))

        # Accounts grid
        accounts = self.ctx.account.get_all()
        cards_frame = ctk.CTkFrame(main, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 24))

        col_count = max(1, self._col_count)
        for col in range(col_count):
            cards_frame.grid_columnconfigure(col, weight=1)

        for i, acc in enumerate(accounts):
            row_i, col_i = divmod(i, col_count)
            bal = self.ctx.account.get_balance(acc)
            bal_base = self.ctx.account.get_balance_in_base(acc, base)
            cur = acc.currency

            card = ctk.CTkFrame(cards_frame, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
            card.grid(row=row_i, column=col_i, padx=(0 if col_i == 0 else 8, 0),
                      pady=(0, 12), sticky="nsew")

            # Color strip
            strip = ctk.CTkFrame(card, height=4, fg_color=acc.color, corner_radius=0)
            strip.pack(fill="x")

            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="both", expand=True, padx=16, pady=12)

            top = ctk.CTkFrame(body, fg_color="transparent")
            top.pack(fill="x")
            ctk.CTkLabel(top, text=acc.account_type.value,
                         font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(side="left")
            if acc.institution:
                ctk.CTkLabel(top, text=acc.institution,
                             font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(side="right")

            ctk.CTkLabel(body, text=acc.name,
                         font=("Segoe UI", 15, "bold"), text_color=theme.TEXT_PRI, anchor="w").pack(fill="x", pady=(4, 0))

            if acc.account_type == AccountType.CREDIT_CARD:
                self._build_credit_card_body(body, acc, cur, base, sym, bal_base)
            else:
                ctk.CTkLabel(body, text=fmt_money(bal, cur.symbol if cur else ""),
                             font=("Segoe UI", 22, "bold"), text_color=acc.color, anchor="w").pack(fill="x", pady=(2, 0))

                if bal_base is not None and cur and cur.code != base:
                    ctk.CTkLabel(body, text=f"≈ {fmt_money(bal_base, sym)} {base}",
                                 font=("Segoe UI", 11), text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")

            btn_row = ctk.CTkFrame(body, fg_color="transparent")
            btn_row.pack(fill="x", pady=(10, 0))
            ctk.CTkButton(btn_row, text="Transactions", width=110, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=lambda a=acc: self._view_transactions(a)
                          ).pack(side="left")
            ctk.CTkButton(btn_row, text="Edit", width=60, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                          command=lambda a=acc: self._edit_account(a)
                          ).pack(side="left", padx=6)

        if not accounts:
            ctk.CTkLabel(cards_frame, text="No accounts yet. Click '＋ New Account' to get started.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 13)).grid(row=0, column=0, pady=40)

    def _build_credit_card_body(self, body, acc, cur, base, sym, bal_base):
        info = self.ctx.account.credit_card_info(acc)
        csym = cur.symbol if cur else ""
        owed_color = theme.RED if info["owed"] > 0 else theme.GREEN
        ctk.CTkLabel(body, text=f"Owed: {fmt_money(info['owed'], csym)}",
                     font=("Segoe UI", 22, "bold"), text_color=owed_color, anchor="w").pack(fill="x", pady=(2, 0))
        if info["limit"]:
            ctk.CTkLabel(body, text=f"Available credit: {fmt_money(info['available'], csym)} "
                                     f"of {fmt_money(info['limit'], csym)}",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")
            # Utilization bar
            bar_bg = ctk.CTkFrame(body, height=6, fg_color=theme.BG_HOVER, corner_radius=3)
            bar_bg.pack(fill="x", pady=(6, 0))
            util = min(1.0, info["utilization_pct"] / 100.0)
            if util > 0:
                bar_fg = ctk.CTkFrame(bar_bg, height=6,
                                      fg_color=(theme.RED if util > 0.8 else
                                                theme.GOLD if util > 0.5 else theme.GREEN),
                                      corner_radius=3)
                bar_fg.place(relx=0, rely=0, relwidth=util, relheight=1)
        if acc.payment_due_day:
            ctk.CTkLabel(body, text=f"Payment due day: {acc.payment_due_day}  •  "
                                     f"Statement closes: {acc.statement_day or '—'}",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC, anchor="w").pack(fill="x", pady=(4, 0))
        if acc.interest_rate:
            ctk.CTkLabel(body, text=f"APR: {acc.interest_rate:.2f}%",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")

    # ── New account ─────────────────────────────────────────────────────────

    def _open_new_account(self):
        modal = Modal(self, "New Account", width=480, height=640)
        b = modal.body

        acc_types  = [t.value for t in AccountType]

        name_e   = modal.add_field("Account Name",    lambda p: make_entry(p, "e.g. Main Chequing"))
        type_c   = modal.add_field("Account Type",    lambda p: make_combo(p, acc_types, command=lambda v: self._toggle_cc_fields(cc_frame, v)))
        inst_e   = modal.add_field("Institution",     lambda p: make_entry(p, "Bank / Broker / Card issuer"))
        acno_e   = modal.add_field("Account Number",  lambda p: make_entry(p, "Last 4 digits (optional)"))
        cur_c    = modal.add_field("Currency",        lambda p: CurrencySearchEntry(p, self.ctx))
        attach_currency_tooltip(cur_c, self.ctx)
        desc_t   = modal.add_field("Description",     lambda p: make_textbox(p, height=60))

        # Credit-card-only fields (shown/hidden based on account type)
        cc_frame = ctk.CTkFrame(b, fg_color="transparent")
        cc_frame.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(cc_frame, text="💳 Credit Card Details", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(4, 4))
        limit_e = ctk.CTkFrame(cc_frame, fg_color="transparent")
        limit_e.pack(fill="x")
        limit_entry = make_entry(limit_e, "Credit limit, e.g. 5000")
        limit_entry.pack(fill="x", pady=(0, 6))
        row2 = ctk.CTkFrame(cc_frame, fg_color="transparent")
        row2.pack(fill="x")
        stmt_entry = make_entry(row2, "Statement day (1-31)")
        stmt_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        due_entry = make_entry(row2, "Payment due day (1-31)")
        due_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        apr_entry = make_entry(cc_frame, "APR / interest rate %, e.g. 21.99")
        apr_entry.pack(fill="x", pady=(6, 0))
        cc_frame.pack_forget()  # hidden by default

        # Color picker
        ctk.CTkLabel(b, text="Color Tag", font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(anchor="w")
        color_var = tk.StringVar(value=ACCOUNT_COLORS[0])
        color_row = ctk.CTkFrame(b, fg_color="transparent")
        color_row.pack(fill="x", pady=(2, 8))
        for c in ACCOUNT_COLORS:
            btn = ctk.CTkButton(color_row, text="", width=24, height=24, corner_radius=12,
                                fg_color=c, hover_color=c,
                                command=lambda col=c: color_var.set(col))
            btn.pack(side="left", padx=2)

        type_c.set(acc_types[0])
        cur_c.set("USD")

        def save():
            name = name_e.get().strip()
            if not name:
                messagebox.showerror("Error", "Account name is required.", parent=modal)
                return
            cur_c.resolve()
            try:
                atype = next(t for t in AccountType if t.value == type_c.get())
                kwargs = {}
                if atype == AccountType.CREDIT_CARD:
                    kwargs["credit_limit"] = self._parse_float(limit_entry.get())
                    kwargs["statement_day"] = self._parse_int(stmt_entry.get())
                    kwargs["payment_due_day"] = self._parse_int(due_entry.get())
                    kwargs["interest_rate"] = self._parse_float(apr_entry.get())
                self.ctx.account.create(
                    name=name, account_type=atype,
                    currency_code=cur_c.get(),
                    institution=inst_e.get().strip(),
                    account_number=acno_e.get().strip(),
                    description=desc_t.get("1.0", "end").strip(),
                    color=color_var.get(),
                    **kwargs
                )
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Create Account", save)

    def _toggle_cc_fields(self, cc_frame, value):
        if value == AccountType.CREDIT_CARD.value:
            cc_frame.pack(fill="x", pady=(0, 8))
        else:
            cc_frame.pack_forget()

    # ── Edit account ────────────────────────────────────────────────────────

    def _edit_account(self, acc):
        modal = Modal(self, f"Edit — {acc.name}", width=480, height=780)
        b = modal.body

        acc_types  = [t.value for t in AccountType]

        name_e = modal.add_field("Account Name", lambda p: make_entry(p))
        name_e.insert(0, acc.name)

        type_c = modal.add_field("Account Type", lambda p: make_combo(p, acc_types, command=lambda v: self._toggle_cc_fields(cc_frame, v)))
        type_c.set(acc.account_type.value)

        inst_e = modal.add_field("Institution", lambda p: make_entry(p))
        inst_e.insert(0, acc.institution or "")

        acno_e = modal.add_field("Account Number", lambda p: make_entry(p))
        acno_e.insert(0, acc.account_number or "")

        cur_c = modal.add_field("Currency", lambda p: CurrencySearchEntry(p, self.ctx, initial_code=acc.currency.code))
        attach_currency_tooltip(cur_c, self.ctx)

        desc_t = modal.add_field("Description", lambda p: make_textbox(p, height=60))
        desc_t.insert("1.0", acc.description or "")

        # Credit-card-only fields
        cc_frame = ctk.CTkFrame(b, fg_color="transparent")
        cc_frame.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(cc_frame, text="💳 Credit Card Details", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(4, 4))
        limit_entry = make_entry(cc_frame, "Credit limit")
        limit_entry.pack(fill="x", pady=(0, 6))
        if acc.credit_limit:
            limit_entry.insert(0, str(acc.credit_limit))
        row2 = ctk.CTkFrame(cc_frame, fg_color="transparent")
        row2.pack(fill="x")
        stmt_entry = make_entry(row2, "Statement day (1-31)")
        stmt_entry.pack(side="left", fill="x", expand=True, padx=(0, 4))
        if acc.statement_day:
            stmt_entry.insert(0, str(acc.statement_day))
        due_entry = make_entry(row2, "Payment due day (1-31)")
        due_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        if acc.payment_due_day:
            due_entry.insert(0, str(acc.payment_due_day))
        apr_entry = make_entry(cc_frame, "APR / interest rate %")
        apr_entry.pack(fill="x", pady=(6, 0))
        if acc.interest_rate:
            apr_entry.insert(0, str(acc.interest_rate))
        if acc.account_type != AccountType.CREDIT_CARD:
            cc_frame.pack_forget()

        # Color picker
        ctk.CTkLabel(b, text="Color Tag", font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(anchor="w")
        color_var = tk.StringVar(value=acc.color)
        color_row = ctk.CTkFrame(b, fg_color="transparent")
        color_row.pack(fill="x", pady=(2, 8))
        for c in ACCOUNT_COLORS:
            btn = ctk.CTkButton(color_row, text="", width=24, height=24, corner_radius=12,
                                fg_color=c, hover_color=c,
                                border_width=(2 if c == acc.color else 0), border_color=theme.TEXT_PRI,
                                command=lambda col=c: color_var.set(col))
            btn.pack(side="left", padx=2)

        # Manual balance override
        bal_e = modal.add_field("Manual Balance Override (optional)",
                                lambda p: make_entry(p, "Leave blank to compute from transactions"))
        if acc.balance_override is not None:
            bal_e.insert(0, str(acc.balance_override))

        # ── Attachments (statements, agreements, ID/proof documents, etc.) ──
        ctk.CTkLabel(b, text="📎 Attachments", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(8, 4))
        attachments_frame = ctk.CTkFrame(b, fg_color="transparent")
        attachments_frame.pack(fill="x", pady=(0, 4))

        def refresh_attachments():
            for w in attachments_frame.winfo_children():
                w.destroy()
            if not acc.attachments:
                ctk.CTkLabel(attachments_frame, text="No files attached yet.",
                             font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w", pady=2)
            for att in acc.attachments:
                row_f = ctk.CTkFrame(attachments_frame, fg_color=theme.ROW_ALT, corner_radius=6)
                row_f.pack(fill="x", pady=2)
                ctk.CTkLabel(row_f, text=f"📎 {att.original_filename}",
                             font=("Segoe UI", 11), text_color=theme.ACCENT).pack(side="left", padx=8, pady=4)
                ctk.CTkButton(row_f, text="Open", width=60, height=24,
                              fg_color="transparent", text_color=theme.ACCENT, font=("Segoe UI", 11),
                              command=lambda a=att: self.ctx.attachment.open_file(a)
                              ).pack(side="right", padx=4, pady=2)
                ctk.CTkButton(row_f, text="✕", width=28, height=24,
                              fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                              command=lambda a=att: delete_attachment(a)
                              ).pack(side="right", pady=2)

        def attach_file():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Attach proof file (statement, agreement, ID — any file type)",
                filetypes=[("All files", "*.*"),
                           ("Documents & images", "*.pdf *.png *.jpg *.jpeg *.doc *.docx *.xls *.xlsx *.csv *.txt")]
            )
            if not path:
                return
            try:
                self.ctx.attachment.save_file(path, self.ctx.session, "account", acc.id)
                self.ctx.session.refresh(acc)
                refresh_attachments()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete_attachment(att):
            if messagebox.askyesno("Delete Attachment", f"Remove '{att.original_filename}'?", parent=modal):
                self.ctx.attachment.delete_file(att, self.ctx.session)
                self.ctx.session.refresh(acc)
                refresh_attachments()

        refresh_attachments()
        ctk.CTkButton(b, text="＋ Attach File", height=30, font=("Segoe UI", 11),
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, command=attach_file).pack(anchor="w", pady=(2, 8))

        def save():
            name = name_e.get().strip()
            if not name:
                messagebox.showerror("Error", "Account name is required.", parent=modal)
                return
            cur_c.resolve()
            try:
                atype = next(t for t in AccountType if t.value == type_c.get())
                kwargs = dict(
                    name=name, account_type=atype,
                    currency_code=cur_c.get(),
                    institution=inst_e.get().strip(),
                    account_number=acno_e.get().strip(),
                    description=desc_t.get("1.0", "end").strip(),
                    color=color_var.get(),
                    balance_override=self._parse_float(bal_e.get()),
                )
                if atype == AccountType.CREDIT_CARD:
                    kwargs["credit_limit"] = self._parse_float(limit_entry.get())
                    kwargs["statement_day"] = self._parse_int(stmt_entry.get())
                    kwargs["payment_due_day"] = self._parse_int(due_entry.get())
                    kwargs["interest_rate"] = self._parse_float(apr_entry.get())
                self.ctx.account.update(acc, **kwargs)
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete():
            if messagebox.askyesno("Delete Account",
                                   f"Delete '{acc.name}' and ALL its transactions/assets? "
                                   "This cannot be undone.", parent=modal):
                try:
                    self.ctx.account.delete(acc)
                    modal.destroy()
                    self.app.refresh()
                    self._rebuild()
                except Exception as e:
                    messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Save Changes", save,
                         extra=[("Delete Account", delete, theme.RED)])

    # ── Navigation ──────────────────────────────────────────────────────────

    def _view_transactions(self, acc):
        self.app.navigate("transactions", initial_account=acc.name)

    @staticmethod
    def _parse_float(text):
        text = (text or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    @staticmethod
    def _parse_int(text):
        text = (text or "").strip()
        if not text:
            return None
        try:
            return int(float(text))
        except ValueError:
            return None

    def _rebuild(self):
        safe_rebuild(self, self._build)
