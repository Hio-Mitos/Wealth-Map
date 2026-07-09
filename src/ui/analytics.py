"""
WealthMap – Wealth Journey (Analytics) Panel
Net worth trend, simple forecast, and monthly/yearly expense analytics.
"""

import tkinter as tk
import customtkinter as ctk
from datetime import datetime, timezone
from calendar import month_abbr

from src.ui.widgets import SectionHeader, StatCard, fmt_money, responsive_columns
from src.ui.theme import theme


class AnalyticsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app, **kwargs):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._canvases = []
        self._build()

    # ── Data ──────────────────────────────────────────────────────────────────

    def _months_back(self, n: int):
        """Return list of (year, month) tuples for the last n months, oldest first."""
        now = datetime.now(timezone.utc)
        out = []
        y, m = now.year, now.month
        for _ in range(n):
            out.append((y, m))
            m -= 1
            if m == 0:
                m = 12
                y -= 1
        return list(reversed(out))

    def _gather_data(self, base: str):
        months = self._months_back(12)
        monthly = []
        for (y, m) in months:
            s = self.ctx.transaction.monthly_summary(y, m, base)
            monthly.append(s)

        # Current totals
        snap = self.ctx.account.net_worth_snapshot(base)
        port = self.ctx.portfolio.portfolio_summary(base)
        loans = self.ctx.loan.summary(base)
        current_net_worth = snap["total"] + port["total_value"] + loans["owed_to_me"] - loans["i_owe"]

        # Approximate trend: cumulative net cash flow, shifted so the last
        # point lands on today's actual net worth (portfolio & loan
        # positions are held at their current value across history — an
        # approximation, since we don't store historical snapshots).
        net_flows = [mm["net"] for mm in monthly]
        cumulative = []
        running = 0.0
        for nf in net_flows:
            running += nf
            cumulative.append(running)
        offset = current_net_worth - cumulative[-1] if cumulative else 0.0
        trend = [c + offset for c in cumulative]

        return {
            "months": months, "monthly": monthly, "trend": trend,
            "current_net_worth": current_net_worth,
            "cash_total": snap["total"], "portfolio_total": port["total_value"],
            "loan_net": loans["owed_to_me"] - loans["i_owe"],
        }

    def _forecast(self, trend, n_forward=6):
        """Simple least-squares linear forecast over the trend points."""
        n = len(trend)
        if n < 2:
            flat = trend[-1] if trend else 0
            return [flat] * n_forward, 0.0
        xs = list(range(n))
        xm = sum(xs) / n
        ym = sum(trend) / n
        num = sum((x - xm) * (y - ym) for x, y in zip(xs, trend))
        den = sum((x - xm) ** 2 for x in xs) or 1
        slope = num / den
        intercept = ym - slope * xm
        return [intercept + slope * (n - 1 + i) for i in range(1, n_forward + 1)], slope

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure((0, 1, 2, 3), weight=1)

        SectionHeader(scroll, "📊 Wealth Journey",
                      "Where you stand, where you're headed, and what's driving it"
                      ).grid(row=0, column=0, columnspan=4, sticky="ew", pady=(0, 20))

        data = self._gather_data(base)
        forecast, slope = self._forecast(data["trend"], n_forward=6)
        trend_color = theme.GREEN if slope >= 0 else theme.RED

        # ── Top stat cards ──────────────────────────────────────────────────
        cards = [
            ("Net Worth Today",  fmt_money(data["current_net_worth"], sym), base, theme.GOLD, "💰"),
            ("Cash & Bank",      fmt_money(data["cash_total"], sym), "Accounts & cards", theme.ACCENT, "🏦"),
            ("Portfolio",        fmt_money(data["portfolio_total"], sym), "Investments", theme.ACCENT3, "📈"),
            ("Net Loan Position",fmt_money(data["loan_net"], sym), "Owed to me − I owe", theme.GREEN if data["loan_net"] >= 0 else theme.RED, "🤝"),
        ]
        for i, (lbl, val, sub, color, icon) in enumerate(cards):
            StatCard(scroll, lbl, val, sub, accent=color, icon=icon
                     ).grid(row=1, column=i, padx=(0 if i == 0 else 8, 0), pady=(0, 20), sticky="nsew")

        # ── Net worth trend + forecast chart ────────────────────────────────
        trend_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                  border_width=1, border_color=theme.BORDER)
        trend_card.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(trend_card, text="NET WORTH TREND (12 MONTHS) + 6-MONTH FORECAST",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))

        avg_monthly = sum(mm["net"] for mm in data["monthly"]) / max(1, len(data["monthly"]))
        forecast_6m = forecast[-1] if forecast else data["current_net_worth"]
        trend_word = "growing" if slope > 0 else ("shrinking" if slope < 0 else "flat")
        ctk.CTkLabel(trend_card,
                     text=f"Your net worth is {trend_word} by roughly {fmt_money(abs(slope), sym)}/month on average "
                          f"(avg. net cash flow {fmt_money(avg_monthly, sym)}/mo). "
                          f"At this pace, in 6 months you'd be around {fmt_money(forecast_6m, sym)}.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC, wraplength=900, justify="left"
                     ).pack(anchor="w", padx=16, pady=(0, 8))

        labels = [f"{month_abbr[m]} '{str(y)[2:]}" for (y, m) in data["months"]]
        forecast_labels = []
        fm_y, fm_m = data["months"][-1]
        for _ in range(6):
            fm_m += 1
            if fm_m == 13:
                fm_m = 1
                fm_y += 1
            forecast_labels.append(f"{month_abbr[fm_m]} '{str(fm_y)[2:]}")

        self._draw_line_chart(trend_card, data["trend"], forecast, labels, forecast_labels, sym)

        # ── Monthly expenses bar chart ───────────────────────────────────────
        exp_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
        exp_card.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=(0, 8), pady=(0, 20))
        ctk.CTkLabel(exp_card, text="MONTHLY INCOME VS EXPENSES",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))
        self._draw_bar_chart(exp_card,
                             [(mm["income"], mm["expenses"]) for mm in data["monthly"][-6:]],
                             labels[-6:], sym)

        # ── Category breakdown (current month) ───────────────────────────────
        cat_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
        cat_card.grid(row=3, column=2, columnspan=2, sticky="nsew", padx=(8, 0), pady=(0, 20))
        ctk.CTkLabel(cat_card, text=f"{labels[-1]} EXPENSES BY CATEGORY",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))
        self._build_category_breakdown(cat_card, data["monthly"][-1], sym)

        # ── Yearly summary ────────────────────────────────────────────────────
        year_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                 border_width=1, border_color=theme.BORDER)
        year_card.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 20))
        ctk.CTkLabel(year_card, text="YEARLY SUMMARY",
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(12, 4))
        self._build_yearly_summary(year_card, base, sym)

    # ── Category breakdown ───────────────────────────────────────────────────

    def _build_category_breakdown(self, parent, month_summary, sym):
        by_cat = month_summary.get("by_category", {})
        if not by_cat:
            ctk.CTkLabel(parent, text="No expenses recorded this month.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 12)).pack(pady=20)
            return
        total = sum(by_cat.values()) or 1
        for cat, val in sorted(by_cat.items(), key=lambda kv: kv[1], reverse=True)[:8]:
            row = ctk.CTkFrame(parent, fg_color="transparent")
            row.pack(fill="x", padx=16, pady=3)
            ctk.CTkLabel(row, text=cat, font=("Segoe UI", 11), text_color=theme.TEXT_PRI,
                        anchor="w", width=140).pack(side="left")
            ctk.CTkLabel(row, text=fmt_money(val, sym), font=("Segoe UI", 11, "bold"),
                        text_color=theme.GOLD, anchor="e", width=90).pack(side="right")
            bar_bg = ctk.CTkFrame(row, height=8, fg_color=theme.BG_HOVER, corner_radius=4)
            bar_bg.pack(side="left", fill="x", expand=True, padx=8)
            pct = val / total
            bar_fg = ctk.CTkFrame(bar_bg, height=8, fg_color=theme.ACCENT, corner_radius=4)
            bar_fg.place(relx=0, rely=0, relwidth=max(0.01, pct), relheight=1)
        ctk.CTkLabel(parent, text="", height=8).pack()

    # ── Yearly summary ────────────────────────────────────────────────────────

    def _build_yearly_summary(self, parent, base, sym):
        now = datetime.now(timezone.utc)
        rows_frame = ctk.CTkFrame(parent, fg_color="transparent")
        rows_frame.pack(fill="x", padx=16, pady=(0, 12))

        hdr = ctk.CTkFrame(rows_frame, fg_color="transparent")
        hdr.pack(fill="x", pady=(0, 4))
        for txt, w in [("Year", 80), ("Income", 140), ("Expenses", 140), ("Net Savings", 140), ("Savings Rate", 110)]:
            ctk.CTkLabel(hdr, text=txt, font=("Segoe UI", 10, "bold"),
                        text_color=theme.TEXT_SEC, width=w, anchor="w").pack(side="left")

        for year in range(now.year - 2, now.year + 1):
            income = expenses = 0.0
            for m in range(1, 13):
                if year == now.year and m > now.month:
                    break
                s = self.ctx.transaction.monthly_summary(year, m, base)
                income += s["income"]
                expenses += s["expenses"]
            net = income - expenses
            rate = (net / income * 100) if income else 0.0
            row = ctk.CTkFrame(rows_frame, fg_color="transparent")
            row.pack(fill="x", pady=2)
            net_col = theme.GREEN if net >= 0 else theme.RED
            ctk.CTkLabel(row, text=str(year), font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
                        width=80, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=fmt_money(income, sym), font=("Segoe UI", 12), text_color=theme.GREEN,
                        width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=fmt_money(expenses, sym), font=("Segoe UI", 12), text_color=theme.RED,
                        width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=fmt_money(net, sym), font=("Segoe UI", 12, "bold"), text_color=net_col,
                        width=140, anchor="w").pack(side="left")
            ctk.CTkLabel(row, text=f"{rate:.1f}%", font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                        width=110, anchor="w").pack(side="left")

    # ── Charts (Canvas-based, theme-aware) ──────────────────────────────────

    def _draw_line_chart(self, parent, trend, forecast, labels, forecast_labels, sym):
        canvas = tk.Canvas(parent, height=220, bg=theme.BG_CARD, highlightthickness=0)
        canvas.pack(fill="x", padx=16, pady=(0, 12))
        self._canvases.append(canvas)

        def render(event=None):
            canvas.delete("all")
            w = canvas.winfo_width() or 800
            h = 220
            pad_l, pad_r, pad_t, pad_b = 60, 20, 20, 30

            all_vals = trend + forecast
            vmin, vmax = min(all_vals), max(all_vals)
            if vmin == vmax:
                vmin -= 1
                vmax += 1
            span = vmax - vmin

            total_pts = len(trend) + len(forecast)
            plot_w = w - pad_l - pad_r
            plot_h = h - pad_t - pad_b
            step = plot_w / max(1, total_pts - 1)

            def to_xy(i, val):
                x = pad_l + i * step
                y = pad_t + plot_h - ((val - vmin) / span) * plot_h
                return x, y

            # Zero line / gridlines (3 horizontal guides)
            for frac in (0, 0.5, 1.0):
                gy = pad_t + plot_h - frac * plot_h
                val = vmin + frac * span
                canvas.create_line(pad_l, gy, w - pad_r, gy, fill=theme.BORDER, dash=(2, 3))
                canvas.create_text(pad_l - 8, gy, text=f"{sym}{val:,.0f}", fill=theme.TEXT_SEC,
                                   anchor="e", font=("Segoe UI", 9))

            # Historical line
            pts = [to_xy(i, v) for i, v in enumerate(trend)]
            for i in range(len(pts) - 1):
                canvas.create_line(*pts[i], *pts[i + 1], fill=theme.ACCENT, width=2)
            for x, y in pts:
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=theme.ACCENT, outline="")

            # Forecast line (dashed)
            f_pts = [to_xy(len(trend) - 1 + i, v) for i, v in enumerate([trend[-1]] + forecast)]
            for i in range(len(f_pts) - 1):
                canvas.create_line(*f_pts[i], *f_pts[i + 1], fill=theme.GOLD, width=2, dash=(4, 3))
            for x, y in f_pts[1:]:
                canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=theme.GOLD, outline="")

            # X labels (every other to avoid crowding)
            all_labels = labels + forecast_labels
            for i, lbl in enumerate(all_labels):
                if i % 2 != 0 and i != len(all_labels) - 1:
                    continue
                x, _ = to_xy(i, vmin)
                canvas.create_text(x, h - 10, text=lbl, fill=theme.TEXT_SEC, font=("Segoe UI", 8))

            # Legend
            canvas.create_line(w - 180, 14, w - 160, 14, fill=theme.ACCENT, width=2)
            canvas.create_text(w - 155, 14, text="Historical", fill=theme.TEXT_SEC, anchor="w", font=("Segoe UI", 9))
            canvas.create_line(w - 90, 14, w - 70, 14, fill=theme.GOLD, width=2, dash=(4, 3))
            canvas.create_text(w - 65, 14, text="Forecast", fill=theme.TEXT_SEC, anchor="w", font=("Segoe UI", 9))

        canvas.bind("<Configure>", render)
        self.after(50, render)

    def _draw_bar_chart(self, parent, pairs, labels, sym):
        canvas = tk.Canvas(parent, height=220, bg=theme.BG_CARD, highlightthickness=0)
        canvas.pack(fill="x", padx=16, pady=(0, 12))
        self._canvases.append(canvas)

        def render(event=None):
            canvas.delete("all")
            w = canvas.winfo_width() or 500
            h = 220
            pad_l, pad_r, pad_t, pad_b = 50, 10, 10, 30
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
            canvas.create_text(w - 132, 13, text="Income", fill=theme.TEXT_SEC, anchor="w", font=("Segoe UI", 9))
            canvas.create_rectangle(w - 80, 8, w - 68, 18, fill=theme.RED, outline="")
            canvas.create_text(w - 62, 13, text="Expenses", fill=theme.TEXT_SEC, anchor="w", font=("Segoe UI", 9))

        canvas.bind("<Configure>", render)
        self.after(50, render)

    def on_resize(self, width: int):
        for c in self._canvases:
            try:
                c.event_generate("<Configure>")
            except Exception:
                pass
