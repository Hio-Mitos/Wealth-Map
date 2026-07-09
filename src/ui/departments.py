"""
WealthMap – Departments Panel (Business profiles)
Cost-center management with per-department cash flow / P&L.
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from src.ui.widgets import (
    SectionHeader, Modal, safe_rebuild,
    make_entry, make_textbox, fmt_money
)
from src.ui.theme import theme

COLOR_CHOICES = [
    "#4A90D9", "#9B59B6", "#F5A623", "#E74C3C", "#7ED321",
    "#2ECC71", "#1ABC9C", "#E67E22", "#F1C40F", "#34495E",
]


class DepartmentsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._build()

    def _rebuild(self):
        safe_rebuild(self, self._build)

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)

        SectionHeader(scroll, "Departments",
                      "Cost centers for department-level cash flow & P&L — "
                      "assign accounts and transactions to a department to see it broken out here.",
                      "＋ Add Department", self._open_new_dept).pack(fill="x", pady=(0, 16))

        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        depts = self.ctx.department.get_all()
        if not depts:
            ctk.CTkLabel(scroll, text="No departments yet. Add one (e.g. \"Sales\", \"Engineering\", "
                                       "\"Marketing\") to start tagging accounts and transactions "
                                       "for department-level cash flow — it'll show up on the "
                                       "Cash Flow dashboard too.",
                         font=("Segoe UI", 13), text_color=theme.TEXT_SEC,
                         wraplength=700, justify="left").pack(anchor="w", pady=20)
            return

        cash_flow = {row["name"]: row for row in self.ctx.department.cash_flow_summary(base, months=1)}
        accounts = self.ctx.account.get_all()

        for dept in depts:
            cf = cash_flow.get(dept.name, {"income": 0.0, "expense": 0.0, "net": 0.0})
            card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
            card.pack(fill="x", pady=6)

            top = ctk.CTkFrame(card, fg_color="transparent")
            top.pack(fill="x", padx=16, pady=(14, 4))
            ctk.CTkFrame(top, width=16, height=16, fg_color=dept.color, corner_radius=4
                        ).pack(side="left", padx=(0, 10))
            ctk.CTkLabel(top, text=dept.name, font=("Segoe UI", 15, "bold"),
                         text_color=theme.TEXT_PRI).pack(side="left")

            if dept.description:
                ctk.CTkLabel(card, text=dept.description, font=("Segoe UI", 11),
                             text_color=theme.TEXT_SEC, anchor="w").pack(fill="x", padx=16, pady=(2, 0))

            stats = ctk.CTkFrame(card, fg_color="transparent")
            stats.pack(fill="x", padx=16, pady=(8, 2))
            net_color = theme.GREEN if cf["net"] >= 0 else theme.RED
            ctk.CTkLabel(stats, text=f"This month  •  Income {fmt_money(cf['income'], sym)}   "
                                     f"Expenses {fmt_money(cf['expense'], sym)}   Net ",
                         font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(side="left")
            ctk.CTkLabel(stats, text=fmt_money(cf['net'], sym), font=("Segoe UI", 12, "bold"),
                         text_color=net_color).pack(side="left")

            n_accounts = sum(1 for a in accounts if a.department_id == dept.id)
            ctk.CTkLabel(card, text=f"{n_accounts} account(s) assigned",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC, anchor="w"
                         ).pack(fill="x", padx=16, pady=(0, 8))

            btn_row = ctk.CTkFrame(card, fg_color="transparent")
            btn_row.pack(fill="x", padx=16, pady=(0, 14))
            ctk.CTkButton(btn_row, text="✎ Edit", width=80, height=30,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.ACCENT, font=("Segoe UI", 12),
                          command=lambda d=dept: self._open_edit_dept(d)).pack(side="left", padx=(0, 8))
            ctk.CTkButton(btn_row, text="🗑 Delete", width=90, height=30,
                          fg_color="transparent", border_color=theme.RED, border_width=1,
                          text_color=theme.RED, font=("Segoe UI", 12),
                          command=lambda d=dept: self._delete(d)).pack(side="left")

    # ── Modals ───────────────────────────────────────────────────────────

    def _dept_modal(self, dept=None):
        is_edit = dept is not None
        modal = Modal(self, "Edit Department" if is_edit else "New Department", width=480, height=440)

        name_e = modal.add_field("Name", lambda p: make_entry(p, "e.g. Sales"))
        desc_t = modal.add_field("Description (optional)", lambda p: make_textbox(p, height=60))

        ctk.CTkLabel(modal.body, text="Color", font=("Segoe UI", 12),
                     text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")
        color_row = ctk.CTkFrame(modal.body, fg_color="transparent")
        color_row.pack(fill="x", pady=(4, 8))
        selected = {"color": dept.color if is_edit else COLOR_CHOICES[0]}
        swatches = {}

        def pick(c):
            selected["color"] = c
            for col, btn in swatches.items():
                btn.configure(border_width=3 if col == c else 0,
                              border_color=theme.TEXT_PRI)

        for c in COLOR_CHOICES:
            b = ctk.CTkButton(color_row, text="", width=28, height=28, corner_radius=6,
                             fg_color=c, hover_color=c, command=lambda c=c: pick(c))
            b.pack(side="left", padx=3)
            swatches[c] = b
        pick(selected["color"])

        if is_edit:
            name_e.insert(0, dept.name)
            if dept.description:
                desc_t.insert("1.0", dept.description)

        def save():
            name = name_e.get().strip()
            if not name:
                messagebox.showerror("Error", "Name cannot be empty", parent=modal)
                return
            try:
                if is_edit:
                    self.ctx.department.update(dept, name=name,
                                                color=selected["color"],
                                                description=desc_t.get("1.0", "end").strip())
                else:
                    self.ctx.department.create(name, selected["color"],
                                               desc_t.get("1.0", "end").strip())
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Save Changes" if is_edit else "Add Department", save)

    def _open_new_dept(self):
        self._dept_modal()

    def _open_edit_dept(self, dept):
        self._dept_modal(dept)

    def _delete(self, dept):
        if messagebox.askyesno("Delete Department",
                               f"Delete '{dept.name}'? Accounts and transactions tagged with "
                               "this department will become unassigned (their data is kept)."):
            self.ctx.department.delete(dept)
            self.app.refresh()
            self._rebuild()
