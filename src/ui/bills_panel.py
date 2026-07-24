"""
WealthMap – Bills Panel

Recurring/one-time bill tracker: rent, electricity, subscriptions, etc.
Each bill shows what's due, when, and how often; overdue and due-soon
bills are highlighted. "Mark as Paid" creates a normal expense
transaction on the chosen account (tagged with the bill, so every bill
keeps its full payment history) and advances the schedule automatically.
"""

from datetime import datetime, timezone
from tkinter import messagebox
import customtkinter as ctk

from src.models.database import TransactionType
from src.ui.widgets import (safe_rebuild,
    SectionHeader, StatCard, Modal,
    make_entry, make_combo, make_textbox, fmt_money, fmt_money_base,
    attach_currency_tooltip, CurrencySearchEntry, AttachmentSection
)
from src.ui.theme import theme
from src.ui.bill_import_dialog import open_bill_import_dialog

FREQ_LABELS = {
    "weekly":    "Weekly",
    "monthly":   "Monthly",
    "quarterly": "Quarterly",
    "yearly":    "Yearly",
    "one_time":  "One-time",
}
FREQ_BY_LABEL = {v: k for k, v in FREQ_LABELS.items()}


class BillsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._show_inactive = False
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""
        self._base = base

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        SectionHeader(scroll, "Bills",
                      "Rent, utilities, subscriptions — what's due, when, and what you've paid",
                      "＋ New Bill", self._open_new_bill,
                      extra_buttons=[("📥 Import Bill", self._import_bill)]
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 16))

        bills = self.ctx.bill.get_all(include_inactive=self._show_inactive)
        now = datetime.now()

        def to_base(b):
            code = b.currency.code if b.currency else base
            return self.ctx.currency.convert(b.amount, code, base) or b.amount

        active = [b for b in bills if b.is_active]
        overdue = [b for b in active if b.next_due and b.next_due < now]
        due_month = [b for b in active if b.next_due and
                     b.next_due.year == now.year and b.next_due.month == now.month]

        cards = ctk.CTkFrame(scroll, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        for i in range(3):
            cards.grid_columnconfigure(i, weight=1)
        StatCard(cards, "Active Bills", str(len(active)), "", theme.ACCENT, "💡"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(cards, "Due This Month",
                 fmt_money(sum(to_base(b) for b in due_month), sym),
                 f"{len(due_month)} bill(s)", theme.GOLD, "📅"
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        StatCard(cards, "Overdue",
                 fmt_money(sum(to_base(b) for b in overdue), sym),
                 f"{len(overdue)} bill(s)", theme.RED if overdue else theme.GREEN, "⚠"
                 ).grid(row=0, column=2, sticky="ew")

        toggle_row = ctk.CTkFrame(scroll, fg_color="transparent")
        toggle_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self._inactive_switch = ctk.CTkSwitch(
            toggle_row, text="Show inactive bills", font=("Segoe UI", 12),
            text_color=theme.TEXT_SEC, progress_color=theme.ACCENT,
            command=self._toggle_inactive)
        self._inactive_switch.pack(side="left")
        if self._show_inactive:
            self._inactive_switch.select()

        # ── Group bills by due month/year, earliest first ─────────────────
        scheduled = [b for b in bills if b.is_active and b.next_due]
        no_due = [b for b in bills if b.is_active and not b.next_due]
        inactive = [b for b in bills if not b.is_active]

        groups = {}
        for b in scheduled:
            key = (b.next_due.year, b.next_due.month)
            groups.setdefault(key, []).append(b)
        for key in groups:
            groups[key].sort(key=lambda b: b.next_due)

        for (year, month) in sorted(groups.keys()):
            month_bills = groups[(year, month)]
            self._render_month_band(scroll, year, month, month_bills, to_base, sym, now)
            for b in month_bills:
                self._render_bill_card(scroll, b, now)

        if no_due:
            self._render_group_band(scroll, "📌 No Due Date Set", no_due, to_base, sym)
            for b in no_due:
                self._render_bill_card(scroll, b, now)

        if self._show_inactive and inactive:
            self._render_group_band(scroll, "⏸ Inactive", inactive, to_base, sym)
            for b in inactive:
                self._render_bill_card(scroll, b, now)

        if not bills:
            ctk.CTkLabel(scroll, text="No bills yet — add rent, utilities, or subscriptions "
                                      "to keep track of what's due.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 13)).grid(
                row=scroll.grid_size()[1], column=0, pady=40)

    def _render_month_band(self, scroll, year, month, month_bills, to_base, sym, now):
        import calendar
        label = f"📆 {calendar.month_name[month]} {year}"
        is_past = (year, month) < (now.year, now.month)
        total = sum(to_base(b) for b in month_bills)
        subtitle = (f"{len(month_bills)} bill(s)  •  {sym}{total:,.2f} due" +
                   ("  •  in the past" if is_past else ""))
        self._render_band(scroll, label, subtitle,
                          theme.RED if is_past else theme.TEXT_PRI)

    def _render_group_band(self, scroll, label, group_bills, to_base, sym):
        total = sum(to_base(b) for b in group_bills)
        subtitle = f"{len(group_bills)} bill(s)  •  {sym}{total:,.2f}"
        self._render_band(scroll, label, subtitle, theme.TEXT_PRI)

    def _render_band(self, scroll, label, subtitle, title_color):
        band = ctk.CTkFrame(scroll, fg_color=theme.BG_HOVER, corner_radius=10)
        band.grid(row=scroll.grid_size()[1], column=0, sticky="ew", pady=(14, 8))
        left = ctk.CTkFrame(band, fg_color="transparent")
        left.pack(side="left", padx=14, pady=10, fill="x")
        ctk.CTkLabel(left, text=label, font=("Segoe UI", 16, "bold"),
                     text_color=title_color).pack(anchor="w")
        ctk.CTkLabel(left, text=subtitle, font=("Segoe UI", 11),
                     text_color=theme.TEXT_SEC).pack(anchor="w")

    def _render_bill_card(self, scroll, bill, now):
        cur = bill.currency

        overdue = bill.is_active and bill.next_due and bill.next_due < now
        due_soon = (bill.is_active and bill.next_due and not overdue and
                    (bill.next_due - now).days <= 7)
        if not bill.is_active:
            status_txt, status_col = "Inactive", theme.TEXT_SEC
        elif overdue:
            days = (now - bill.next_due).days
            status_txt, status_col = f"⚠ Overdue by {days} day(s)", theme.RED
        elif due_soon:
            days = (bill.next_due - now).days
            status_txt = "📅 Due today" if days == 0 else f"📅 Due in {days} day(s)"
            status_col = theme.GOLD
        elif bill.next_due:
            status_txt, status_col = f"Next due {bill.next_due.strftime('%d %b %Y')}", theme.TEXT_SEC
        else:
            status_txt, status_col = "No due date set", theme.TEXT_SEC

        card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1,
                            border_color=theme.RED if overdue else theme.BORDER)
        card.grid(row=scroll.grid_size()[1], column=0, sticky="ew", pady=(0, 10))

        hdr = ctk.CTkFrame(card, fg_color=theme.BG_HOVER, corner_radius=0)
        hdr.pack(fill="x")
        ctk.CTkLabel(hdr, text=status_txt, font=("Segoe UI", 11, "bold"),
                     text_color=status_col).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(hdr, text=FREQ_LABELS.get(bill.frequency, bill.frequency),
                     font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(side="right", padx=12)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=12)
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text=bill.name,
                     font=("Segoe UI", 15, "bold"), text_color=theme.TEXT_PRI).pack(anchor="w")
        sub = "  •  ".join(x for x in (bill.payee, bill.category) if x)
        if sub:
            ctk.CTkLabel(left, text=sub, font=("Segoe UI", 11),
                         text_color=theme.TEXT_SEC).pack(anchor="w")
        detail_bits = []
        if bill.account_number:
            detail_bits.append(f"Acct # {bill.account_number}")
        if bill.meter_number:
            detail_bits.append(f"Meter {bill.meter_number}")
        if bill.consumption:
            detail_bits.append(f"{bill.consumption:g} {bill.consumption_unit}".strip())
        if detail_bits:
            ctk.CTkLabel(left, text="  •  ".join(detail_bits), font=("Segoe UI", 10),
                         text_color=theme.TEXT_SEC).pack(anchor="w")
        if bill.last_paid_on:
            ctk.CTkLabel(left, text=f"Last paid {bill.last_paid_on.strftime('%d %b %Y')}"
                                    f"  ({len(bill.transactions)} payment(s) recorded)",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="w")

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkLabel(right, text=fmt_money_base(self.ctx, bill.amount, cur.code if cur else ""),
                     font=("Segoe UI", 20, "bold"),
                     text_color=theme.RED if overdue else theme.TEXT_PRI).pack(anchor="e")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        if bill.is_active:
            ctk.CTkButton(btn_row, text="✓ Mark as Paid", width=130, height=28,
                          fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
                          text_color="#fff", font=("Segoe UI", 11, "bold"),
                          command=lambda b=bill: self._mark_paid(b)).pack(side="left")
        if bill.transactions:
            ctk.CTkButton(btn_row, text="🧾 Payment History", width=140, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                          command=lambda b=bill: self._show_history(b)).pack(side="left", padx=6)
        ctk.CTkButton(btn_row, text="✎ Edit", width=70, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=lambda b=bill: self._edit_bill(b)).pack(side="left", padx=6)

    def _import_bill(self):
        open_bill_import_dialog(self, self.ctx, on_done=lambda: (self.app.refresh(), self._rebuild()))

    def _toggle_inactive(self):
        self._show_inactive = not self._show_inactive
        self._rebuild()

    # ── New / Edit ────────────────────────────────────────────────────────

    def _bill_form(self, modal, bill=None):
        accounts = self.ctx.account.get_all()
        acc_names = ["(choose at payment time)"] + [a.name for a in accounts]

        name_e = modal.add_field("Bill Name", lambda p: make_entry(p, "e.g. Electricity, Rent, Netflix"))
        payee_e = modal.add_field("Payee / Company", lambda p: make_entry(p, "Who gets paid (optional)"))
        amt_e = modal.add_field("Amount", lambda p: make_entry(p, "0.00"))
        cur_c = modal.add_field("Currency", lambda p: CurrencySearchEntry(
            p, self.ctx, width=120,
            initial_code=(bill.currency.code if bill and bill.currency
                          else self.ctx.settings.get("base_currency", "USD"))))
        attach_currency_tooltip(cur_c, self.ctx)
        freq_c = modal.add_field("Frequency", lambda p: make_combo(p, list(FREQ_LABELS.values())))
        due_e = modal.add_field("Next Due Date (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
        acc_c = modal.add_field("Default Pay-From Account", lambda p: make_combo(p, acc_names))
        cat_e = modal.add_field("Category", lambda p: make_entry(p, "Bills & Utilities"))
        notes_t = modal.add_field("Notes", lambda p: make_textbox(p, height=50))

        if bill:
            name_e.insert(0, bill.name)
            payee_e.insert(0, bill.payee or "")
            amt_e.insert(0, f"{bill.amount:g}")
            freq_c.set(FREQ_LABELS.get(bill.frequency, "Monthly"))
            if bill.next_due:
                due_e.insert(0, bill.next_due.strftime("%Y-%m-%d"))
            acc_c.set(bill.account.name if bill.account else acc_names[0])
            cat_e.insert(0, bill.category or "")
            notes_t.insert("1.0", bill.notes or "")
        else:
            freq_c.set("Monthly")
            acc_c.set(acc_names[0])
            cat_e.insert(0, "Bills & Utilities")

        def read():
            cur_c.resolve()
            name = name_e.get().strip()
            if not name:
                raise ValueError("Give the bill a name.")
            try:
                amount = float(amt_e.get().replace(",", ""))
            except ValueError:
                raise ValueError("Amount must be a number.") from None
            due_txt = due_e.get().strip()
            next_due = None
            if due_txt:
                try:
                    next_due = datetime.strptime(due_txt, "%Y-%m-%d")
                except ValueError:
                    raise ValueError("Due date must be YYYY-MM-DD.") from None
            account = next((a for a in accounts if a.name == acc_c.get()), None)
            return dict(
                name=name, payee=payee_e.get().strip(), amount=amount,
                currency_code=cur_c.get(),
                frequency=FREQ_BY_LABEL.get(freq_c.get(), "monthly"),
                next_due=next_due, account=account,
                category=cat_e.get().strip() or "Bills & Utilities",
                notes=notes_t.get("1.0", "end").strip(),
            )

        return read

    def _open_new_bill(self):
        modal = Modal(self, "New Bill", width=480, height=700)
        read = self._bill_form(modal)

        def save():
            try:
                self.ctx.bill.create(**read())
                modal.destroy()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Create", save)

    def _edit_bill(self, bill):
        modal = Modal(self, f"Edit Bill — {bill.name}", width=480, height=740)
        read = self._bill_form(modal, bill)

        active_var = ctk.BooleanVar(value=bill.is_active)
        ctk.CTkCheckBox(modal.body, text="Active (shows in upcoming bills)",
                        variable=active_var, font=("Segoe UI", 12),
                        text_color=theme.TEXT_SEC, fg_color=theme.ACCENT
                        ).pack(anchor="w", pady=(4, 0))

        def save():
            try:
                fields = read()
                account = fields.pop("account")
                fields["account_id"] = account.id if account else None
                fields["is_active"] = active_var.get()
                self.ctx.bill.update(bill, **fields)
                modal.destroy()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete():
            if messagebox.askyesno(
                    "Delete Bill",
                    f"Delete '{bill.name}'? Past payment transactions stay in "
                    "your ledger — only the bill and its schedule are removed.",
                    parent=modal):
                self.ctx.bill.delete(bill)
                modal.destroy()
                self._rebuild()

        modal.add_buttons("Save Changes", save, extra=[("Delete Bill", delete, theme.RED)])

    # ── Payment ───────────────────────────────────────────────────────────

    def _mark_paid(self, bill):
        accounts = self.ctx.account.get_all()
        if not accounts:
            messagebox.showerror("No Accounts", "Create an account first.", parent=self)
            return
        acc_names = [a.name for a in accounts]

        modal = Modal(self, f"Pay Bill — {bill.name}", width=440, height=620)
        cur = bill.currency
        code = cur.code if cur else self.ctx.settings.get("base_currency", "USD")

        acc_c = modal.add_field("Pay From Account", lambda p: make_combo(p, acc_names))
        acc_c.set(bill.account.name if bill.account and bill.account.name in acc_names
                  else acc_names[0])
        amt_e = modal.add_field(f"Amount ({code})", lambda p: make_entry(p, "0.00"))
        amt_e.insert(0, f"{bill.amount:g}")
        date_e = modal.add_field("Payment Date (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
        date_e.insert(0, datetime.now().strftime("%Y-%m-%d"))
        notes_e = modal.add_field("Notes", lambda p: make_entry(p, "Optional"))

        # Proof of payment — one or more receipts/screenshots can be
        # attached here; staged until the payment transaction exists, then
        # uploaded and linked to it (so "Payment History" can show them).
        receipts = AttachmentSection(modal.body, self.ctx, "transaction", entity=None,
                                     title="🧾 Proof of Payment (receipts)")
        receipts.pack(fill="x")

        def save():
            try:
                account = next((a for a in accounts if a.name == acc_c.get()), None)
                amount = float(amt_e.get().replace(",", ""))
                paid_on = datetime.strptime(date_e.get().strip(), "%Y-%m-%d")
                tx = self.ctx.transaction.add(
                    account, TransactionType.EXPENSE, amount,
                    description=f"Bill — {bill.name}",
                    category=bill.category or "Bills & Utilities",
                    payee=bill.payee or bill.name,
                    transaction_date=paid_on,
                    currency_code=code,
                    notes=notes_e.get().strip(),
                    bill_id=bill.id,
                )
                receipts.commit(tx.id)
                self.ctx.bill.record_payment(bill, paid_on=paid_on.replace(tzinfo=timezone.utc))
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Record Payment", save)

    def _show_history(self, bill):
        modal = Modal(self, f"Payment History — {bill.name}", width=520, height=520)
        txs = sorted(bill.transactions, key=lambda t: t.transaction_date, reverse=True)
        if not txs:
            ctk.CTkLabel(modal.body, text="No payments recorded yet.",
                         font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(pady=20)
        for tx in txs:
            cur = tx.currency
            sym = cur.symbol if cur else ""
            row = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=tx.transaction_date.strftime("%d %b %Y"),
                         font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
                         width=100, anchor="w").pack(side="left", padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=tx.account.name if tx.account else "—",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=f"−{fmt_money(tx.amount, sym)}",
                         font=("Segoe UI", 12, "bold"), text_color=theme.RED
                         ).pack(side="right", padx=(0, 10))
            if tx.attachments:
                ctk.CTkButton(row, text=f"🧾 {len(tx.attachments)}", width=44, height=26,
                              fg_color="transparent", border_color=theme.BORDER, border_width=1,
                              text_color=theme.ACCENT, font=("Segoe UI", 11),
                              command=lambda t=tx: self._show_receipts(modal, t)
                              ).pack(side="right", padx=(0, 4))

        modal.add_buttons("Close", modal.destroy, cancel_text="")
        for child in list(modal.footer.winfo_children()):
            if child.cget("text") == "":
                child.destroy()

    def _show_receipts(self, parent_modal, tx):
        modal = Modal(parent_modal, "Proof of Payment", width=460, height=420)
        section = AttachmentSection(modal.body, self.ctx, "transaction", entity=tx,
                                    title="🧾 Receipts for this payment")
        section.pack(fill="x")
        modal.add_buttons("Close", modal.destroy, cancel_text="")
        for child in list(modal.footer.winfo_children()):
            if child.cget("text") == "":
                child.destroy()

    def _rebuild(self):
        safe_rebuild(self, self._build)
