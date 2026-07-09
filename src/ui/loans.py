"""
WealthMap – Loans Panel
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime, timezone

from src.ui.widgets import (safe_rebuild, 
    SectionHeader, StatCard, DataTable, Modal,
    make_entry, make_combo, make_textbox, fmt_money, fmt_money_base,
    attach_currency_tooltip
)
from src.ui.theme import theme


class LoansPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._show_settled = False

        if ctx.is_business:
            self.L = dict(
                title="Receivables & Payables",
                subtitle="Money clients owe you (Accounts Receivable) and money you owe "
                         "vendors (Accounts Payable)",
                owed_to_me="Receivable (AR)", i_owe="Payable (AP)",
                dir_to_me="→ Client owes (AR)", dir_i_owe="← Vendor owed (AP)",
                dir_options=["Client owes me (AR)", "I owe a vendor (AP)"],
                new_btn="＋ New Receivable / Payable",
                name_label="Client / Vendor Name", name_placeholder="Client or vendor name",
                modal_title="Receivable / Payable",
            )
        else:
            self.L = dict(
                title="Loans & Personal Debts",
                subtitle="Money you lent or borrowed from people",
                owed_to_me="Owed to Me", i_owe="I Owe",
                dir_to_me="→ They owe me", dir_i_owe="← I owe them",
                dir_options=["They owe me", "I owe them"],
                new_btn="＋ New Loan",
                name_label="Contact Name", name_placeholder="Person's name",
                modal_title="Loan / Debt",
            )
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        SectionHeader(scroll, self.L["title"],
                      self.L["subtitle"],
                      self.L["new_btn"], self._open_new_loan
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 20))

        summary = self.ctx.loan.summary(base)

        cards_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        for i in range(3):
            cards_frame.grid_columnconfigure(i, weight=1)

        net_col = theme.GREEN if summary["net"] >= 0 else theme.RED
        StatCard(cards_frame, self.L["owed_to_me"], fmt_money(summary["owed_to_me"], sym), "", theme.GREEN, "💚"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(cards_frame, self.L["i_owe"],      fmt_money(summary["i_owe"],      sym), "", theme.RED,   "❤"
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        StatCard(cards_frame, "Net Position",fmt_money(summary["net"],        sym), "", net_col, "⚖"
                 ).grid(row=0, column=2, sticky="ew")

        # Toggle settled
        toggle_row = ctk.CTkFrame(scroll, fg_color="transparent")
        toggle_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self._settled_switch = ctk.CTkSwitch(
            toggle_row, text="Show settled loans", font=("Segoe UI", 12),
            text_color=theme.TEXT_SEC, progress_color=theme.ACCENT,
            command=self._toggle_settled)
        self._settled_switch.pack(side="left")
        if self._show_settled:
            self._settled_switch.select()

        # Active (and optionally settled) loans
        loans = self.ctx.loan.get_all(include_settled=self._show_settled)
        for loan in loans:
            card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
            card.grid(row=scroll.grid_size()[1], column=0, sticky="ew", pady=(0, 10))

            hdr = ctk.CTkFrame(card, fg_color=theme.BG_HOVER, corner_radius=0)
            hdr.pack(fill="x")
            direction_text = self.L["dir_to_me"] if loan.direction == "owed_to_me" else self.L["dir_i_owe"]
            direction_color= theme.GREEN if loan.direction == "owed_to_me" else theme.RED
            if loan.is_settled:
                direction_text += "  (Settled)"
                direction_color = theme.TEXT_SEC
            ctk.CTkLabel(hdr, text=direction_text, font=("Segoe UI", 11, "bold"),
                         text_color=direction_color).pack(side="left", padx=12, pady=8)
            cur = loan.currency
            sym2 = cur.symbol if cur else ""
            ctk.CTkLabel(hdr, text=f"{cur.code if cur else ''}", font=("Segoe UI", 10),
                         text_color=theme.TEXT_SEC).pack(side="right", padx=12)

            body = ctk.CTkFrame(card, fg_color="transparent")
            body.pack(fill="x", padx=16, pady=12)
            left = ctk.CTkFrame(body, fg_color="transparent")
            left.pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(left, text=loan.contact_name,
                         font=("Segoe UI", 15, "bold"), text_color=theme.TEXT_PRI).pack(anchor="w")
            ctk.CTkLabel(left, text=loan.description or "No description",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w")
            if loan.contact_info:
                ctk.CTkLabel(left, text=loan.contact_info,
                             font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="w")
            if loan.fee_amount:
                fcur = loan.fee_currency or cur
                fsym = fcur.symbol if fcur else ""
                ctk.CTkLabel(left, text=f"Fee: {fmt_money(loan.fee_amount, fsym)}"
                                         f"{' — ' + loan.fee_description if loan.fee_description else ''}",
                             font=("Segoe UI", 10), text_color=theme.GOLD).pack(anchor="w")

            right = ctk.CTkFrame(body, fg_color="transparent")
            right.pack(side="right")
            pct = min(100, (loan.amount_repaid / loan.principal * 100)) if loan.principal else 0
            ctk.CTkLabel(right, text=fmt_money_base(self.ctx, loan.outstanding, cur.code if cur else ""),
                         font=("Segoe UI", 20, "bold"), text_color=direction_color).pack(anchor="e")
            ctk.CTkLabel(right, text=f"of {fmt_money(loan.principal, sym2)} • {pct:.0f}% repaid",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="e")

            prog = ctk.CTkProgressBar(body, height=6, fg_color=theme.BORDER, progress_color=direction_color)
            prog.set(pct / 100)
            prog.pack(fill="x", pady=(8, 4))

            btn_row = ctk.CTkFrame(card, fg_color="transparent")
            btn_row.pack(fill="x", padx=16, pady=(0, 12))
            if not loan.is_settled:
                ctk.CTkButton(btn_row, text="Record Repayment", width=150, height=28,
                              fg_color="transparent", border_color=theme.BORDER, border_width=1,
                              text_color=theme.ACCENT, font=("Segoe UI", 11),
                              command=lambda l=loan: self._record_repayment(l)).pack(side="left")
            ctk.CTkButton(btn_row, text="Attach Proof", width=110, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                          command=lambda l=loan: self._attach_to_loan(l)).pack(side="left", padx=6)
            ctk.CTkButton(btn_row, text="✎ Edit", width=70, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                          command=lambda l=loan: self._edit_loan(l)).pack(side="left", padx=6)
            ctk.CTkLabel(btn_row, text=f"Created {loan.created_at.strftime('%d %b %Y')}",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(side="right")

        if not loans:
            empty_msg = ("No outstanding receivables or payables — all clear! 🎉"
                         if self.ctx.is_business else "No active loans — all clear! 🎉")
            ctk.CTkLabel(scroll, text=empty_msg,
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 13)).grid(
                row=scroll.grid_size()[1], column=0, pady=40)

    def _toggle_settled(self):
        self._show_settled = not self._show_settled
        self._rebuild()

    # ── New loan ──────────────────────────────────────────────────────────────

    def _open_new_loan(self):
        modal = Modal(self, f"New {self.L['modal_title']}", width=480, height=620)
        currencies = [c.code for c in self.ctx.currency.get_all()]

        name_e    = modal.add_field(self.L["name_label"],   lambda p: make_entry(p, self.L["name_placeholder"]))
        contact_e = modal.add_field("Contact Info",   lambda p: make_entry(p, "Email / phone (optional)"))
        dir_c     = modal.add_field("Direction",      lambda p: make_combo(p, self.L["dir_options"]))
        amt_e     = modal.add_field("Amount",         lambda p: make_entry(p, "0.00"))
        cur_c     = modal.add_field("Currency",       lambda p: make_combo(p, currencies))
        attach_currency_tooltip(cur_c, self.ctx)
        desc_t    = modal.add_field("Description",    lambda p: make_textbox(p, height=60))

        ctk.CTkLabel(modal.body, text="💰 Fee (optional — e.g. transfer/processing fee)",
                     font=("Segoe UI", 12, "bold"), text_color=theme.ACCENT).pack(anchor="w", pady=(8, 4))
        fee_row = ctk.CTkFrame(modal.body, fg_color="transparent")
        fee_row.pack(fill="x", pady=(0, 4))
        fee_amt_e = make_entry(fee_row, "Fee amount")
        fee_amt_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
        fee_cur_c = make_combo(fee_row, currencies, width=90)
        fee_cur_c.pack(side="left")
        attach_currency_tooltip(fee_cur_c, self.ctx)
        fee_desc_e = make_entry(modal.body, "Fee description")
        fee_desc_e.pack(fill="x", pady=(2, 8))

        dir_c.set(self.L["dir_options"][0])
        cur_c.set("USD")
        fee_cur_c.set("USD")

        def save():
            try:
                direction = "owed_to_me" if dir_c.get() == self.L["dir_options"][0] else "i_owe"
                amount = float(amt_e.get().replace(",", ""))
                fee_amount = self._parse_float(fee_amt_e.get()) or 0.0
                self.ctx.loan.create(
                    contact_name=name_e.get().strip(),
                    direction=direction, principal=amount,
                    currency_code=cur_c.get(),
                    description=desc_t.get("1.0", "end").strip(),
                    contact_info=contact_e.get().strip(),
                    fee_amount=fee_amount,
                    fee_currency_code=fee_cur_c.get() if fee_amount else None,
                    fee_description=fee_desc_e.get().strip(),
                )
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Create", save)

    # ── Edit / Delete loan ───────────────────────────────────────────────────

    def _edit_loan(self, loan):
        modal = Modal(self, f"Edit {self.L['modal_title']} — {loan.contact_name}", width=480, height=660)
        currencies = [c.code for c in self.ctx.currency.get_all()]

        name_e = modal.add_field(self.L["name_label"], lambda p: make_entry(p))
        name_e.insert(0, loan.contact_name)

        contact_e = modal.add_field("Contact Info", lambda p: make_entry(p))
        contact_e.insert(0, loan.contact_info or "")

        dir_c = modal.add_field("Direction", lambda p: make_combo(p, self.L["dir_options"]))
        dir_c.set(self.L["dir_options"][0] if loan.direction == "owed_to_me" else self.L["dir_options"][1])

        amt_e = modal.add_field("Principal Amount", lambda p: make_entry(p))
        amt_e.insert(0, f"{loan.principal:g}")

        cur_c = modal.add_field("Currency", lambda p: make_combo(p, currencies))
        cur_c.set(loan.currency.code)
        attach_currency_tooltip(cur_c, self.ctx)

        desc_t = modal.add_field("Description", lambda p: make_textbox(p, height=60))
        desc_t.insert("1.0", loan.description or "")

        ctk.CTkLabel(modal.body, text="💰 Fee (optional)", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(8, 4))
        fee_row = ctk.CTkFrame(modal.body, fg_color="transparent")
        fee_row.pack(fill="x", pady=(0, 4))
        fee_amt_e = make_entry(fee_row, "Fee amount")
        fee_amt_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
        if loan.fee_amount:
            fee_amt_e.insert(0, f"{loan.fee_amount:g}")
        fee_cur_c = make_combo(fee_row, currencies, width=90)
        fee_cur_c.pack(side="left")
        fee_cur_c.set((loan.fee_currency or loan.currency).code)
        attach_currency_tooltip(fee_cur_c, self.ctx)
        fee_desc_e = make_entry(modal.body, "Fee description")
        fee_desc_e.pack(fill="x", pady=(2, 8))
        fee_desc_e.insert(0, loan.fee_description or "")

        settled_var = ctk.BooleanVar(value=loan.is_settled)
        ctk.CTkCheckBox(modal.body, text="Mark as settled", variable=settled_var,
                        font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                        fg_color=theme.ACCENT).pack(anchor="w", pady=(4, 0))

        def save():
            try:
                amount = float(amt_e.get().replace(",", ""))
                fee_amount = self._parse_float(fee_amt_e.get()) or 0.0
                direction = "owed_to_me" if dir_c.get() == self.L["dir_options"][0] else "i_owe"
                fields = dict(
                    contact_name=name_e.get().strip(),
                    contact_info=contact_e.get().strip(),
                    direction=direction,
                    principal=amount,
                    currency_code=cur_c.get(),
                    description=desc_t.get("1.0", "end").strip(),
                    fee_amount=fee_amount,
                    fee_currency_code=fee_cur_c.get() if fee_amount else None,
                    fee_description=fee_desc_e.get().strip(),
                    is_settled=settled_var.get(),
                )
                if settled_var.get() and not loan.is_settled:
                    fields["settled_at"] = datetime.now(timezone.utc)
                elif not settled_var.get():
                    fields["settled_at"] = None
                self.ctx.loan.update(loan, **fields)
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete():
            if messagebox.askyesno("Delete Loan",
                                   f"Delete the loan with '{loan.contact_name}' and all its "
                                   "repayment history? This cannot be undone.", parent=modal):
                self.ctx.loan.delete(loan)
                modal.destroy()
                self.app.refresh()
                self._rebuild()

        modal.add_buttons("Save Changes", save,
                         extra=[("Delete Loan", delete, theme.RED)])

    def _record_repayment(self, loan):
        modal = Modal(self, "Record Repayment", width=400, height=400)
        cur = loan.currency
        sym = cur.symbol if cur else ""
        ctk.CTkLabel(modal.body,
                     text=f"Outstanding: {fmt_money(loan.outstanding, sym)} {cur.code if cur else ''}",
                     font=("Segoe UI", 13), text_color=theme.GOLD).pack(pady=(0, 12))
        amt_e   = modal.add_field("Amount Repaid", lambda p: make_entry(p, "0.00"))
        fee_e   = modal.add_field("Fee on this repayment (optional)", lambda p: make_entry(p, "0.00"))
        notes_e = modal.add_field("Notes",         lambda p: make_entry(p, "Optional"))

        def save():
            try:
                amount = float(amt_e.get().replace(",", ""))
                fee = self._parse_float(fee_e.get()) or 0.0
                self.ctx.loan.record_repayment(loan, amount, notes=notes_e.get().strip(),
                                               fee_amount=fee)
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Record", save)

    def _attach_to_loan(self, loan):
        path = filedialog.askopenfilename(title="Attach proof",
            filetypes=[("All files", "*.*"),
                       ("Documents & images", "*.pdf *.png *.jpg *.jpeg *.doc *.docx *.txt")])
        if path:
            try:
                self.ctx.attachment.save_file(path, self.ctx.session, "loan", loan.id)
                messagebox.showinfo("Attached", "File attached successfully.")
            except Exception as e:
                messagebox.showerror("Error", str(e))

    @staticmethod
    def _parse_float(text):
        text = (text or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _rebuild(self):
        safe_rebuild(self, self._build)
