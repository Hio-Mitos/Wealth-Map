"""
WealthMap – Opportunities Panel
Tracks "attempts" to gain (or take on) money — credit card applications,
loan/mortgage applications, investment opportunities, new income streams,
business ventures, etc. — with status tracking and supporting documents.
"""

import tkinter as tk
from tkinter import messagebox, filedialog
import customtkinter as ctk
from datetime import datetime, timezone

from src.models.database import (
    OpportunityCategory, OpportunityDirection, OpportunityStatus, AccountType
)
from src.ui.widgets import (
    SectionHeader, StatCard, DataTable, Modal,
    make_entry, make_combo, make_textbox, fmt_money,
    attach_currency_tooltip, AttachmentSection
)
from src.ui.theme import theme

STATUS_COLORS = {
    OpportunityStatus.CONSIDERING: "TEXT_SEC",
    OpportunityStatus.RESEARCHING: "ACCENT",
    OpportunityStatus.APPLIED:     "GOLD",
    OpportunityStatus.PENDING:     "GOLD",
    OpportunityStatus.APPROVED:    "GREEN",
    OpportunityStatus.ACTIVE:      "GREEN",
    OpportunityStatus.REJECTED:    "RED",
    OpportunityStatus.DECLINED:    "TEXT_SEC",
    OpportunityStatus.COMPLETED:   "ACCENT2",
}


class OpportunitiesPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._filter_status = "All"
        self._filter_direction = "All"
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        main = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        main.pack(fill="both", expand=True, padx=24, pady=16)
        main.grid_columnconfigure(0, weight=1)

        SectionHeader(main, "🎯 Opportunities", "Attempts to grow your assets — or take on new debt — tracked end to end",
                      "＋ New Opportunity", self._open_new_opportunity
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 20))

        opps = self.ctx.opportunity.get_all()

        # Summary cards
        active_count = sum(1 for o in opps if o.status in (OpportunityStatus.APPLIED, OpportunityStatus.PENDING))
        approved_assets = sum((o.estimated_value or 0) for o in opps
                              if o.status in (OpportunityStatus.APPROVED, OpportunityStatus.ACTIVE)
                              and o.direction == OpportunityDirection.ASSET)
        approved_liab = sum((o.estimated_value or 0) for o in opps
                            if o.status in (OpportunityStatus.APPROVED, OpportunityStatus.ACTIVE)
                            and o.direction == OpportunityDirection.LIABILITY)

        cards = ctk.CTkFrame(main, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        for i in range(3):
            cards.grid_columnconfigure(i, weight=1)
        StatCard(cards, "Total Tracked", str(len(opps)), "", theme.ACCENT, "📋"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(cards, "In Progress", str(active_count), "Applied / Pending", theme.GOLD, "⏳"
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        StatCard(cards, "Approved/Active Value", f"{sym}{approved_assets:,.0f} assets / {sym}{approved_liab:,.0f} liabilities",
                 "", theme.GREEN, "✅"
                 ).grid(row=0, column=2, sticky="ew")

        # Filter bar
        filter_bar = ctk.CTkFrame(main, fg_color=theme.BG_CARD, corner_radius=10,
                                  border_width=1, border_color=theme.BORDER)
        filter_bar.grid(row=2, column=0, sticky="ew", pady=(0, 12))
        ctk.CTkLabel(filter_bar, text="Filter:", text_color=theme.TEXT_SEC,
                     font=("Segoe UI", 12)).pack(side="left", padx=(12, 8), pady=10)
        status_opts = ["All"] + [s.value for s in OpportunityStatus]
        self._status_filter = make_combo(filter_bar, status_opts, width=160, command=self._apply_filter)
        self._status_filter.set("All")
        self._status_filter.pack(side="left", padx=4, pady=8)
        dir_opts = ["All"] + [d.value for d in OpportunityDirection]
        self._dir_filter = make_combo(filter_bar, dir_opts, width=160, command=self._apply_filter)
        self._dir_filter.set("All")
        self._dir_filter.pack(side="left", padx=4, pady=8)

        # Cards list
        self._list_frame = ctk.CTkFrame(main, fg_color="transparent")
        self._list_frame.grid(row=3, column=0, sticky="ew")
        self._list_frame.grid_columnconfigure(0, weight=1)
        self._render_list(sym, base)

    def _apply_filter(self, *_):
        for w in self._list_frame.winfo_children():
            w.destroy()
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""
        self._render_list(sym, base)

    def _render_list(self, sym, base):
        opps = self.ctx.opportunity.get_all()
        status_f = self._status_filter.get()
        dir_f = self._dir_filter.get()

        shown = 0
        for opp in opps:
            if status_f != "All" and opp.status.value != status_f:
                continue
            if dir_f != "All" and opp.direction.value != dir_f:
                continue
            self._render_card(opp, sym, base)
            shown += 1

        if shown == 0:
            ctk.CTkLabel(self._list_frame,
                         text="No opportunities match this filter yet. Click '＋ New Opportunity' "
                              "to log a credit card application, loan, investment, new income "
                              "stream, or anything else you're considering.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12),
                         wraplength=800, justify="left").grid(row=0, column=0, pady=30, sticky="w")

    def _render_card(self, opp, sym, base):
        row_i = self._list_frame.grid_size()[1]
        card = ctk.CTkFrame(self._list_frame, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=theme.BORDER)
        card.grid(row=row_i, column=0, sticky="ew", pady=(0, 10))

        hdr = ctk.CTkFrame(card, fg_color=theme.BG_HOVER, corner_radius=0)
        hdr.pack(fill="x")
        status_color = getattr(theme, STATUS_COLORS.get(opp.status, "TEXT_SEC"))
        ctk.CTkLabel(hdr, text=f"{opp.category.value}  •  {opp.direction.value}",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(hdr, text=opp.status.value, font=("Segoe UI", 10, "bold"),
                     text_color=status_color).pack(side="right", padx=12)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=12)
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        ctk.CTkLabel(left, text=opp.title, font=("Segoe UI", 15, "bold"),
                     text_color=theme.TEXT_PRI).pack(anchor="w")
        if opp.institution:
            ctk.CTkLabel(left, text=opp.institution, font=("Segoe UI", 11),
                         text_color=theme.TEXT_SEC).pack(anchor="w")
        if opp.description:
            ctk.CTkLabel(left, text=opp.description, font=("Segoe UI", 11),
                         text_color=theme.TEXT_SEC, wraplength=500, justify="left").pack(anchor="w", pady=(2, 0))
        meta = []
        if opp.applied_date:
            meta.append(f"Applied {opp.applied_date.strftime('%d %b %Y')}")
        if opp.decision_date:
            meta.append(f"Decision {opp.decision_date.strftime('%d %b %Y')}")
        if opp.interest_rate:
            meta.append(f"Rate: {opp.interest_rate:.2f}%")
        if meta:
            ctk.CTkLabel(left, text="  •  ".join(meta), font=("Segoe UI", 10),
                         text_color=theme.TEXT_SEC).pack(anchor="w", pady=(4, 0))
        if opp.attachments:
            ctk.CTkLabel(left, text=f"📎 {len(opp.attachments)} file(s) attached", font=("Segoe UI", 10),
                         text_color=theme.ACCENT).pack(anchor="w", pady=(2, 0))
        if opp.linked_account:
            ctk.CTkLabel(left, text=f"🔗 Linked to account: {opp.linked_account.name}", font=("Segoe UI", 10),
                         text_color=theme.GREEN).pack(anchor="w", pady=(2, 0))

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="right")
        if opp.estimated_value:
            cur = opp.currency
            csym = cur.symbol if cur else sym
            val_color = theme.GREEN if opp.direction == OpportunityDirection.ASSET else theme.RED
            ctk.CTkLabel(right, text=fmt_money(opp.estimated_value, csym),
                         font=("Segoe UI", 18, "bold"), text_color=val_color).pack(anchor="e")
            ctk.CTkLabel(right, text="estimated value", font=("Segoe UI", 10),
                         text_color=theme.TEXT_SEC).pack(anchor="e")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(btn_row, text="✎ Edit", width=80, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=lambda o=opp: self._open_edit_modal(o)).pack(side="left")
        ctk.CTkButton(btn_row, text="＋ Attach File", width=110, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=lambda o=opp: self._attach_file(o)).pack(side="left", padx=6)
        if opp.status in (OpportunityStatus.APPROVED, OpportunityStatus.ACTIVE) and not opp.linked_account:
            ctk.CTkButton(btn_row, text="🔗 Link / Create Account", width=170, height=28,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.GREEN, font=("Segoe UI", 11),
                          command=lambda o=opp: self._link_account(o)).pack(side="left", padx=6)

        for att in opp.attachments:
            att_row = ctk.CTkFrame(card, fg_color=theme.ROW_ALT, corner_radius=6)
            att_row.pack(fill="x", padx=16, pady=2)
            ctk.CTkLabel(att_row, text=f"📎 {att.original_filename}",
                         font=("Segoe UI", 11), text_color=theme.ACCENT).pack(side="left", padx=8, pady=4)
            ctk.CTkButton(att_row, text="Open", width=60, height=24,
                          fg_color="transparent", text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=lambda a=att: self.ctx.attachment.open_file(a)).pack(side="right", padx=4)
            ctk.CTkButton(att_row, text="✕", width=28, height=24,
                          fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                          command=lambda a=att, o=opp: self._delete_attachment(a, o)).pack(side="right")
        if opp.attachments:
            ctk.CTkLabel(card, text="", height=4).pack()

    # ── Attachments ──────────────────────────────────────────────────────────

    def _attach_file(self, opp):
        path = filedialog.askopenfilename(
            title="Attach file to opportunity (any file type — offer letters, "
                  "applications, contracts, screenshots, etc.)",
            filetypes=[("All files", "*.*"),
                       ("Documents & images", "*.pdf *.png *.jpg *.jpeg *.gif *.webp *.doc *.docx *.xls *.xlsx *.csv *.txt")]
        )
        if not path:
            return
        try:
            self.ctx.attachment.save_file(path, self.ctx.session, "opportunity", opp.id)
            self.ctx.session.refresh(opp)
            self._apply_filter()
        except Exception as e:
            messagebox.showerror("Attach Error", str(e))

    def _delete_attachment(self, att, opp):
        if messagebox.askyesno("Delete Attachment", f"Remove '{att.original_filename}'?"):
            self.ctx.attachment.delete_file(att, self.ctx.session)
            self.ctx.session.refresh(opp)
            self._apply_filter()

    # ── Link to account ──────────────────────────────────────────────────────

    def _link_account(self, opp):
        accounts = self.ctx.account.get_all()
        acc_names = [a.name for a in accounts]
        modal = Modal(self, f"Link '{opp.title}' to an Account", width=460, height=320)
        ctk.CTkLabel(modal.body,
                     text="Link this opportunity to an existing account, marking it Active.",
                     font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                     wraplength=400, justify="left").pack(anchor="w", pady=(0, 12))
        if acc_names:
            acc_c = modal.add_field("Existing Account", lambda p: make_combo(p, acc_names))
            acc_c.set(acc_names[0])
        else:
            acc_c = None
            ctk.CTkLabel(modal.body, text="No accounts yet — create one from the Accounts panel first.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack()

        def save():
            if not acc_c:
                modal.destroy()
                return
            acc = next((a for a in accounts if a.name == acc_c.get()), None)
            if acc:
                self.ctx.opportunity.link_account(opp, acc)
            modal.destroy()
            self._apply_filter()

        modal.add_buttons("Link Account", save)

    # ── New / edit opportunity ───────────────────────────────────────────────

    def _open_new_opportunity(self):
        self._opportunity_modal(None)

    def _open_edit_modal(self, opp):
        self._opportunity_modal(opp)

    def _opportunity_modal(self, opp):
        is_edit = opp is not None
        modal = Modal(self, "Edit Opportunity" if is_edit else "New Opportunity", width=520, height=760)
        currencies = [c.code for c in self.ctx.currency.get_all()]
        categories = [c.value for c in OpportunityCategory]
        directions = [d.value for d in OpportunityDirection]
        statuses   = [s.value for s in OpportunityStatus]

        title_e = modal.add_field("Title", lambda p: make_entry(p, "e.g. Chase Sapphire Preferred application"))
        cat_c   = modal.add_field("Category", lambda p: make_combo(p, categories))
        dir_c   = modal.add_field("Direction", lambda p: make_combo(p, directions))
        status_c= modal.add_field("Status", lambda p: make_combo(p, statuses))
        inst_e  = modal.add_field("Institution", lambda p: make_entry(p, "Bank / Lender / Broker / Employer"))

        val_row = ctk.CTkFrame(modal.body, fg_color="transparent")
        val_row.pack(fill="x", pady=(0, 8))
        ctk.CTkLabel(val_row, text="Estimated Value & Currency", font=("Segoe UI", 12),
                     text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")
        val_inner = ctk.CTkFrame(val_row, fg_color="transparent")
        val_inner.pack(fill="x", pady=(2, 0))
        val_e = make_entry(val_inner, "e.g. 10000")
        val_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
        val_cur_c = make_combo(val_inner, currencies, width=90)
        val_cur_c.pack(side="left")
        attach_currency_tooltip(val_cur_c, self.ctx)

        rate_e  = modal.add_field("Interest Rate / Expected Return % (optional)", lambda p: make_entry(p, "e.g. 22.5"))
        applied_e = modal.add_field("Applied Date (YYYY-MM-DD, optional)", lambda p: make_entry(p, "YYYY-MM-DD"))
        decision_e = modal.add_field("Decision Date (YYYY-MM-DD, optional)", lambda p: make_entry(p, "YYYY-MM-DD"))
        desc_t  = modal.add_field("Description", lambda p: make_textbox(p, height=60))
        notes_t = modal.add_field("Notes", lambda p: make_textbox(p, height=60))

        att_section = AttachmentSection(modal.body, self.ctx, "opportunity",
                                        entity=opp if is_edit else None)
        att_section.pack(fill="x")

        if is_edit:
            title_e.insert(0, opp.title)
            cat_c.set(opp.category.value)
            dir_c.set(opp.direction.value)
            status_c.set(opp.status.value)
            inst_e.insert(0, opp.institution or "")
            if opp.estimated_value:
                val_e.insert(0, f"{opp.estimated_value:g}")
            val_cur_c.set(opp.currency.code if opp.currency else "USD")
            if opp.interest_rate:
                rate_e.insert(0, f"{opp.interest_rate:g}")
            if opp.applied_date:
                applied_e.insert(0, opp.applied_date.strftime("%Y-%m-%d"))
            if opp.decision_date:
                decision_e.insert(0, opp.decision_date.strftime("%Y-%m-%d"))
            desc_t.insert("1.0", opp.description or "")
            notes_t.insert("1.0", opp.notes or "")
        else:
            cat_c.set(categories[0])
            dir_c.set(directions[0])
            status_c.set(statuses[0])
            val_cur_c.set(self.ctx.settings.get("base_currency", "USD"))

        def parse_date(text):
            text = text.strip()
            if not text:
                return None
            try:
                return datetime.strptime(text, "%Y-%m-%d")
            except ValueError:
                return None

        def save():
            try:
                title = title_e.get().strip()
                if not title:
                    raise ValueError("Title is required")
                category = next(c for c in OpportunityCategory if c.value == cat_c.get())
                direction = next(d for d in OpportunityDirection if d.value == dir_c.get())
                status = next(s for s in OpportunityStatus if s.value == status_c.get())
                est_val_text = val_e.get().strip()
                est_val = float(est_val_text.replace(",", "")) if est_val_text else None
                rate_text = rate_e.get().strip()
                rate = float(rate_text) if rate_text else None

                fields = dict(
                    title=title, category=category, direction=direction, status=status,
                    institution=inst_e.get().strip(),
                    estimated_value=est_val,
                    currency_code=val_cur_c.get() if est_val is not None else None,
                    interest_rate=rate,
                    applied_date=parse_date(applied_e.get()),
                    decision_date=parse_date(decision_e.get()),
                    description=desc_t.get("1.0", "end").strip(),
                    notes=notes_t.get("1.0", "end").strip(),
                )
                if is_edit:
                    self.ctx.opportunity.update(opp, **fields)
                else:
                    new_opp = self.ctx.opportunity.create(**fields)
                    att_section.commit(new_opp.id)
                modal.destroy()
                self._apply_filter()
            except ValueError as e:
                messagebox.showerror("Validation Error", str(e), parent=modal)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete():
            if messagebox.askyesno("Delete Opportunity",
                                   f"Delete '{opp.title}' and any attached files? "
                                   "This cannot be undone.", parent=modal):
                self.ctx.opportunity.delete(opp)
                modal.destroy()
                self._apply_filter()

        extra = [("Delete", delete, theme.RED)] if is_edit else None
        modal.add_buttons("Save Changes" if is_edit else "Create", save, extra=extra)
