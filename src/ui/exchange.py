"""
WealthMap – Exchange Rates Panel
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from src.ui.widgets import (
    SectionHeader, StatCard, Modal,
    make_entry, fmt_money, attach_currency_tooltip, CurrencySearchEntry
)
from src.ui.theme import theme


class ExchangePanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        SectionHeader(scroll, "Exchange Rates",
                      "Live & manual currency rates",
                      "Refresh Rates", self._fetch_rates
                      ).grid(row=0, column=0, sticky="ew", pady=(0, 20))

        # Converter tool
        conv_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                 border_width=1, border_color=theme.BORDER)
        conv_card.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(conv_card, text="CURRENCY CONVERTER",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))

        conv_body = ctk.CTkFrame(conv_card, fg_color="transparent")
        conv_body.pack(fill="x", padx=16, pady=(0, 16))

        self._conv_amt  = make_entry(conv_body, "Amount", width=140)
        self._conv_from = CurrencySearchEntry(conv_body, self.ctx, width=100, initial_code="USD")
        self._conv_to   = CurrencySearchEntry(conv_body, self.ctx, width=100, initial_code="EUR")
        self._conv_result = ctk.CTkLabel(conv_body, text="", font=("Segoe UI", 20, "bold"),
                                          text_color=theme.GOLD, width=200)

        self._conv_amt.pack(side="left", padx=(0, 8))
        self._conv_from.pack(side="left", padx=(0, 8))
        attach_currency_tooltip(self._conv_from, self.ctx)
        ctk.CTkLabel(conv_body, text="→", font=("Segoe UI", 16), text_color=theme.TEXT_SEC).pack(side="left", padx=8)
        self._conv_to.pack(side="left", padx=(0, 8))
        attach_currency_tooltip(self._conv_to, self.ctx)
        ctk.CTkButton(conv_body, text="Convert", width=90, height=36,
                      fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                      font=("Segoe UI", 12), command=self._convert).pack(side="left", padx=8)
        self._conv_result.pack(side="left", padx=16)

        # Manual rate setter
        manual_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                   border_width=1, border_color=theme.BORDER)
        manual_card.grid(row=2, column=0, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(manual_card, text="SET MANUAL RATE",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))

        man_body = ctk.CTkFrame(manual_card, fg_color="transparent")
        man_body.pack(fill="x", padx=16, pady=(0, 16))
        self._man_from = CurrencySearchEntry(man_body, self.ctx, width=90, initial_code="USD")
        self._man_to   = CurrencySearchEntry(man_body, self.ctx, width=90, initial_code="GBP")
        self._man_rate = make_entry(man_body, "Rate", width=120)

        self._man_from.pack(side="left", padx=(0, 8))
        attach_currency_tooltip(self._man_from, self.ctx)
        ctk.CTkLabel(man_body, text="→", text_color=theme.TEXT_SEC, font=("Segoe UI", 14)).pack(side="left", padx=4)
        self._man_to.pack(side="left", padx=(0, 8))
        attach_currency_tooltip(self._man_to, self.ctx)
        ctk.CTkLabel(man_body, text="=", text_color=theme.TEXT_SEC, font=("Segoe UI", 14)).pack(side="left", padx=4)
        self._man_rate.pack(side="left", padx=(0, 8))
        ctk.CTkButton(man_body, text="Set Rate", width=90, height=36,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 12),
                      command=self._set_manual_rate).pack(side="left")

        # Rate table
        ctk.CTkLabel(scroll, text="CACHED RATES (USD BASE)",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC
                     ).grid(row=3, column=0, sticky="w", pady=(0, 6))

        self._rate_frame = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                        border_width=1, border_color=theme.BORDER)
        self._rate_frame.grid(row=4, column=0, sticky="ew")
        self._populate_rate_table()

    def _populate_rate_table(self):
        for w in self._rate_frame.winfo_children():
            w.destroy()

        from src.models.database import ExchangeRate
        base_cur = self.ctx.currency.get_by_code("USD")
        if not base_cur:
            return
        rates = (self.ctx.session.query(ExchangeRate)
                 .filter_by(base_currency_id=base_cur.id)
                 .order_by(ExchangeRate.target_currency_id)
                 .all())

        col_count = 4
        for i, r in enumerate(rates):
            row_i, col_i = divmod(i, col_count)
            cell = ctk.CTkFrame(self._rate_frame, fg_color="transparent")
            cell.grid(row=row_i, column=col_i, padx=16, pady=6, sticky="w")
            ctk.CTkLabel(cell, text=f"USD → {r.target_currency.code}",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w")
            ctk.CTkLabel(cell, text=f"{r.rate:,.4f}",
                         font=("Segoe UI", 13, "bold"), text_color=theme.TEXT_PRI).pack(anchor="w")
            age = ""
            if r.fetched_at:
                from datetime import datetime, timezone
                secs = (datetime.now(timezone.utc) - r.fetched_at.replace(tzinfo=timezone.utc)).total_seconds()
                age = f"{r.source} · {int(secs // 60)}m ago"
            ctk.CTkLabel(cell, text=age, font=("Segoe UI", 9), text_color=theme.TEXT_SEC).pack(anchor="w")

        if not rates:
            ctk.CTkLabel(self._rate_frame,
                         text="No rates cached yet. Click 'Refresh Rates' to fetch.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=20)

    def _convert(self):
        try:
            self._conv_from.resolve()
            self._conv_to.resolve()
            amt  = float(self._conv_amt.get().replace(",", ""))
            from_code = self._conv_from.get()
            to_code   = self._conv_to.get()
            result = self.ctx.currency.convert(amt, from_code, to_code)
            if result is None:
                self._conv_result.configure(text="No rate available", text_color=theme.RED)
            else:
                to_cur = self.ctx.currency.get_by_code(to_code)
                sym = to_cur.symbol if to_cur else ""
                self._conv_result.configure(
                    text=f"{sym}{result:,.4f} {to_code}", text_color=theme.GOLD)
        except Exception as e:
            self._conv_result.configure(text=str(e), text_color=theme.RED)

    def _set_manual_rate(self):
        try:
            self._man_from.resolve()
            self._man_to.resolve()
            rate = float(self._man_rate.get())
            self.ctx.currency.set_manual_rate(self._man_from.get(), self._man_to.get(), rate)
            messagebox.showinfo("Rate Set", "Manual rate saved successfully.")
            self._populate_rate_table()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def _fetch_rates(self):
        self.ctx.fetch_rates_background()
        messagebox.showinfo("Fetching", "Rates are being fetched in the background. Refresh the page in a moment.")
