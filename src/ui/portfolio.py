"""
WealthMap – Portfolio Panel
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime, timezone

from src.models.database import AssetType
from src.ui.widgets import (safe_rebuild, 
    SectionHeader, StatCard, DataTable, Modal,
    make_entry, make_combo, make_textbox, fmt_money, fmt_money_base,
    attach_currency_tooltip, AttachmentSection
)
from src.ui.theme import theme


class PortfolioPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._assets_by_id = {}
        self._build()

    def _build(self):
        base = self.ctx.settings.get("base_currency", "USD")
        base_cur = self.ctx.currency.get_by_code(base)
        sym = base_cur.symbol if base_cur else ""

        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)

        hdr_row = ctk.CTkFrame(scroll, fg_color="transparent")
        hdr_row.grid(row=0, column=0, sticky="ew", pady=(0, 20))
        SectionHeader(hdr_row, "Portfolio", "Investments & assets",
                      "＋ Add Asset", self._open_new_asset).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(hdr_row, text="⟳ Refresh Prices", height=34, font=("Segoe UI", 12),
                      fg_color=theme.BG_CARD, hover_color=theme.BG_HOVER,
                      border_width=1, border_color=theme.BORDER, text_color=theme.TEXT_PRI,
                      command=self._refresh_prices).pack(side="right", padx=(8, 0))

        # Summary cards
        try:
            port = self.ctx.portfolio.portfolio_summary(base)
        except Exception:
            port = {"total_value": 0, "total_pnl": 0, "pnl_pct": 0, "assets": []}

        cards_frame = ctk.CTkFrame(scroll, fg_color="transparent")
        cards_frame.grid(row=1, column=0, sticky="ew", pady=(0, 20))
        for i in range(3):
            cards_frame.grid_columnconfigure(i, weight=1)

        pnl_color = theme.GREEN if port["total_pnl"] >= 0 else theme.RED
        StatCard(cards_frame, "Total Value",    fmt_money(port["total_value"], sym), "", theme.GOLD,   "💼"
                 ).grid(row=0, column=0, sticky="ew", padx=(0, 8))
        StatCard(cards_frame, "Unrealized P&L", fmt_money(port["total_pnl"],   sym),
                 f"{port['pnl_pct']:+.2f}%", pnl_color, "📊"
                 ).grid(row=0, column=1, sticky="ew", padx=(0, 8))
        StatCard(cards_frame, "Assets",         str(len(port["assets"])),           "", theme.ACCENT, "🔢"
                 ).grid(row=0, column=2, sticky="ew")

        # Holdings table
        cols = [
            {"key": "ticker",       "label": "Ticker",      "width": 80,  "anchor": "w"},
            {"key": "name",         "label": "Name",        "width": 160, "anchor": "w"},
            {"key": "type",         "label": "Type",        "width": 100, "anchor": "w"},
            {"key": "qty",          "label": "Qty",         "width": 80,  "anchor": "e"},
            {"key": "avg_cost",     "label": "Avg Cost",    "width": 90,  "anchor": "e"},
            {"key": "curr_price",   "label": "Price",       "width": 100, "anchor": "e"},
            {"key": "source",       "label": "Source",      "width": 70,  "anchor": "w"},
            {"key": "market_value", "label": "Mkt Value",   "width": 110, "anchor": "e"},
            {"key": "pnl",          "label": "P&L",         "width": 100, "anchor": "e"},
            {"key": "pnl_pct",      "label": "P&L %",       "width": 80,  "anchor": "e"},
        ]
        table = DataTable(scroll, cols, height=300)
        table.grid(row=2, column=0, sticky="ew", pady=(0, 16))
        self._table = table

        # Build a quick lookup of asset objects for the edit dialog
        from src.models.database import PortfolioAsset
        self._assets_by_id = {a.id: a for a in self.ctx.session.query(PortfolioAsset).all()}

        rows = []
        for a in port["assets"]:
            pnl_col = theme.GREEN if a["unrealized_pnl"] >= 0 else theme.RED
            cur_sym = ""
            try:
                c = self.ctx.currency.get_by_code(a["currency"])
                cur_sym = c.symbol if c else ""
            except Exception:
                pass
            asset_obj = self._assets_by_id.get(a["id"])
            source = (asset_obj.price_source if asset_obj else "manual") or "manual"
            rows.append({
                "ticker":       a["ticker"] or "—",
                "name":         a["name"],
                "type":         a["type"],
                "qty":          f"{a['quantity']:,.4f}",
                "avg_cost":     fmt_money_base(self.ctx, a["avg_cost"], a["currency"]),
                "curr_price":   fmt_money_base(self.ctx, a["current_price"], a["currency"]) if a["current_price"] else "—",
                "source":       "📡 market" if source == "market" else "✎ manual",
                "market_value": fmt_money(a["market_value_base"], sym),
                "pnl":          fmt_money(a["unrealized_pnl"], cur_sym),
                "pnl_pct":      f"{a['pnl_pct']:+.2f}%",
                "_color_pnl":   pnl_col,
                "_color_pnl_pct": pnl_col,
                "_color_source": theme.ACCENT if source == "market" else theme.TEXT_SEC,
                "_asset_id":    a["id"],
                # Raw values for inline editing
                "_raw_ticker":   a["ticker"] or "",
                "_raw_name":     a["name"],
                "_raw_qty":      f"{a['quantity']:g}",
                "_raw_avg_cost": f"{a['avg_cost']:g}",
            })
        editable_cols = [
            {"key": "ticker", "editor": "entry"},
            {"key": "name", "editor": "entry"},
            {"key": "qty", "editor": "entry"},
            {"key": "avg_cost", "editor": "entry"},
        ]
        table.set_rows(rows, on_select=self._on_asset_select,
                      editable_cols=editable_cols, on_row_save=self._on_row_save)

        if not rows:
            ctk.CTkLabel(scroll, text="No assets yet. Click '＋ Add Asset' to start tracking your portfolio.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 13)).grid(row=3, column=0, pady=20)
        else:
            ctk.CTkLabel(scroll, text="Click a row to edit, update price, or record a trade.",
                         text_color=theme.TEXT_SEC, font=("Segoe UI", 11)).grid(row=3, column=0, sticky="w", pady=(0, 8))

    # ── Live price refresh ──────────────────────────────────────────────────

    def _refresh_prices(self):
        try:
            result = self.ctx.market_data.update_all_prices(self.ctx.portfolio)
            msg = f"Updated {result['updated']} asset price(s)."
            if result["failed"]:
                lines = "\n".join(f"  • {ticker}: {reason}" for ticker, reason in result["failed"])
                msg += f"\n\nCould not fetch:\n{lines}"
            if result["skipped"]:
                msg += f"\n\n{result['skipped']} asset(s) use manual pricing (Real Estate / Other / no ticker)."
            messagebox.showinfo("Price Refresh", msg)
            self.app.refresh()
            self._rebuild()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ── Asset selection → edit/trade dialog ─────────────────────────────────

    def _on_asset_select(self, row):
        asset = self._assets_by_id.get(row.get("_asset_id"))
        if asset:
            self._open_asset_modal(asset)

    def _on_row_save(self, row, new_values):
        asset = self._assets_by_id.get(row.get("_asset_id"))
        if not asset:
            return
        try:
            qty = float(new_values["qty"].strip().replace(",", ""))
            cost = float(new_values["avg_cost"].strip().replace(",", ""))
        except ValueError:
            raise ValueError("Quantity and Average Cost must be numbers")
        name = new_values["name"].strip()
        if not name:
            raise ValueError("Name cannot be empty")
        self.ctx.portfolio.update_asset(
            asset,
            name=name,
            ticker=new_values["ticker"].strip(),
            quantity=qty,
            average_cost=cost,
        )
        self.app.refresh()
        self._rebuild()

    def _open_asset_modal(self, asset):
        modal = Modal(self, f"{asset.name} ({asset.ticker or '—'})", width=520, height=760)
        currencies = [c.code for c in self.ctx.currency.get_all()]
        asset_types = [t.value for t in AssetType]

        cur = asset.currency
        sym = cur.symbol if cur else ""

        # ── Summary ──────────────────────────────────────────────────────
        info_frame = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
        info_frame.pack(fill="x", pady=(0, 12))
        pnl_col = theme.GREEN if asset.unrealized_pnl >= 0 else theme.RED
        ctk.CTkLabel(info_frame, text=f"Market Value: {fmt_money(asset.market_value, sym)}  •  "
                                       f"P&L: {fmt_money(asset.unrealized_pnl, sym)} ({asset.pnl_pct:+.2f}%)",
                     font=("Segoe UI", 12, "bold"), text_color=pnl_col).pack(anchor="w", padx=12, pady=8)
        if asset.purchase_date:
            ctk.CTkLabel(info_frame, text=f"Purchased: {asset.purchase_date.strftime('%d %b %Y %H:%M')}",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="w", padx=12, pady=(0, 8))
        if asset.last_price_update:
            src = "live market data" if asset.price_source == "market" else "manual entry"
            ctk.CTkLabel(info_frame, text=f"Price last updated: {asset.last_price_update.strftime('%d %b %Y %H:%M')} "
                                           f"({src})",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(anchor="w", padx=12, pady=(0, 8))

        meta = asset.market_meta_dict
        if asset.price_source == "market" and meta:
            stats = []
            if meta.get("day_change_pct") is not None:
                dc_pct = meta["day_change_pct"]
                dc_abs = meta.get("day_change_abs")
                dc_col = "▲" if dc_pct >= 0 else "▼"
                dc_str = f"{dc_col} {dc_pct:+.2f}%"
                if dc_abs is not None:
                    dc_str += f" ({fmt_money(dc_abs, sym)})"
                stats.append(("Day Change", dc_str))
            if meta.get("previous_close") is not None:
                stats.append(("Prev. Close", fmt_money(meta["previous_close"], sym)))
            if meta.get("week52_high") is not None or meta.get("week52_low") is not None:
                lo = meta.get("week52_low")
                hi = meta.get("week52_high")
                rng = f"{fmt_money(lo, sym) if lo is not None else '—'} – {fmt_money(hi, sym) if hi is not None else '—'}"
                stats.append(("52-Week Range", rng))
            if meta.get("market_cap") is not None:
                stats.append(("Market Cap", fmt_money(meta["market_cap"], sym)))
            if stats:
                stats_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
                stats_frame.pack(fill="x", padx=12, pady=(0, 10))
                for label, val in stats:
                    cell = ctk.CTkFrame(stats_frame, fg_color="transparent")
                    cell.pack(side="left", padx=(0, 16))
                    ctk.CTkLabel(cell, text=label, font=("Segoe UI", 9),
                                 text_color=theme.TEXT_SEC).pack(anchor="w")
                    ctk.CTkLabel(cell, text=val, font=("Segoe UI", 12, "bold"),
                                 text_color=theme.TEXT_PRI).pack(anchor="w")

        if len(asset.price_history) > 1:
            hist_frame = ctk.CTkFrame(info_frame, fg_color="transparent")
            hist_frame.pack(fill="x", padx=12, pady=(0, 10))
            ctk.CTkLabel(hist_frame, text=f"Price history ({len(asset.price_history)} snapshots saved for analysis)",
                         font=("Segoe UI", 9), text_color=theme.TEXT_SEC).pack(anchor="w")
            recent = list(reversed(asset.price_history))[:5]
            hist_text = "   ".join(
                f"{s.recorded_at.strftime('%d %b %H:%M')}: {fmt_money(s.price, sym)}" for s in recent
            )
            ctk.CTkLabel(hist_frame, text=hist_text, font=("Segoe UI", 10),
                         text_color=theme.TEXT_PRI, wraplength=440, justify="left").pack(anchor="w")

        # ── Edit fields ──────────────────────────────────────────────────
        ctk.CTkLabel(modal.body, text="✎ Edit Asset", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(4, 4))

        name_e = modal.add_field("Name", lambda p: make_entry(p))
        name_e.insert(0, asset.name)

        tick_e = modal.add_field("Ticker Symbol", lambda p: make_entry(p))
        tick_e.insert(0, asset.ticker or "")

        type_c = modal.add_field("Asset Type", lambda p: make_combo(p, asset_types,
                                  command=lambda v: _on_type_change(v)))
        type_c.set(asset.asset_type.value)
        hint_lbl = ctk.CTkLabel(modal.body, text=self._ticker_hint(asset.asset_type.value),
                               font=("Segoe UI", 10), text_color=theme.TEXT_SEC, anchor="w")
        hint_lbl.pack(fill="x", pady=(0, 8))

        qty_e = modal.add_field("Quantity", lambda p: make_entry(p))
        qty_e.insert(0, f"{asset.quantity:g}")

        cost_e = modal.add_field("Average Cost / Unit", lambda p: make_entry(p))
        cost_e.insert(0, f"{asset.average_cost:g}")

        cur_c = modal.add_field("Currency", lambda p: make_combo(p, currencies))
        cur_c.set(cur.code)
        attach_currency_tooltip(cur_c, self.ctx)

        price_e = modal.add_field("Current Price (manual override)", lambda p: make_entry(p))
        if asset.current_price is not None:
            price_e.insert(0, f"{asset.current_price:g}")

        # Valuation factors — shown for Real Estate / Other, where price isn't
        # driven by a market feed. Free-form: location, size, condition,
        # comparables, last appraisal, renovations, market trends, etc.
        factors_lbl = ctk.CTkLabel(modal.body, text="Valuation Factors (what drives this asset's value)",
                                   font=("Segoe UI", 12), text_color=theme.TEXT_SEC, anchor="w")
        factors_t = make_textbox(modal.body, height=80)
        factors_t.insert("1.0", asset.valuation_factors or "")

        def update_factors_visibility(value):
            atype = next((t for t in AssetType if t.value == value), None)
            if atype in (AssetType.REAL_ESTATE, AssetType.OTHER):
                factors_lbl.pack(fill="x", pady=(0, 2), before=notes_row)
                factors_t.pack(fill="x", pady=(0, 8), before=notes_row)
            else:
                factors_lbl.pack_forget()
                factors_t.pack_forget()

        def _on_type_change(value):
            hint_lbl.configure(text=self._ticker_hint(value))
            update_factors_visibility(value)

        notes_t = modal.add_field("Notes", lambda p: make_textbox(p, height=50))
        notes_row = notes_t.master
        notes_t.insert("1.0", asset.notes or "")
        update_factors_visibility(asset.asset_type.value)

        # ── Attachments (proof files: deeds, certificates, statements, photos) ──
        ctk.CTkLabel(modal.body, text="📎 Attachments", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(8, 4))
        attachments_frame = ctk.CTkFrame(modal.body, fg_color="transparent")
        attachments_frame.pack(fill="x", pady=(0, 4))

        def refresh_attachments():
            for w in attachments_frame.winfo_children():
                w.destroy()
            if not asset.attachments:
                ctk.CTkLabel(attachments_frame, text="No files attached yet.",
                             font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w", pady=2)
            for att in asset.attachments:
                row_f = ctk.CTkFrame(attachments_frame, fg_color=theme.ROW_ALT, corner_radius=6)
                row_f.pack(fill="x", pady=2)
                ctk.CTkLabel(row_f, text=f"📎 {att.original_filename}",
                             font=("Segoe UI", 11), text_color=theme.ACCENT).pack(side="left", padx=8, pady=4)
                ctk.CTkButton(row_f, text="Open", width=60, height=24,
                              fg_color="transparent", text_color=theme.ACCENT, font=("Segoe UI", 11),
                              command=lambda a=att: self.ctx.attachment.open_file(a)
                              ).pack(side="right", padx=4, pady=2)
                ctk.CTkButton(row_f, text="✕", width=28, height=24,
                              fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                              command=lambda a=att: delete_attachment(a)
                              ).pack(side="right", pady=2)

        def attach_file():
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                title="Attach proof file (deed, certificate, statement, photo — any file type)",
                filetypes=[("All files", "*.*"),
                           ("Documents & images", "*.pdf *.png *.jpg *.jpeg *.doc *.docx *.xls *.xlsx *.csv *.txt")]
            )
            if not path:
                return
            try:
                self.ctx.attachment.save_file(path, self.ctx.session, "asset", asset.id)
                self.ctx.session.refresh(asset)
                refresh_attachments()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete_attachment(att):
            if messagebox.askyesno("Delete Attachment", f"Remove '{att.original_filename}'?", parent=modal):
                self.ctx.attachment.delete_file(att, self.ctx.session)
                self.ctx.session.refresh(asset)
                refresh_attachments()

        refresh_attachments()
        ctk.CTkButton(modal.body, text="＋ Attach File", height=30, font=("Segoe UI", 11),
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, command=attach_file).pack(anchor="w", pady=(2, 8))

        def save():
            try:
                atype = next(t for t in AssetType if t.value == type_c.get())
                fields = dict(
                    name=name_e.get().strip(),
                    ticker=tick_e.get().strip(),
                    asset_type=atype,
                    quantity=float(qty_e.get().replace(",", "")),
                    average_cost=float(cost_e.get().replace(",", "")),
                    currency_code=cur_c.get(),
                    notes=notes_t.get("1.0", "end").strip(),
                    valuation_factors=factors_t.get("1.0", "end").strip(),
                )
                self.ctx.portfolio.update_asset(asset, **fields)
                price_text = price_e.get().strip()
                if price_text:
                    new_price = float(price_text.replace(",", ""))
                    if new_price != asset.current_price:
                        self.ctx.portfolio.update_price(asset, new_price)
                        asset.price_source = "manual"
                        self.ctx.session.commit()
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        def delete():
            if messagebox.askyesno("Delete Asset",
                                   f"Delete '{asset.name}' and its full trade history? "
                                   "This cannot be undone.", parent=modal):
                self.ctx.portfolio.delete_asset(asset)
                modal.destroy()
                self.app.refresh()
                self._rebuild()

        # ── Record trade ─────────────────────────────────────────────────
        ctk.CTkLabel(modal.body, text="📈 Record a Trade", font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(12, 4))
        trade_type_c = make_combo(modal.body, ["BUY", "SELL", "DIVIDEND"])
        trade_type_c.set("BUY")
        trade_type_c.pack(fill="x", pady=(0, 4))
        trade_qty_e = make_entry(modal.body, "Quantity")
        trade_qty_e.pack(fill="x", pady=(0, 4))
        trade_price_e = make_entry(modal.body, "Price per unit")
        trade_price_e.pack(fill="x", pady=(0, 4))
        fee_tax_row = ctk.CTkFrame(modal.body, fg_color="transparent")
        fee_tax_row.pack(fill="x", pady=(0, 4))
        trade_fee_e = make_entry(fee_tax_row, "Fees")
        trade_fee_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
        trade_tax_e = make_entry(fee_tax_row, "Taxes")
        trade_tax_e.pack(side="left", fill="x", expand=True)

        def record_trade():
            try:
                qty = float(trade_qty_e.get().replace(",", ""))
                price = float(trade_price_e.get().replace(",", ""))
                fees = self._parse_float(trade_fee_e.get()) or 0.0
                taxes = self._parse_float(trade_tax_e.get()) or 0.0
                self.ctx.portfolio.record_trade(asset, trade_type_c.get(), qty, price,
                                                 fees=fees, taxes=taxes)
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        ctk.CTkButton(modal.body, text="Record Trade", height=34, font=("Segoe UI", 12),
                      fg_color=theme.ACCENT2, hover_color=theme.BG_SELECTED, text_color="#fff",
                      command=record_trade).pack(fill="x", pady=(4, 8))

        modal.add_buttons("Save Changes", save,
                         extra=[("Delete Asset", delete, theme.RED)])

    # ── New asset ────────────────────────────────────────────────────────────

    def _ticker_hint(self, asset_type_value: str) -> str:
        try:
            atype = next(t for t in AssetType if t.value == asset_type_value)
            return self.ctx.market_data.suggested_ticker_format(atype)
        except Exception:
            return ""

    def _open_new_asset(self):
        modal = Modal(self, "Add Portfolio Asset", width=520, height=700)
        accounts  = [a for a in self.ctx.account.get_all()
                     if a.account_type.value in ("Investment Portfolio", "Crypto Wallet")]
        acc_names = [a.name for a in accounts]
        if not acc_names:
            messagebox.showinfo("No Portfolio Accounts",
                                "Create an Investment Portfolio account first.")
            modal.destroy()
            return
        asset_types = [t.value for t in AssetType]
        currencies  = [c.code for c in self.ctx.currency.get_all()]

        acc_c   = modal.add_field("Portfolio Account",  lambda p: make_combo(p, acc_names))
        type_c  = modal.add_field("Asset Type",         lambda p: make_combo(p, asset_types,
                                  command=lambda v: on_type_change(v)))
        hint_lbl = ctk.CTkLabel(modal.body, text=self._ticker_hint("Stock"),
                               font=("Segoe UI", 10), text_color=theme.TEXT_SEC, anchor="w")
        hint_lbl.pack(fill="x", pady=(0, 8))

        # Known-asset picker (Stock/ETF/Mutual Fund/Crypto/Commodity) — selecting
        # one auto-fills the name & ticker fields below.
        known_lbl = ctk.CTkLabel(modal.body, text="Known Asset (optional — auto-fills name & ticker)",
                                 font=("Segoe UI", 12), text_color=theme.TEXT_SEC, anchor="w")
        known_c = make_combo(modal.body, [], command=lambda v: on_known_pick(v))

        name_e  = modal.add_field("Asset Name",         lambda p: make_entry(p, "Apple Inc."))
        tick_e  = modal.add_field("Ticker Symbol",      lambda p: make_entry(p, "AAPL"))
        qty_e   = modal.add_field("Quantity",           lambda p: make_entry(p, "0"))
        cost_e  = modal.add_field("Average Cost / Unit",lambda p: make_entry(p, "0.00"))
        fetch_status_lbl = ctk.CTkLabel(modal.body, text="", font=("Segoe UI", 10),
                                        text_color=theme.ACCENT, anchor="w")
        fetch_status_lbl.pack(fill="x", pady=(0, 4))
        cur_c   = modal.add_field("Currency",           lambda p: make_combo(p, currencies))
        attach_currency_tooltip(cur_c, self.ctx)

        # Purchase date & time — seeds the initial trade-history entry
        ctk.CTkLabel(modal.body, text="Purchase Date & Time", font=("Segoe UI", 12),
                     text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")
        purchase_row = ctk.CTkFrame(modal.body, fg_color="transparent")
        purchase_row.pack(fill="x", pady=(2, 8))
        purchase_date_e = make_entry(purchase_row, "YYYY-MM-DD")
        purchase_date_e.pack(side="left", fill="x", expand=True, padx=(0, 4))
        purchase_time_e = make_entry(purchase_row, "HH:MM", width=80)
        purchase_time_e.pack(side="left")
        now = datetime.now()
        purchase_date_e.insert(0, now.strftime("%Y-%m-%d"))
        purchase_time_e.insert(0, now.strftime("%H:%M"))

        # Valuation factors (Real Estate / Other) — packed after currency, before notes
        factors_lbl = ctk.CTkLabel(modal.body, text="Valuation Factors (what drives this asset's value)",
                                   font=("Segoe UI", 12), text_color=theme.TEXT_SEC, anchor="w")
        factors_t = make_textbox(modal.body, height=80)

        notes_t = modal.add_field("Notes",              lambda p: make_textbox(p, height=60))

        att_section = AttachmentSection(modal.body, self.ctx, "asset", entity=None)
        att_section.pack(fill="x")

        known_map = {}
        fetched_quote = {"data": None}  # mutable holder so save() can see it

        def on_known_pick(label):
            entry = known_map.get(label)
            if not entry:
                return
            name, ticker = entry
            name_e.delete(0, "end")
            name_e.insert(0, name)
            tick_e.delete(0, "end")
            tick_e.insert(0, ticker)

            # Fetch the live price so "Average Cost / Unit" starts pre-filled
            # with today's market price (the user can still edit it).
            atype = next((t for t in AssetType if t.value == type_c.get()), AssetType.STOCK)
            fetched_quote["data"] = None
            if self.ctx.market_data.supports_live(atype):
                fetch_status_lbl.configure(text=f"Fetching current price for {ticker}…")
                modal.update_idletasks()
                quote, reason = self.ctx.market_data.fetch_quote_with_reason(ticker, atype)
                if quote and quote.get("price") is not None:
                    cost_e.delete(0, "end")
                    cost_e.insert(0, f"{quote['price']:g}")
                    if quote.get("currency"):
                        cur_codes = [c.code for c in self.ctx.currency.get_all()]
                        if quote["currency"] in cur_codes:
                            cur_c.set(quote["currency"])
                    fetched_quote["data"] = quote
                    fetch_status_lbl.configure(
                        text=f"✓ Live price loaded: {quote['price']:g} {quote.get('currency','')} "
                             "— you can adjust it if you bought at a different price.")
                else:
                    fetch_status_lbl.configure(
                        text=f"Could not fetch a live price for {ticker} ({reason}). "
                             "Enter the price you paid manually.")

        def on_type_change(value):
            hint_lbl.configure(text=self._ticker_hint(value))
            atype = next((t for t in AssetType if t.value == value), AssetType.STOCK)
            known = self.ctx.market_data.known_assets(atype)
            known_map.clear()
            if known:
                labels = []
                for name, ticker in known:
                    label = f"{name} ({ticker})"
                    known_map[label] = (name, ticker)
                    labels.append(label)
                known_c.configure(values=labels)
                known_c.set("")
                known_lbl.pack(fill="x", pady=(0, 2), before=name_e.master)
                known_c.pack(fill="x", pady=(0, 8), before=name_e.master)
            else:
                known_lbl.pack_forget()
                known_c.pack_forget()

            if atype in (AssetType.REAL_ESTATE, AssetType.OTHER):
                factors_lbl.pack(fill="x", pady=(0, 2), before=notes_t.master)
                factors_t.pack(fill="x", pady=(0, 8), before=notes_t.master)
            else:
                factors_lbl.pack_forget()
                factors_t.pack_forget()

        acc_c.set(acc_names[0])
        type_c.set("Stock")
        cur_c.set("USD")
        on_type_change("Stock")

        def save():
            try:
                acc = next(a for a in accounts if a.name == acc_c.get())
                atype = next(t for t in AssetType if t.value == type_c.get())
                qty  = float(qty_e.get())
                cost = float(cost_e.get().replace(",", ""))

                date_text = purchase_date_e.get().strip()
                time_text = purchase_time_e.get().strip() or "00:00"
                try:
                    purchase_dt = datetime.strptime(f"{date_text} {time_text}", "%Y-%m-%d %H:%M")
                except ValueError:
                    raise ValueError("Purchase date must be YYYY-MM-DD and time HH:MM")

                new_asset = self.ctx.portfolio.add_asset(
                    acc, atype, name_e.get().strip(), tick_e.get().strip(),
                    qty, cost, cur_c.get(), notes_t.get("1.0", "end").strip(),
                    valuation_factors=factors_t.get("1.0", "end").strip(),
                    purchase_date=purchase_dt,
                )
                if fetched_quote["data"]:
                    self.ctx.portfolio.record_price_snapshot(new_asset, fetched_quote["data"])
                att_section.commit(new_asset.id)
                modal.destroy()
                self.app.refresh()
                self._rebuild()
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Add Asset", save)

    @staticmethod
    def _parse_float(text):
        text = (text or "").strip()
        if not text:
            return None
        try:
            return float(text)
        except ValueError:
            return None

    def _rebuild(self):
        safe_rebuild(self, self._build)

    def on_resize(self, width: int):
        pass
