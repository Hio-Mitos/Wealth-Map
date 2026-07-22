"""
WealthMap – Employees Panel (Business profiles only)

Employee directory with a base salary/currency/pay-frequency template and
a list of recurring standard earning/deduction lines (allowances, statutory
contributions, etc.) — used to pre-fill payslip generation in the Payslips
tab so only period-specific adjustments need to be entered by hand.
"""

from datetime import datetime
from tkinter import messagebox
import customtkinter as ctk

from src.ui.widgets import (safe_rebuild,
    SectionHeader, StatCard, Modal,
    make_entry, make_combo, make_textbox, fmt_money,
    attach_currency_tooltip, CurrencySearchEntry
)
from src.ui.theme import theme

FREQ_LABELS = {
    "monthly": "Monthly", "semi_monthly": "Semi-Monthly",
    "biweekly": "Bi-Weekly", "weekly": "Weekly",
}
FREQ_BY_LABEL = {v: k for k, v in FREQ_LABELS.items()}


class EmployeesPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._show_inactive = False
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        SectionHeader(scroll, "Employees",
                      "Directory and salary templates used to generate payslips",
                      "＋ New Employee", self._open_new_employee
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 16))

        employees = self.ctx.employee.get_all(include_inactive=self._show_inactive)
        active = [e for e in employees if e.is_active]
        total_payroll = sum(
            self.ctx.currency.convert(e.base_salary, e.currency.code if e.currency else base, base)
            or e.base_salary for e in active
        )
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        cards = ctk.CTkFrame(scroll, fg_color="transparent")
        cards.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        for i in range(2):
            cards.grid_columnconfigure(i, weight=1)
        StatCard(cards, "Active Employees", str(len(active)), "", theme.ACCENT, "👥"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(cards, "Total Base Payroll", fmt_money(total_payroll, sym),
                 "per pay cycle (base salaries only)", theme.GOLD, "💵"
                 ).grid(row=0, column=1, sticky="ew")

        toggle_row = ctk.CTkFrame(scroll, fg_color="transparent")
        toggle_row.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        self._inactive_switch = ctk.CTkSwitch(
            toggle_row, text="Show inactive employees", font=("Segoe UI", 12),
            text_color=theme.TEXT_SEC, progress_color=theme.ACCENT,
            command=self._toggle_inactive)
        self._inactive_switch.pack(side="left")
        if self._show_inactive:
            self._inactive_switch.select()

        for emp in employees:
            self._render_employee_card(scroll, emp)

        if not employees:
            ctk.CTkLabel(scroll, text="No employees yet — add one to start generating payslips.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 13)).grid(
                row=scroll.grid_size()[1], column=0, pady=40)

    def _render_employee_card(self, scroll, emp):
        cur = emp.currency
        sym = cur.symbol if cur else ""

        card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=theme.BORDER)
        card.grid(row=scroll.grid_size()[1], column=0, sticky="ew", pady=(0, 10))

        hdr = ctk.CTkFrame(card, fg_color=theme.BG_HOVER, corner_radius=0)
        hdr.pack(fill="x")
        status_txt = "Active" if emp.is_active else "Inactive"
        status_col = theme.GREEN if emp.is_active else theme.TEXT_SEC
        ctk.CTkLabel(hdr, text=status_txt, font=("Segoe UI", 11, "bold"),
                     text_color=status_col).pack(side="left", padx=12, pady=8)
        ctk.CTkLabel(hdr, text=FREQ_LABELS.get(emp.pay_frequency, emp.pay_frequency),
                     font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(side="right", padx=12)

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=12)
        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        title = emp.name + (f"  ({emp.employee_code})" if emp.employee_code else "")
        ctk.CTkLabel(left, text=title, font=("Segoe UI", 15, "bold"),
                     text_color=theme.TEXT_PRI).pack(anchor="w")
        sub = "  •  ".join(x for x in (emp.position, emp.department.name if emp.department else "") if x)
        if sub:
            ctk.CTkLabel(left, text=sub, font=("Segoe UI", 11),
                         text_color=theme.TEXT_SEC).pack(anchor="w")
        contact = "  •  ".join(x for x in (emp.email, emp.phone) if x)
        if contact:
            ctk.CTkLabel(left, text=contact, font=("Segoe UI", 10),
                         text_color=theme.TEXT_SEC).pack(anchor="w")
        earnings = [l for l in emp.comp_lines if l.section == "earning"]
        deductions = [l for l in emp.comp_lines if l.section == "deduction"]
        if earnings or deductions:
            ctk.CTkLabel(left, text=f"{len(earnings)} standard earning line(s), "
                                    f"{len(deductions)} standard deduction line(s)",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="w")
        if emp.payslips:
            ctk.CTkLabel(left, text=f"{len(emp.payslips)} payslip(s) generated",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="w")

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkLabel(right, text=fmt_money(emp.base_salary, sym),
                     font=("Segoe UI", 18, "bold"), text_color=theme.TEXT_PRI).pack(anchor="e")
        ctk.CTkLabel(right, text=f"base / {FREQ_LABELS.get(emp.pay_frequency, emp.pay_frequency).lower()}",
                     font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="e")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        ctk.CTkButton(btn_row, text="💰 Comp Template", width=140, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=lambda e=emp: self._manage_comp_lines(e)).pack(side="left")
        ctk.CTkButton(btn_row, text="✎ Edit", width=70, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=lambda e=emp: self._edit_employee(e)).pack(side="left", padx=6)

    def _toggle_inactive(self):
        self._show_inactive = not self._show_inactive
        self._rebuild()

    # ── New / Edit ────────────────────────────────────────────────────────

    def _employee_form(self, modal, emp=None):
        departments = self.ctx.department.get_all()
        dept_options = ["(none)"] + [d.name for d in departments]

        name_e = modal.add_field("Full Name", lambda p: make_entry(p, "Employee's name"))
        code_e = modal.add_field("Employee Code", lambda p: make_entry(p, "Optional"))
        pos_e = modal.add_field("Position / Title", lambda p: make_entry(p, "e.g. Software Engineer"))
        dept_c = modal.add_field("Department", lambda p: make_combo(p, dept_options))
        email_e = modal.add_field("Email", lambda p: make_entry(p, "Optional"))
        phone_e = modal.add_field("Phone", lambda p: make_entry(p, "Optional"))
        hire_e = modal.add_field("Hire Date (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
        salary_e = modal.add_field("Base Salary", lambda p: make_entry(p, "0.00"))
        cur_c = modal.add_field("Currency", lambda p: CurrencySearchEntry(
            p, self.ctx, width=120,
            initial_code=(emp.currency.code if emp and emp.currency
                          else self.ctx.settings.get("base_currency", "USD"))))
        attach_currency_tooltip(cur_c, self.ctx)
        freq_c = modal.add_field("Pay Frequency", lambda p: make_combo(p, list(FREQ_LABELS.values())))
        notes_t = modal.add_field("Notes", lambda p: make_textbox(p, height=50))

        if emp:
            name_e.insert(0, emp.name)
            code_e.insert(0, emp.employee_code or "")
            pos_e.insert(0, emp.position or "")
            dept_c.set(emp.department.name if emp.department else "(none)")
            email_e.insert(0, emp.email or "")
            phone_e.insert(0, emp.phone or "")
            if emp.hire_date:
                hire_e.insert(0, emp.hire_date.strftime("%Y-%m-%d"))
            salary_e.insert(0, f"{emp.base_salary:g}")
            freq_c.set(FREQ_LABELS.get(emp.pay_frequency, "Monthly"))
            notes_t.insert("1.0", emp.notes or "")
        else:
            dept_c.set("(none)")
            freq_c.set("Monthly")

        def read():
            cur_c.resolve()
            name = name_e.get().strip()
            if not name:
                raise ValueError("Give the employee a name.")
            try:
                salary = float(salary_e.get().replace(",", "") or 0)
            except ValueError:
                raise ValueError("Base salary must be a number.") from None
            hire_date = None
            hire_txt = hire_e.get().strip()
            if hire_txt:
                try:
                    hire_date = datetime.strptime(hire_txt, "%Y-%m-%d")
                except ValueError:
                    raise ValueError("Hire date must be YYYY-MM-DD.") from None
            dept = next((d for d in departments if d.name == dept_c.get()), None)
            return dict(
                name=name, employee_code=code_e.get().strip(), position=pos_e.get().strip(),
                department_id=dept.id if dept else None,
                email=email_e.get().strip(), phone=phone_e.get().strip(),
                hire_date=hire_date, base_salary=salary,
                currency_code=cur_c.get(),
                pay_frequency=FREQ_BY_LABEL.get(freq_c.get(), "monthly"),
                notes=notes_t.get("1.0", "end").strip(),
            )

        return read

    def _open_new_employee(self):
        modal = Modal(self, "New Employee", width=480, height=760)
        read = self._employee_form(modal)

        def save():
            try:
                self.ctx.employee.create(**read())
                modal.destroy()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Create", save)

    def _edit_employee(self, emp):
        modal = Modal(self, f"Edit Employee — {emp.name}", width=480, height=800)
        read = self._employee_form(modal, emp)

        active_var = ctk.BooleanVar(value=emp.is_active)
        ctk.CTkCheckBox(modal.body, text="Active (available for payslip generation)",
                        variable=active_var, font=("Segoe UI", 12),
                        text_color=theme.TEXT_SEC, fg_color=theme.ACCENT
                        ).pack(anchor="w", pady=(4, 0))

        def save():
            try:
                fields = read()
                fields["is_active"] = active_var.get()
                self.ctx.employee.update(emp, **fields)
                modal.destroy()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete():
            msg = (f"Delete '{emp.name}' from the employee directory?\n\n"
                   f"Any payslips already generated for them ({len(emp.payslips)}) are "
                   "kept as a historical record — they'll just no longer be linked to "
                   "an employee profile.")
            if messagebox.askyesno("Delete Employee", msg, parent=modal):
                self.ctx.employee.delete(emp)
                modal.destroy()
                self._rebuild()

        modal.add_buttons("Save Changes", save, extra=[("Delete Employee", delete, theme.RED)])

    # ── Standard compensation template ──────────────────────────────────────

    def _manage_comp_lines(self, emp):
        modal = Modal(self, f"Compensation Template — {emp.name}", width=560, height=620)
        cur = emp.currency
        sym = cur.symbol if cur else ""
        ctk.CTkLabel(modal.body,
                     text=f"Base salary {fmt_money(emp.base_salary, sym)} is always included. "
                          "Add any recurring allowances or standard deductions below — these "
                          "pre-fill every payslip generated for this employee.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     wraplength=500, justify="left").pack(fill="x", pady=(0, 10))

        for section, title in (("earning", "💰 Standard Earnings / Allowances"),
                               ("deduction", "💸 Standard Deductions")):
            ctk.CTkLabel(modal.body, text=title, font=("Segoe UI", 12, "bold"),
                         text_color=theme.ACCENT).pack(anchor="w", pady=(8, 4))
            container = ctk.CTkFrame(modal.body, fg_color="transparent")
            container.pack(fill="x", pady=(0, 4))
            lines = [l for l in emp.comp_lines if l.section == section]
            if not lines:
                ctk.CTkLabel(container, text="(none)", font=("Segoe UI", 11),
                             text_color=theme.TEXT_SEC).pack(anchor="w", pady=2)
            for line in lines:
                row = ctk.CTkFrame(container, fg_color=theme.BG_HOVER, corner_radius=8)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=line.label, font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI, anchor="w").pack(
                    side="left", fill="x", expand=True, padx=10, pady=8)
                ctk.CTkLabel(row, text=fmt_money(line.amount, sym), font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="left", padx=6)
                ctk.CTkButton(row, text="✕", width=28, height=28,
                              fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 12),
                              command=lambda l=line: (self.ctx.employee.remove_comp_line(l),
                                                      modal.destroy(), self._manage_comp_lines(emp))
                              ).pack(side="right", padx=6)

            add_row = ctk.CTkFrame(modal.body, fg_color="transparent")
            add_row.pack(fill="x", pady=(0, 8))
            label_e = make_entry(add_row, "Label")
            label_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
            amt_e = make_entry(add_row, "Amount", width=100)
            amt_e.pack(side="left", padx=4)

            def add_line(section=section, label_e=label_e, amt_e=amt_e):
                try:
                    amt = float(amt_e.get().replace(",", "") or 0)
                except ValueError:
                    messagebox.showerror("Invalid Amount", "Amount must be a number.", parent=modal)
                    return
                label = label_e.get().strip()
                if not label or amt == 0:
                    return
                self.ctx.employee.add_comp_line(emp, section, label, amt)
                modal.destroy()
                self._manage_comp_lines(emp)

            ctk.CTkButton(add_row, text="＋ Add", width=70, height=32,
                          fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED, text_color="#fff",
                          font=("Segoe UI", 11), command=add_line).pack(side="left", padx=4)

        modal.add_buttons("Close", modal.destroy, cancel_text="")
        for child in list(modal.footer.winfo_children()):
            if child.cget("text") == "":
                child.destroy()

    def _rebuild(self):
        safe_rebuild(self, self._build)
