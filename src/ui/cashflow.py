"""
WealthMap – Cash Flow Command Center (Business profiles)
A CEO-focused live overview: cash position, burn rate, runway, revenue,
margin, AR/AP, department cash flow, revenue vs expense trend, and top
expense categories.
"""

import tkinter as tk
import customtkinter as ctk
from datetime import datetime, timezone

from src.models.database import AccountType
from src.ui.widgets import SectionHeader, StatCard, fmt_money
from src.ui.theme import theme

LIQUID_TYPES = {AccountType.BANK, AccountType.SAVINGS, AccountType.WALLET, AccountType.CASH}


class CashFlowPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._canvases = []
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure((0, 1, 2, 3), weight=1)

        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        SectionHeader(scroll, "🚀 Cash Flow Command Center",
                      f"{self.ctx.profile.get('name', 'Business')} — live cash position, "
                      "burn rate, and runway"
                      ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 16))

        # ── KPI computations ────────────────────────────────────────────────
        accounts = self.ctx.account.get_all()
        cash_position = 0.0
        for a in accounts:
            if a.account_type in LIQUID_TYPES:
                bal = self.ctx.account.get_balance(a)
                bal_base = self.ctx.account.get_balance_in_base(a, base)
                cash_position += bal_base if bal_base is not None else bal

        trailing3 = self.ctx.transaction.trailing_months_cash_flow(base, 3)
        avg_income = sum(m["income"] for m in trailing3) / max(1, len(trailing3))
        avg_expense = sum(m["expense"] for m in trailing3) / max(1, len(trailing3))
        burn = avg_expense - avg_income  # positive = burning cash, negative = profitable
        runway = (cash_position / burn) if burn > 0 else None

        now = datetime.now(timezone.utc)
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        mtd = self.ctx.transaction.cash_flow_excluding_transfers(base, month_start, None)
        revenue_mtd = mtd["income"]
        expense_mtd = mtd["expenses"]
        margin = ((revenue_mtd - expense_mtd) / revenue_mtd * 100) if revenue_mtd else None

        loan_summary = self.ctx.loan.summary(base)
        ar, ap = loan_summary["owed_to_me"], loan_summary["i_owe"]

        # ── KPI cards ─────────────────────────────────────────────────────
        StatCard(scroll, "Cash Position", fmt_money(cash_position, sym),
                 "across liquid accounts", theme.GREEN, "💰"
                 ).grid(row=1, column=0, sticky="ew", padx=6, pady=6)

        burn_color = theme.RED if burn > 0 else theme.GREEN
        burn_sub = "avg net outflow / month (last 3 mo)" if burn > 0 else "profitable — net inflow / month"
        StatCard(scroll, "Monthly Burn", fmt_money(abs(burn), sym), burn_sub, burn_color, "🔥"
                 ).grid(row=1, column=1, sticky="ew", padx=6, pady=6)

        if runway is None:
            runway_text, runway_color = "∞", theme.GREEN
        else:
            runway_text = f"{runway:.1f} mo"
            runway_color = theme.RED if runway < 3 else (theme.GOLD if runway < 6 else theme.ACCENT)
        StatCard(scroll, "Runway", runway_text, "at current burn rate", runway_color, "🛟"
                 ).grid(row=1, column=2, sticky="ew", padx=6, pady=6)

        StatCard(scroll, "Revenue (MTD)", fmt_money(revenue_mtd, sym), "this month so far",
                 theme.GREEN, "📈", on_click=lambda: self.app.navigate("analytics")
                 ).grid(row=1, column=3, sticky="ew", padx=6, pady=6)

        margin_text = "—" if margin is None else f"{margin:+.1f}%"
        margin_color = theme.TEXT_SEC if margin is None else (theme.GREEN if margin >= 0 else theme.RED)
        StatCard(scroll, "Net Margin (MTD)", margin_text, "profit ÷ revenue", margin_color, "📊"
                 ).grid(row=2, column=0, sticky="ew", padx=6, pady=6)

        StatCard(scroll, "Receivables (AR)", fmt_money(ar, sym), "owed to you by clients",
                 theme.ACCENT, "📥", on_click=lambda: self.app.navigate("loans")
                 ).grid(row=2, column=1, sticky="ew", padx=6, pady=6)

        StatCard(scroll, "Payables (AP)", fmt_money(ap, sym), "you owe vendors",
                 theme.GOLD, "📤", on_click=lambda: self.app.navigate("loans")
                 ).grid(row=2, column=2, sticky="ew", padx=6, pady=6)

        net_ar_ap = ar - ap
        StatCard(scroll, "Net AR − AP", fmt_money(net_ar_ap, sym), "receivables minus payables",
                 theme.GREEN if net_ar_ap >= 0 else theme.RED, "⚖️"
                 ).grid(row=2, column=3, sticky="ew", padx=6, pady=6)

        # ── Revenue vs Expenses trend ───────────────────────────────────────
        SectionHeader(scroll, "Revenue vs Expenses (last 6 months)",
                      "Excludes internal transfers between your own accounts"
                      ).grid(row=3, column=0, columnspan=4, sticky="ew", pady=(20, 8))
        trend = self.ctx.transaction.trailing_months_cash_flow(base, 6)
        trend_frame = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                   border_width=1, border_color=theme.BORDER)
        trend_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 16))
        self._draw_bar_chart(trend_frame, [(m["income"], m["expense"]) for m in trend],
                             [m["label"] for m in trend], sym)

        # ── Cash flow by department ─────────────────────────────────────────
        SectionHeader(scroll, "Net Cash Flow by Department (this month)"
                      ).grid(row=5, column=0, columnspan=4, sticky="ew", pady=(8, 8))
        dept_cf = self.ctx.department.cash_flow_summary(base, months=1)
        dept_frame = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                  border_width=1, border_color=theme.BORDER)
        dept_frame.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 16))
        if any(d["income"] or d["expense"] for d in dept_cf):
            self._draw_dept_chart(dept_frame, dept_cf, sym)
        else:
            ctk.CTkLabel(dept_frame, text="No transactions yet this month.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(padx=16, pady=24)

        # ── Top expense categories ──────────────────────────────────────────
        SectionHeader(scroll, "Top Expense Categories (this month)"
                      ).grid(row=7, column=0, columnspan=4, sticky="ew", pady=(8, 8))
        cat_frame = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                 border_width=1, border_color=theme.BORDER)
        cat_frame.grid(row=8, column=0, columnspan=4, sticky="ew", pady=(0, 16))
        cats = sorted(mtd["by_category"].items(), key=lambda x: -x[1])[:8]
        if cats:
            total_exp = sum(c[1] for c in cats) or 1
            ctk.CTkLabel(cat_frame, text="", height=4).pack()
            for name, amt in cats:
                row = ctk.CTkFrame(cat_frame, fg_color="transparent")
                row.pack(fill="x", padx=16, pady=4)
                ctk.CTkLabel(row, text=name, font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
                             width=180, anchor="w").pack(side="left")
                bar_bg = ctk.CTkFrame(row, fg_color=theme.BG_HOVER, height=14, corner_radius=4)
                bar_bg.pack(side="left", fill="x", expand=True, padx=8)
                frac = amt / total_exp
                ctk.CTkFrame(bar_bg, fg_color=theme.GOLD, height=14, corner_radius=4
                             ).place(relx=0, rely=0, relwidth=max(0.01, frac), relheight=1)
                ctk.CTkLabel(row, text=fmt_money(amt, sym), font=("Segoe UI", 12, "bold"),
                             text_color=theme.TEXT_PRI, width=100, anchor="e").pack(side="left")
            ctk.CTkLabel(cat_frame, text="", height=8).pack()
        else:
            ctk.CTkLabel(cat_frame, text="No expenses recorded yet this month.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(padx=16, pady=24)

    # ── Charts (Canvas-based, theme-aware) ──────────────────────────────────

    def _draw_bar_chart(self, parent, pairs, labels, sym):
        canvas = tk.Canvas(parent, height=220, bg=theme.BG_CARD, highlightthickness=0)
        canvas.pack(fill="x", padx=16, pady=12)
        self._canvases.append(canvas)

        def render(event=None):
            canvas.delete("all")
            w = canvas.winfo_width() or 700
            h = 220
            pad_l, pad_r, pad_t, pad_b = 60, 10, 10, 30
            plot_w = w - pad_l - pad_r
            plot_h = h - pad_t - pad_b

            vmax = max([max(inc, exp) for inc, exp in pairs] + [1])
            n = len(pairs)
            group_w = plot_w / max(1, n)
            bar_w = group_w * 0.32

            for frac in (0, 0.5, 1.0):
                gy = pad_t + plot_h - frac * plot_h
                canvas.create_line(pad_l, gy, w - pad_r, gy, fill=theme.BORDER, dash=(2, 3))
                canvas.create_text(pad_l - 6, gy, text=f"{sym}{vmax*frac:,.0f}", fill=theme.TEXT_SEC,
                                   anchor="e", font=("Segoe UI", 9))

            for i, (inc, exp) in enumerate(pairs):
                cx = pad_l + i * group_w + group_w / 2
                inc_h = (inc / vmax) * plot_h
                exp_h = (exp / vmax) * plot_h
                canvas.create_rectangle(cx - bar_w - 2, pad_t + plot_h - inc_h,
                                        cx - 2, pad_t + plot_h, fill=theme.GREEN, outline="")
                canvas.create_rectangle(cx + 2, pad_t + plot_h - exp_h,
                                        cx + 2 + bar_w, pad_t + plot_h, fill=theme.RED, outline="")
                canvas.create_text(cx, h - 10, text=labels[i], fill=theme.TEXT_SEC, font=("Segoe UI", 8))

            canvas.create_rectangle(w - 150, 8, w - 138, 18, fill=theme.GREEN, outline="")
            canvas.create_text(w - 132, 13, text="Revenue", fill=theme.TEXT_SEC, anchor="w", font=("Segoe UI", 9))
            canvas.create_rectangle(w - 80, 8, w - 68, 18, fill=theme.RED, outline="")
            canvas.create_text(w - 62, 13, text="Expenses", fill=theme.TEXT_SEC, anchor="w", font=("Segoe UI", 9))

        canvas.bind("<Configure>", render)
        self.after(50, render)

    def _draw_dept_chart(self, parent, dept_cf, sym):
        row_h = 40
        height = row_h * len(dept_cf) + 20
        canvas = tk.Canvas(parent, height=height, bg=theme.BG_CARD, highlightthickness=0)
        canvas.pack(fill="x", padx=16, pady=12)
        self._canvases.append(canvas)

        def render(event=None):
            canvas.delete("all")
            w = canvas.winfo_width() or 700
            label_w = 150
            right_pad = 110
            usable = max(40, w - label_w - right_pad)
            center = label_w + usable / 2
            max_abs = max([abs(d["net"]) for d in dept_cf] + [1])
            scale = (usable / 2) / max_abs

            canvas.create_line(center, 5, center, height - 5, fill=theme.BORDER)
            for i, d in enumerate(dept_cf):
                y = 20 + i * row_h
                canvas.create_text(10, y, text=d["name"], fill=theme.TEXT_PRI,
                                   anchor="w", font=("Segoe UI", 11, "bold"))
                net = d["net"]
                bar_len = abs(net) * scale
                color = theme.GREEN if net >= 0 else theme.RED
                if net >= 0:
                    canvas.create_rectangle(center, y - 8, center + bar_len, y + 8, fill=color, outline="")
                    text_x, anchor = center + bar_len + 8, "w"
                else:
                    canvas.create_rectangle(center - bar_len, y - 8, center, y + 8, fill=color, outline="")
                    text_x, anchor = center - bar_len - 8, "e"
                canvas.create_text(text_x, y, text=fmt_money(net, sym), fill=color,
                                   anchor=anchor, font=("Segoe UI", 10, "bold"))

        canvas.bind("<Configure>", render)
        self.after(50, render)

    def on_resize(self, width: int):
        for c in self._canvases:
            try:
                c.event_generate("<Configure>")
            except Exception:
                pass
