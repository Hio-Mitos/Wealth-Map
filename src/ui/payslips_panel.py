"""
WealthMap – Payslips Panel

Payslips grouped by year, each year headed by a live, calculated
Year-To-Date summary (earnings, deductions, and the real net = earnings −
deductions). The YTD figures are computed from every imported payslip in
that year — so importing a payslip for an earlier month immediately
updates them, and each new year starts from zero.

Also hosts the Payslip Cashflow report: pick any period, see every
earning/deduction label aggregated (each value clickable for the
per-payslip detail behind it), and export the whole thing as PDF or
Excel.
"""

import os
from datetime import datetime
from tkinter import messagebox, filedialog
import customtkinter as ctk

from src.ui.widgets import (safe_rebuild,
    SectionHeader, StatCard, Modal, make_entry, fmt_money_base)
from src.ui.theme import theme
from src.ui.payslip_dialog import open_payslip_import_dialog, show_payslip_viewer
from src.ui.payslip_generate_dialog import open_generate_payslip_dialog

SECTION_TITLES = {
    "taxable_earning":     "💰 Taxable Earnings",
    "non_taxable_earning": "🧾 Non-Taxable Earnings",
    "deduction":           "💸 Deductions",
}


class PayslipsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        self._base = base

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        is_business = getattr(self.ctx, "is_business", False)
        if is_business:
            SectionHeader(scroll, "Payslips",
                          "Generated for your employees, grouped by year with a live "
                          "year-to-date summary",
                          "🧾 Generate Payslip", self._generate_payslip,
                          extra_buttons=[("📈 Payslip Cashflow Report", self._cashflow_report)]
                          ).grid(row=0, column=0, sticky="ew", pady=(0, 16))
        else:
            SectionHeader(scroll, "Payslips",
                          "Grouped by year, with a live year-to-date summary that "
                          "updates whenever a payslip is added",
                          "📄 Import Payslip", self._import_payslip,
                          extra_buttons=[("📈 Payslip Cashflow Report", self._cashflow_report)]
                          ).grid(row=0, column=0, sticky="ew", pady=(0, 16))

        payslips = self.ctx.payslip.get_all()

        cards_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 16))
        for i in range(3):
            cards_frame.grid_columnconfigure(i, weight=1)

        total_net = sum(
            self.ctx.currency.convert(p.net_pay, p.currency_code, base) or p.net_pay
            for p in payslips)
        total_gross = sum(
            self.ctx.currency.convert(p.gross_pay, p.currency_code, base) or p.gross_pay
            for p in payslips)
        StatCard(cards_frame, "Payslips Imported", str(len(payslips)), "", theme.ACCENT, "📋"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(cards_frame, "All-Time Net Pay", fmt_money_base(self.ctx, total_net, base), "", theme.GREEN, "💵"
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        StatCard(cards_frame, "All-Time Gross Pay", fmt_money_base(self.ctx, total_gross, base), "", theme.GOLD, "💰"
                 ).grid(row=0, column=2, sticky="ew")

        if not payslips:
            empty_msg = ('No payslips generated yet — click "Generate Payslip" to get started.'
                        if is_business else
                        'No payslips imported yet — click "Import Payslip" to get started.')
            ctk.CTkLabel(scroll, text=empty_msg,
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 13)).grid(
                row=2, column=0, pady=40)
            return

        # ── Grouped by year, newest first ────────────────────────────────
        for year in self.ctx.payslip.years():
            ytd = self.ctx.payslip.ytd_summary(year)
            code = ytd["currency_code"]
            sym = ""
            cur = self.ctx.currency.get_by_code(code) if code else None
            sym = cur.symbol if cur else ""
            t = ytd["totals"]

            band = ctk.CTkFrame(scroll, fg_color=theme.BG_HOVER, corner_radius=10)
            band.grid(row=scroll.grid_size()[1], column=0, sticky="ew", pady=(14, 8))
            left = ctk.CTkFrame(band, fg_color="transparent")
            left.pack(side="left", padx=14, pady=10)
            ctk.CTkLabel(left, text=f"📆 {year}", font=("Segoe UI", 16, "bold"),
                         text_color=theme.TEXT_PRI).pack(anchor="w")
            ctk.CTkLabel(
                left,
                text=(f"YTD:  Gross {sym}{t['gross']:,.2f}   −   "
                      f"Deductions {sym}{t['deductions']:,.2f}   =   "
                      f"Net {sym}{t['net']:,.2f} {code}   "
                      f"({len(ytd['payslips'])} payslip(s))"),
                font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w")
            ctk.CTkButton(band, text="🔎 YTD Breakdown", width=140, height=30,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=lambda y=year: self._show_summary(
                              f"Year-To-Date Summary — {y}",
                              self.ctx.payslip.ytd_summary(y))
                          ).pack(side="right", padx=14, pady=10)

            for p in ytd["payslips"][::-1]:  # newest first within the year
                self._render_payslip_card(scroll, p)

    def _render_payslip_card(self, scroll, p):
        card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=theme.BORDER, cursor="hand2")
        card.grid(row=scroll.grid_size()[1], column=0, sticky="ew", pady=(0, 8))

        body = ctk.CTkFrame(card, fg_color="transparent")
        body.pack(fill="x", padx=16, pady=12)

        left = ctk.CTkFrame(body, fg_color="transparent")
        left.pack(side="left", fill="x", expand=True)
        period = ""
        if p.period_start and p.period_end:
            period = f"{p.period_start.strftime('%b %Y')}"
        ctk.CTkLabel(left, text=f"{p.company or 'Payslip'}" + (f"  •  {period}" if period else ""),
                     font=("Segoe UI", 14, "bold"), text_color=theme.TEXT_PRI).pack(anchor="w")
        ctk.CTkLabel(left, text=p.employee_name or "", font=("Segoe UI", 11),
                     text_color=theme.TEXT_SEC).pack(anchor="w")

        right = ctk.CTkFrame(body, fg_color="transparent")
        right.pack(side="right")
        ctk.CTkLabel(right, text=f"Net {p.net_pay:,.2f} {p.currency_code}",
                     font=("Segoe UI", 16, "bold"), text_color=theme.GREEN).pack(anchor="e")
        ctk.CTkLabel(right, text=f"Gross {p.gross_pay:,.2f}  −  Deductions {p.total_deductions:,.2f}",
                     font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="e")

        ctk.CTkButton(body, text="🗑", width=32, height=32,
                      fg_color="transparent", hover_color=theme.BG_HOVER,
                      text_color=theme.RED, font=("Segoe UI", 13),
                      command=lambda p=p: self._delete_payslip(p)
                      ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(body, text="📄", width=32, height=32,
                      fg_color="transparent", hover_color=theme.BG_HOVER,
                      text_color=theme.ACCENT, font=("Segoe UI", 13),
                      command=lambda p=p: self._export_payslip_pdf(p)
                      ).pack(side="right", padx=(0, 4))

        def _click(event, p=p):
            self._view(p)
        for w in (card, body, left, right, *left.winfo_children(), *right.winfo_children()):
            w.bind("<Button-1>", _click)

    def _export_payslip_pdf(self, p):
        from src.services.report_generators import PayslipDocument
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = (p.employee_name or "Payslip").replace(" ", "_")
        path = filedialog.asksaveasfilename(
            title="Save payslip as…", defaultextension=".pdf",
            initialfile=f"Payslip_{safe_name}_{ts}.pdf",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")])
        if not path:
            return
        try:
            out = PayslipDocument().generate(self.ctx, p, path)
        except Exception as e:
            messagebox.showerror("Export Failed", str(e), parent=self)
            return
        if messagebox.askyesno("Payslip Ready", f"Saved to:\n{out}\n\nOpen it now?", parent=self):
            try:
                os.startfile(out)  # Windows
            except Exception:
                import webbrowser
                webbrowser.open(f"file://{out}")

    def _delete_payslip(self, p):
        from src.models.database import LoanRepayment, PersonalLoan, Transaction, Bill
        n = len(p.transactions)
        period = ""
        if p.period_start:
            period = f" ({p.period_start.strftime('%b %Y')})"

        # ── Preview: Loans impact ───────────────────────────────────────
        repayments = self.ctx.session.query(LoanRepayment).filter_by(payslip_id=p.id).all()
        auto_loans = self.ctx.session.query(PersonalLoan).filter_by(payslip_id=p.id).all()
        loan_lines = []
        for rep in repayments:
            loan = rep.loan
            if not loan:
                continue
            will_be_removed = loan in auto_loans and len(loan.repayments) == 1
            if will_be_removed:
                loan_lines.append(f"     −  \"{loan.contact_name}\" will be REMOVED entirely "
                                  f"(it only exists because of this payslip)")
            else:
                loan_lines.append(f"     −  \"{loan.contact_name}\" will have "
                                  f"{rep.amount:,.2f} un-repaid (reversed)")

        if repayments:
            loan_block = ("  •  its footprint in the Loans tab will be undone:\n" +
                          "\n".join(loan_lines) + "\n")
        else:
            loan_block = "  •  (no linked loan activity to undo)\n"

        # ── Preview: Bills impact ────────────────────────────────────────
        bill_txs = (self.ctx.session.query(Transaction)
                   .filter_by(payslip_id=p.id).filter(Transaction.bill_id.isnot(None)).all())
        affected_bill_ids = {tx.bill_id for tx in bill_txs}
        bill_lines = []
        for bid in affected_bill_ids:
            bill = self.ctx.session.query(Bill).get(bid)
            if not bill:
                continue
            this_payslip_payment_ids = {tx.id for tx in bill_txs if tx.bill_id == bid}
            total_payments = self.ctx.session.query(Transaction).filter_by(bill_id=bid).count()
            other_payments = total_payments - len(this_payslip_payment_ids)
            if bill.payslip_id == p.id and other_payments == 0:
                bill_lines.append(f"     −  \"{bill.name}\" will be REMOVED entirely "
                                  f"(it only exists because of this payslip)")
            else:
                bill_lines.append(f"     −  \"{bill.name}\" payment will be reversed "
                                  "(due date reverts to its previous schedule)")

        if bill_lines:
            bill_block = ("  •  its footprint in the Bills tab will be undone:\n" +
                          "\n".join(bill_lines) + "\n")
        else:
            bill_block = "  •  (no linked bill activity to undo)\n"

        msg = (
            f"Deleting this payslip{period} will permanently remove "
            "EVERYTHING it created:\n\n"
            f"  •  the payslip record and every line item on it\n"
            f"  •  all {n} transaction(s) it generated — salary income, "
            "deductions, taxes, and bill payments\n"
            "     (your account balance will change accordingly)\n"
            "  •  the tax records in the Taxes tab that came from it\n"
            f"{loan_block}"
            f"{bill_block}"
            "  •  the attached payslip PDF\n\n"
            "This cannot be undone. Delete everything related to this payslip?"
        )
        if not messagebox.askyesno("⚠️ Delete Payslip & Everything It Created",
                                    msg, icon="warning", parent=self):
            return
        try:
            result = self.ctx.payslip.delete_cascade(p)
        except Exception as e:
            messagebox.showerror("Delete Failed", str(e), parent=self)
            return
        parts = [f"{result['transactions']} transaction(s)"]
        if result["repayments_reversed"]:
            parts.append(f"{result['repayments_reversed']} loan repayment(s) reversed")
        if result["loans_removed"]:
            parts.append(f"{result['loans_removed']} loan(s) removed")
        if result.get("bills_removed"):
            parts.append(f"{result['bills_removed']} bill(s) removed")
        messagebox.showinfo("Payslip Deleted",
                            "Payslip and " + ", ".join(parts) + " were removed.",
                            parent=self)
        self.app.refresh()
        self._rebuild()

    # ── Computed summary modal (YTD + cashflow report share this) ─────────

    def _show_summary(self, title, summary, exportable=False):
        modal = Modal(self, title, width=640, height=760)
        t = summary["totals"]
        code = summary["currency_code"]
        cur = self.ctx.currency.get_by_code(code) if code else None
        sym = cur.symbol if cur else ""

        period_txt = ""
        if summary["start"] or summary["end"]:
            s = summary["start"].strftime("%d %b %Y") if summary["start"] else "start"
            e = summary["end"].strftime("%d %b %Y") if summary["end"] else "today"
            period_txt = f"{s} – {e}  •  "
        ctk.CTkLabel(modal.body,
                     text=f"{period_txt}{len(summary['payslips'])} payslip(s)  •  "
                          "click any value for the detail behind it",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     anchor="w").pack(fill="x", pady=(0, 8))

        totals_card = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=10)
        totals_card.pack(fill="x", pady=(0, 6))
        for label, val, col in (
                ("Taxable Income",     t["taxable"],     theme.GREEN),
                ("Non-Taxable Income", t["non_taxable"], theme.ACCENT),
                ("Total Deductions",   -t["deductions"], theme.RED),
                ("NET (earnings − deductions)", t["net"], theme.GOLD)):
            row = ctk.CTkFrame(totals_card, fg_color="transparent")
            row.pack(fill="x", padx=12, pady=2)
            bold = "bold" if label.startswith("NET") else "normal"
            ctk.CTkLabel(row, text=label, font=("Segoe UI", 12, bold),
                         text_color=theme.TEXT_PRI, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=f"{sym}{val:,.2f}", font=("Segoe UI", 12, "bold"),
                         text_color=col).pack(side="right")
        ctk.CTkLabel(totals_card, text="", height=4).pack()

        for section, s_title in SECTION_TITLES.items():
            buckets = summary["sections"][section]
            if not buckets:
                continue
            ctk.CTkLabel(modal.body, text=s_title, font=("Segoe UI", 13, "bold"),
                         text_color=theme.ACCENT).pack(anchor="w", pady=(10, 4))
            card = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
            card.pack(fill="x", pady=(0, 4))
            for label, b in sorted(buckets.items(), key=lambda kv: kv[1]["total"], reverse=True):
                row = ctk.CTkFrame(card, fg_color="transparent")
                row.pack(fill="x", padx=8, pady=1)
                ctk.CTkButton(row, text=f"{label}   ({len(b['items'])}×)",
                              fg_color="transparent", hover_color=theme.BG_SELECTED,
                              text_color=theme.TEXT_PRI, font=("Segoe UI", 12), anchor="w",
                              command=lambda l=label, bb=b, m=modal: self._show_label_detail(m, l, bb)
                              ).pack(side="left", fill="x", expand=True)
                ctk.CTkLabel(row, text=f"{sym}{b['total']:,.2f}", font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="right", padx=6)
            total = sum(b["total"] for b in buckets.values())
            trow = ctk.CTkFrame(card, fg_color="transparent")
            trow.pack(fill="x", padx=14, pady=(2, 6))
            ctk.CTkLabel(trow, text="Total", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_SEC, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(trow, text=f"{sym}{total:,.2f}", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_SEC).pack(side="right")

        if exportable:
            ctk.CTkButton(modal.footer, text="📄 Export PDF", width=130, height=36,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.ACCENT, font=("Segoe UI", 12),
                          command=lambda: self._export(summary, "pdf")
                          ).pack(side="left", padx=(16, 6), pady=12)
            ctk.CTkButton(modal.footer, text="📊 Export Excel", width=130, height=36,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.GREEN, font=("Segoe UI", 12),
                          command=lambda: self._export(summary, "xlsx")
                          ).pack(side="left", padx=6, pady=12)

        ctk.CTkButton(modal.footer, text="Close", command=modal.destroy,
                      fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
                      text_color="#fff", font=("Segoe UI", 13, "bold"),
                      height=36, width=120).pack(side="right", padx=16, pady=12)

    def _show_label_detail(self, parent_modal, label, bucket):
        modal = Modal(parent_modal, f"Detail — {label}", width=520, height=520)
        for p, li in sorted(bucket["items"],
                            key=lambda pi: (pi[0].period_end or pi[0].period_start
                                            or pi[0].created_at), reverse=True):
            period = (p.period_end or p.period_start)
            row = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
            row.pack(fill="x", pady=3)
            ctk.CTkLabel(row, text=period.strftime("%b %Y") if period else "—",
                         font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_PRI,
                         width=80, anchor="w").pack(side="left", padx=(10, 4), pady=8)
            ctk.CTkLabel(row, text=p.company or "—", font=("Segoe UI", 11),
                         text_color=theme.TEXT_SEC, anchor="w").pack(side="left", fill="x", expand=True)
            ctk.CTkLabel(row, text=f"{li.amount:,.2f} {p.currency_code}",
                         font=("Segoe UI", 12), text_color=theme.TEXT_PRI).pack(side="right", padx=8)
            ctk.CTkButton(row, text="View", width=56, height=26,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=lambda p=p: show_payslip_viewer(modal, p, ctx=self.ctx, app=self.app)
                          ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(modal.footer, text="Close", command=modal.destroy,
                      fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
                      text_color="#fff", font=("Segoe UI", 13, "bold"),
                      height=36, width=120).pack(side="right", padx=16, pady=12)

    # ── Cashflow report ───────────────────────────────────────────────────

    def _cashflow_report(self):
        modal = Modal(self, "Payslip Cashflow — Choose Period", width=420, height=330)
        now = datetime.now()
        start_e = modal.add_field("From (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
        start_e.insert(0, f"{now.year}-01-01")
        end_e = modal.add_field("To (YYYY-MM-DD)", lambda p: make_entry(p, "YYYY-MM-DD"))
        end_e.insert(0, now.strftime("%Y-%m-%d"))
        ctk.CTkLabel(modal.body,
                     text="Leave either field empty for an open-ended range.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     anchor="w").pack(fill="x", pady=(4, 0))

        def go():
            try:
                s_txt, e_txt = start_e.get().strip(), end_e.get().strip()
                start = datetime.strptime(s_txt, "%Y-%m-%d") if s_txt else None
                end = (datetime.strptime(e_txt, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
                       if e_txt else None)
            except ValueError:
                messagebox.showerror("Invalid Date", "Use the format YYYY-MM-DD.", parent=modal)
                return
            summary = self.ctx.payslip.summarize_period(start, end)
            modal.destroy()
            self._show_summary("Payslip Cashflow Report", summary, exportable=True)

        modal.add_buttons("View Report", go)

    def _export(self, summary, fmt):
        from src.services.report_generators import PayslipCashflowReport
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        if fmt == "pdf":
            ft, ext, name = [("PDF files", "*.pdf")], ".pdf", f"WealthMap_PayslipCashflow_{ts}.pdf"
        else:
            ft, ext, name = [("Excel files", "*.xlsx")], ".xlsx", f"WealthMap_PayslipCashflow_{ts}.xlsx"
        path = filedialog.asksaveasfilename(
            title="Save report as…", defaultextension=ext,
            initialfile=name, filetypes=ft + [("All files", "*.*")])
        if not path:
            return
        try:
            gen = PayslipCashflowReport()
            if fmt == "pdf":
                out = gen.generate(self.ctx, path,
                                   start_date=summary["start"], end_date=summary["end"])
            else:
                out = gen.generate_xlsx(self.ctx, path,
                                        start_date=summary["start"], end_date=summary["end"])
        except Exception as e:
            messagebox.showerror("Export Failed", str(e), parent=self)
            return
        if messagebox.askyesno("Report Ready", f"Saved to:\n{out}\n\nOpen it now?", parent=self):
            try:
                os.startfile(out)  # Windows
            except Exception:
                import webbrowser
                webbrowser.open(f"file://{out}")

    # ── Misc ──────────────────────────────────────────────────────────────

    def _view(self, payslip):
        show_payslip_viewer(self, payslip, ctx=self.ctx, app=self.app)

    def _import_payslip(self):
        open_payslip_import_dialog(self, self.ctx, on_done=lambda: (self.app.refresh(), self._rebuild()))

    def _generate_payslip(self):
        open_generate_payslip_dialog(self, self.ctx, on_done=lambda: (self.app.refresh(), self._rebuild()))

    def _rebuild(self):
        safe_rebuild(self, self._build)
