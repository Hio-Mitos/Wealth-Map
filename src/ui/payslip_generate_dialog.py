"""
WealthMap – Generate Payslip dialog (Business profile)

Business profiles don't import payslip PDFs — they generate them for their
own Employees. Pick an Employee and the fields pre-fill from that employee's
salary template (base salary as a taxable earning + every EmployeeCompLine),
fully editable for the period (overtime, one-off deductions, etc.) before
confirming, exactly like the personal "Import Payslip" review step.

On confirm this creates the Payslip header (Payslip.is_generated=True,
linked back to the Employee), one PayslipLineItem per earning/deduction row
(informational only — no individual transaction per line, since these are
templated figures rather than parsed from a document), and a single net-pay
EXPENSE transaction tagged with payslip_id so it shows up in the business's
ledger and can be reversed via the same delete_cascade used everywhere else.
"""

from datetime import datetime as _dt
import calendar
from tkinter import messagebox
import customtkinter as ctk

from src.models.database import TransactionType
from src.ui.widgets import Modal, make_entry, make_combo
from src.ui.theme import theme


def _default_period(now=None):
    now = now or _dt.now()
    start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_day = calendar.monthrange(now.year, now.month)[1]
    end = start.replace(day=last_day)
    return start, end


def open_generate_payslip_dialog(parent, ctx, on_done=None):
    employees = ctx.employee.get_all()
    if not employees:
        messagebox.showerror("No Employees", "Add an employee first (Employees tab).", parent=parent)
        return
    accounts = ctx.account.get_all()
    if not accounts:
        messagebox.showerror("No Accounts", "Create an account first.", parent=parent)
        return

    emp_names = [e.name for e in employees]
    acc_names = [a.name for a in accounts]

    modal = Modal(parent, "Generate Payslip", width=720, height=820)

    ctk.CTkLabel(modal.body, text="Choose the employee, then adjust any earning or "
                 "deduction row for this specific period — the rest is pre-filled "
                 "from their salary template.",
                 font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                 wraplength=660, justify="left", anchor="w").pack(fill="x", pady=(0, 12))

    emp_c = modal.add_field("Employee", lambda p: make_combo(p, emp_names, command=lambda *_: _on_emp_change()))
    acc_c = modal.add_field("Pay From Account", lambda p: make_combo(p, acc_names))
    acc_c.set(acc_names[0])

    period_start, period_end = _default_period()
    start_e = modal.add_field("Period Start (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
    start_e.insert(0, period_start.strftime("%Y-%m-%d"))
    end_e = modal.add_field("Period End (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
    end_e.insert(0, period_end.strftime("%Y-%m-%d"))

    # ── Editable row sections, rebuilt whenever the employee changes ───────
    sections_frame = ctk.CTkFrame(modal.body, fg_color="transparent")
    sections_frame.pack(fill="x", pady=(6, 4))

    all_rows = {"taxable_earning": [], "deduction": []}
    net_lbl = ctk.CTkLabel(modal.body, text="", font=("Segoe UI", 12, "bold"),
                           text_color=theme.TEXT_SEC, anchor="w")
    net_lbl.pack(fill="x", pady=(4, 8))

    def _recalc(*_a):
        def total(section):
            t = 0.0
            for entry in all_rows[section]:
                try:
                    t += float(entry["amount"].get().replace(",", ""))
                except ValueError:
                    pass
            return t
        gross = total("taxable_earning")
        ded = total("deduction")
        net_lbl.configure(text=f"Gross {gross:,.2f}  −  Deductions {ded:,.2f}  =  Net {gross - ded:,.2f}")

    def _add_row(container, section, label="", amount=0.0):
        row = ctk.CTkFrame(container, fg_color=theme.BG_HOVER, corner_radius=8)
        row.pack(fill="x", pady=2)
        inner = ctk.CTkFrame(row, fg_color="transparent")
        inner.pack(fill="x", padx=6, pady=6)

        desc_e = make_entry(inner, "Description")
        desc_e.insert(0, label)
        desc_e.pack(side="left", fill="x", expand=True, padx=(0, 4))

        amt_e = make_entry(inner, "Amount", width=110)
        amt_e.insert(0, f"{amount:.2f}")
        amt_e.pack(side="left", padx=4)
        amt_e.bind("<KeyRelease>", _recalc)

        entry = {"row": row, "description": desc_e, "amount": amt_e}

        def remove_row():
            entry["row"].destroy()
            if entry in all_rows[section]:
                all_rows[section].remove(entry)
            _recalc()

        ctk.CTkButton(inner, text="✕", width=28, height=28,
                      fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 12),
                      command=remove_row).pack(side="left", padx=(4, 0))

        all_rows[section].append(entry)
        return entry

    def _build_sections():
        for w in list(sections_frame.winfo_children()):
            w.destroy()
        all_rows["taxable_earning"].clear()
        all_rows["deduction"].clear()

        emp = next((e for e in employees if e.name == emp_c.get()), None)
        if not emp:
            _recalc()
            return

        ctk.CTkLabel(sections_frame, text="💰 Earnings", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(6, 4))
        earn_container = ctk.CTkFrame(sections_frame, fg_color="transparent")
        earn_container.pack(fill="x")
        if emp.base_salary:
            _add_row(earn_container, "taxable_earning", "Base Salary", emp.base_salary)
        for line in emp.comp_lines:
            if line.section == "earning":
                _add_row(earn_container, "taxable_earning", line.label, line.amount)
        ctk.CTkButton(sections_frame, text="＋ Add Earning", width=140, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=lambda: (_add_row(earn_container, "taxable_earning"), _recalc())
                      ).pack(anchor="w", pady=(4, 0))

        ctk.CTkLabel(sections_frame, text="💸 Deductions", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(14, 4))
        ded_container = ctk.CTkFrame(sections_frame, fg_color="transparent")
        ded_container.pack(fill="x")
        for line in emp.comp_lines:
            if line.section == "deduction":
                _add_row(ded_container, "deduction", line.label, line.amount)
        ctk.CTkButton(sections_frame, text="＋ Add Deduction", width=140, height=28,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=lambda: (_add_row(ded_container, "deduction"), _recalc())
                      ).pack(anchor="w", pady=(4, 0))

        _recalc()

    def _on_emp_change():
        _build_sections()

    emp_c.set(emp_names[0])
    _build_sections()

    def do_generate():
        try:
            emp = next((e for e in employees if e.name == emp_c.get()), None)
            account = next((a for a in accounts if a.name == acc_c.get()), None)
            if not emp or not account:
                messagebox.showerror("Missing Selection", "Choose an employee and an account.", parent=modal)
                return
            try:
                p_start = _dt.strptime(start_e.get().strip(), "%Y-%m-%d")
                p_end = _dt.strptime(end_e.get().strip(), "%Y-%m-%d")
            except ValueError:
                messagebox.showerror("Invalid Date", "Use the format YYYY-MM-DD.", parent=modal)
                return

            earnings, deductions = [], []
            for entry in all_rows["taxable_earning"]:
                label = entry["description"].get().strip()
                try:
                    amt = float(entry["amount"].get().replace(",", ""))
                except ValueError:
                    amt = 0.0
                if label and amt:
                    earnings.append((label, amt))
            for entry in all_rows["deduction"]:
                label = entry["description"].get().strip()
                try:
                    amt = float(entry["amount"].get().replace(",", ""))
                except ValueError:
                    amt = 0.0
                if label and amt:
                    deductions.append((label, amt))

            if not earnings:
                messagebox.showerror("No Earnings", "Add at least one earning row.", parent=modal)
                return

            gross = sum(a for _, a in earnings)
            total_ded = sum(a for _, a in deductions)
            net = gross - total_ded
            company = ctx.profile.get("name", "") if getattr(ctx, "profile", None) else ""
            currency_code = emp.currency.code if emp.currency else ctx.settings.get("base_currency", "USD")

            payslip = ctx.payslip.create_header_for_employee(
                emp, company=company, period_start=p_start, period_end=p_end,
                gross_pay=gross, total_deductions=total_ded, net_pay=net,
                account=account,
            )
            for label, amt in earnings:
                ctx.payslip.add_item(payslip, "taxable_earning", label, amt)
            for label, amt in deductions:
                ctx.payslip.add_item(payslip, "deduction", label, amt)

            ctx.transaction.add(
                account, TransactionType.EXPENSE, net,
                description=f"Payslip — {emp.name} — {p_end.strftime('%b %Y')}",
                category="Payroll", payee=emp.name, transaction_date=p_end,
                currency_code=currency_code, payslip_id=payslip.id,
                notes="Net pay for this payslip; individual earning/deduction lines are "
                      "informational only and are not separately posted as transactions.",
            )

            modal.destroy()
            messagebox.showinfo("Payslip Generated",
                                f"Net pay {net:,.2f} {currency_code} paid to {emp.name} "
                                f"from {account.name}.", parent=parent)
            if on_done:
                on_done()
        except Exception as e:
            messagebox.showerror("Generate Failed", str(e), parent=modal)

    modal.add_buttons("Generate Payslip", do_generate, cancel_text="Cancel")
