"""
WealthMap – Reports Panel
Central hub to generate any report with progress feedback.
"""

import os
import threading
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog, messagebox
import tkinter as tk
import customtkinter as ctk

from src.ui.widgets import (
    SectionHeader
)
from src.ui.theme import theme

# Report catalogue — (key, icon, label, description, report_type)
REPORTS = [
    # ── Overviews ──────────────────────────────────────────────────────────
    ("net_worth",   "💰", "Net Worth Report",
     "Complete financial position: accounts, portfolio, loans", "pdf"),
    ("annual",      "📅", "Annual Report",
     "Full-year income, expenses, portfolio, cash flow analysis", "pdf"),
    ("xlsx_export", "📊", "Full Data Export (Excel)",
     "All data across 6 sheets: accounts, transactions, portfolio, loans, rates", "xlsx"),

    # ── Module-specific ────────────────────────────────────────────────────
    ("transactions","↕",  "Transaction Report",
     "Monthly transaction ledger with category breakdown & charts", "pdf"),
    ("account_stmt","🏦", "Account Statement",
     "Single-account statement with income/expense analysis", "pdf"),
    ("portfolio",   "📈", "Portfolio Report",
     "Holdings, P&L, trade history, allocation charts", "pdf"),
    ("loans",       "💸", "Loans & Debts Report",
     "Inter-personal loans register with repayment history", "pdf"),
    ("receipts",    "🧾", "Receipts Register",
     "All receipts and attached file index", "pdf"),
    ("exchange",    "💱", "Exchange Rates Report",
     "All cached exchange rates and major pairs snapshot", "pdf"),
    ("fees_taxes",  "🧮", "Fees & Taxes Report",
     "Every fee and tax charged across transactions, loans & trades", "pdf"),
]


class ReportsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure((0, 1), weight=1)

        SectionHeader(scroll, "Reports", "Generate PDF & Excel reports for every module"
                      ).grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 20))

        # Quick-action row
        qa = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                          border_width=1, border_color=theme.BORDER)
        qa.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 24))
        ctk.CTkLabel(qa, text="⚡  Quick Actions",
                     font=("Segoe UI", 12, "bold"), text_color=theme.ACCENT).pack(anchor="w", padx=16, pady=(12, 4))
        btn_row = ctk.CTkFrame(qa, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 14))

        quick = [
            ("📅 Annual Report (this year)",  lambda: self._generate("annual")),
            ("💰 Net Worth Report",            lambda: self._generate("net_worth")),
            ("📊 Full Excel Export",           lambda: self._generate("xlsx_export")),
            ("↕ This Month's Transactions",    lambda: self._generate("transactions")),
        ]
        for text, cmd in quick:
            ctk.CTkButton(btn_row, text=text, height=34, font=("Segoe UI", 12),
                          fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                          command=cmd).pack(side="left", padx=(0, 8))

        # Report cards grid
        for i, (key, icon, label, desc, rtype) in enumerate(REPORTS):
            row_i, col_i = divmod(i, 2)
            card = self._make_card(scroll, key, icon, label, desc, rtype)
            card.grid(row=row_i + 2, column=col_i,
                      padx=(0 if col_i == 0 else 8, 0), pady=(0, 12), sticky="nsew")

        # Progress / log area
        log_frame = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=10,
                                 border_width=1, border_color=theme.BORDER)
        log_frame.grid(row=len(REPORTS)//2 + 4, column=0, columnspan=2,
                       sticky="ew", pady=(12, 0))
        ctk.CTkLabel(log_frame, text="Generation Log",
                     font=("Segoe UI", 11, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=14, pady=(10, 4))
        self._log = ctk.CTkTextbox(log_frame, height=110, font=("Consolas", 10),
                                   fg_color=theme.BG_DARK, text_color=theme.GREEN)
        self._log.pack(fill="x", padx=14, pady=(0, 12))
        self._log.configure(state="disabled")
        self._progress = ctk.CTkProgressBar(log_frame, height=6,
                                            fg_color=theme.BORDER, progress_color=theme.ACCENT)
        self._progress.set(0)
        self._progress.pack(fill="x", padx=14, pady=(0, 12))

    def _make_card(self, parent, key, icon, label, desc, rtype):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=12,
                            border_width=1, border_color=theme.BORDER)
        card.grid_columnconfigure(0, weight=1)

        # Type badge
        badge_color = theme.ACCENT if rtype == "pdf" else theme.GREEN
        badge_text  = "PDF" if rtype == "pdf" else "XLSX"
        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=14, pady=(12, 0))
        ctk.CTkLabel(top, text=f"{icon}  {label}",
                     font=("Segoe UI", 13, "bold"), text_color=theme.TEXT_PRI).pack(side="left")
        ctk.CTkLabel(top, text=badge_text,
                     font=("Segoe UI", 9, "bold"), text_color=badge_color).pack(side="right")

        ctk.CTkLabel(card, text=desc, font=("Segoe UI", 11),
                     text_color=theme.TEXT_SEC, wraplength=300, anchor="w",
                     justify="left").pack(anchor="w", padx=14, pady=(4, 0))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=14, pady=(8, 14))

        ctk.CTkButton(btn_row, text="Generate & Save",
                      height=30, font=("Segoe UI", 11),
                      fg_color=badge_color, hover_color="#1C6FBF" if rtype == "pdf" else "#2D8A3E",
                      text_color="#fff",
                      command=lambda k=key: self._generate(k)).pack(side="left")

        ctk.CTkButton(btn_row, text="Generate & Open",
                      height=30, font=("Segoe UI", 11),
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC,
                      command=lambda k=key: self._generate(k, auto_open=True)).pack(side="left", padx=6)
        return card

    # ── Generation Logic ───────────────────────────────────────────────────────

    def _generate(self, key: str, auto_open: bool = False):
        """Ask for options if needed, then dispatch generation in a thread."""
        from src.services.report_generators import (
            NetWorthReport, AccountStatementReport, TransactionReport,
            PortfolioReport, LoansReport, ReceiptsReport,
            ExchangeRatesReport, AnnualReport, XLSXExporter, FeesTaxesReport
        )

        # Determine default filename & extension
        ts    = datetime.now().strftime("%Y%m%d_%H%M%S")
        is_xl = key == "xlsx_export"
        ext   = ".xlsx" if is_xl else ".pdf"
        default_names = {
            "net_worth":   f"WealthMap_NetWorth_{ts}.pdf",
            "annual":      f"WealthMap_Annual_{datetime.now().year}_{ts}.pdf",
            "transactions":f"WealthMap_Transactions_{ts}.pdf",
            "account_stmt":f"WealthMap_Statement_{ts}.pdf",
            "portfolio":   f"WealthMap_Portfolio_{ts}.pdf",
            "loans":       f"WealthMap_Loans_{ts}.pdf",
            "receipts":    f"WealthMap_Receipts_{ts}.pdf",
            "exchange":    f"WealthMap_ExchangeRates_{ts}.pdf",
            "fees_taxes":  f"WealthMap_FeesTaxes_{ts}.pdf",
            "xlsx_export": f"WealthMap_Export_{ts}.xlsx",
        }

        # Extra options for some reports
        extra_kwargs = {}

        if key == "annual":
            year = self._ask_year()
            if year is None:
                return
            extra_kwargs["year"] = year

        elif key == "transactions":
            year, month = self._ask_year_month()
            if year is None:
                return
            extra_kwargs["year"] = year
            extra_kwargs["month"] = month

        elif key == "account_stmt":
            acc_id = self._ask_account()
            if acc_id is None:
                return
            extra_kwargs["account_id"] = acc_id

        # Ask save location
        ft = [("PDF files", "*.pdf")] if not is_xl else [("Excel files", "*.xlsx")]
        path = filedialog.asksaveasfilename(
            title="Save report as…",
            defaultextension=ext,
            initialfile=default_names[key],
            filetypes=ft + [("All files", "*.*")],
        )
        if not path:
            return

        self._log_append(f"[{datetime.now().strftime('%H:%M:%S')}] Starting: {default_names[key]}")
        self._progress.set(0.1)
        self._progress.configure(progress_color=theme.ACCENT)

        def run():
            try:
                generators = {
                    "net_worth":   lambda p: NetWorthReport().generate(self.ctx, p),
                    "annual":      lambda p: AnnualReport().generate(self.ctx, p, **extra_kwargs),
                    "transactions":lambda p: TransactionReport().generate(self.ctx, p, **extra_kwargs),
                    "account_stmt":lambda p: AccountStatementReport().generate(
                                       self.ctx, extra_kwargs["account_id"], p),
                    "portfolio":   lambda p: PortfolioReport().generate(self.ctx, p),
                    "loans":       lambda p: LoansReport().generate(self.ctx, p),
                    "receipts":    lambda p: ReceiptsReport().generate(self.ctx, p),
                    "exchange":    lambda p: ExchangeRatesReport().generate(self.ctx, p),
                    "fees_taxes":  lambda p: FeesTaxesReport().generate(self.ctx, p),
                    "xlsx_export": lambda p: XLSXExporter().generate(self.ctx, p),
                }
                self.after(0, lambda: self._progress.set(0.5))
                out = generators[key](path)
                self.after(0, lambda: self._on_success(out, auto_open))
            except Exception as e:
                import traceback
                tb = traceback.format_exc()
                msg = str(e)
                self.after(0, lambda: self._on_error(msg, tb))

        threading.Thread(target=run, daemon=True).start()

    def _on_success(self, path: str, auto_open: bool):
        self._progress.set(1.0)
        self._progress.configure(progress_color=theme.GREEN)
        size_kb = Path(path).stat().st_size // 1024
        self._log_append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅  Saved: {Path(path).name}  ({size_kb} KB)")
        if auto_open:
            self._open_file(path)
        else:
            if messagebox.askyesno("Report Ready",
                                   f"Report saved to:\n{path}\n\nOpen it now?"):
                self._open_file(path)
        self.after(3000, lambda: self._progress.set(0))

    def _on_error(self, msg: str, tb: str):
        self._progress.set(0)
        self._progress.configure(progress_color=theme.RED)
        self._log_append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌  Error: {msg}")
        messagebox.showerror("Report Error",
                             f"Failed to generate report:\n\n{msg}\n\nCheck the log for details.")
        print(tb)

    def _log_append(self, text: str):
        self._log.configure(state="normal")
        self._log.insert("end", text + "\n")
        self._log.see("end")
        self._log.configure(state="disabled")

    def _open_file(self, path: str):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)
            elif sys.platform == "darwin":
                subprocess.run(["open", path])
            else:
                subprocess.run(["xdg-open", path])
        except Exception as e:
            messagebox.showinfo("Open File", f"File saved at:\n{path}")

    # ── Option Dialogs ─────────────────────────────────────────────────────────

    def _ask_year(self) -> int:
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Year")
        dialog.geometry("280x160")
        dialog.configure(fg_color=theme.BG_DARK)
        dialog.grab_set()
        dialog.lift()

        years = [str(y) for y in range(datetime.now().year, datetime.now().year - 6, -1)]
        result = {"year": None}

        ctk.CTkLabel(dialog, text="Report Year:", font=("Segoe UI", 12), text_color=theme.TEXT_PRI).pack(pady=(20, 6))
        combo = ctk.CTkComboBox(dialog, values=years,
                                fg_color=theme.BG_CARD, border_color=theme.BORDER,
                                text_color=theme.TEXT_PRI, font=("Segoe UI", 12), height=36)
        combo.set(str(datetime.now().year))
        combo.pack(pady=6)

        def ok():
            result["year"] = int(combo.get())
            dialog.destroy()

        ctk.CTkButton(dialog, text="Generate", fg_color=theme.ACCENT, hover_color="#1C6FBF",
                      text_color="#fff", font=("Segoe UI", 12), height=34,
                      command=ok).pack(pady=8)
        dialog.wait_window()
        return result["year"]

    def _ask_year_month(self):
        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Period")
        dialog.geometry("320x180")
        dialog.configure(fg_color=theme.BG_DARK)
        dialog.grab_set()
        dialog.lift()

        now = datetime.now()
        years  = [str(y) for y in range(now.year, now.year - 4, -1)]
        months = [datetime(2000, m, 1).strftime("%B") for m in range(1, 13)]
        result = {"year": None, "month": None}

        row = ctk.CTkFrame(dialog, fg_color="transparent")
        row.pack(pady=(20, 8))
        ctk.CTkLabel(row, text="Year:", text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(side="left", padx=8)
        yr_c = ctk.CTkComboBox(row, values=years, width=100,
                               fg_color=theme.BG_CARD, border_color=theme.BORDER,
                               text_color=theme.TEXT_PRI, font=("Segoe UI", 12), height=34)
        yr_c.set(str(now.year))
        yr_c.pack(side="left")

        row2 = ctk.CTkFrame(dialog, fg_color="transparent")
        row2.pack(pady=4)
        ctk.CTkLabel(row2, text="Month:", text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(side="left", padx=8)
        mo_c = ctk.CTkComboBox(row2, values=months, width=140,
                               fg_color=theme.BG_CARD, border_color=theme.BORDER,
                               text_color=theme.TEXT_PRI, font=("Segoe UI", 12), height=34)
        mo_c.set(now.strftime("%B"))
        mo_c.pack(side="left")

        def ok():
            result["year"]  = int(yr_c.get())
            result["month"] = months.index(mo_c.get()) + 1
            dialog.destroy()

        ctk.CTkButton(dialog, text="Generate", fg_color=theme.ACCENT, hover_color="#1C6FBF",
                      text_color="#fff", font=("Segoe UI", 12), height=34,
                      command=ok).pack(pady=10)
        dialog.wait_window()
        return result["year"], result["month"]

    def _ask_account(self):
        accounts = self.ctx.account.get_all()
        if not accounts:
            messagebox.showinfo("No Accounts", "No accounts found.")
            return None

        dialog = ctk.CTkToplevel(self)
        dialog.title("Select Account")
        dialog.geometry("340x160")
        dialog.configure(fg_color=theme.BG_DARK)
        dialog.grab_set()
        dialog.lift()

        result = {"id": None}
        names  = [a.name for a in accounts]

        ctk.CTkLabel(dialog, text="Account:", text_color=theme.TEXT_PRI,
                     font=("Segoe UI", 12)).pack(pady=(20, 6))
        combo = ctk.CTkComboBox(dialog, values=names,
                                fg_color=theme.BG_CARD, border_color=theme.BORDER,
                                text_color=theme.TEXT_PRI, font=("Segoe UI", 12), height=36, width=280)
        combo.set(names[0])
        combo.pack(pady=6)

        def ok():
            acc = next((a for a in accounts if a.name == combo.get()), None)
            result["id"] = acc.id if acc else None
            dialog.destroy()

        ctk.CTkButton(dialog, text="Generate", fg_color=theme.ACCENT, hover_color="#1C6FBF",
                      text_color="#fff", font=("Segoe UI", 12), height=34,
                      command=ok).pack(pady=8)
        dialog.wait_window()
        return result["id"]
