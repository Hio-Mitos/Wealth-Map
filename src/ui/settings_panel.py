"""
WealthMap – Settings Panel
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk

from src.ui.widgets import (
    SectionHeader,
    make_entry,
    make_combo
)
from src.ui.theme import theme


class SettingsPanel(ctk.CTkFrame):
    def __init__(self, parent, ctx, app):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self.ctx = ctx
        self.app = app
        self._build()

    def _build(self):
        scroll = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        scroll.pack(fill="both", expand=True, padx=24, pady=16)
        scroll.grid_columnconfigure(0, weight=1)
        self._scroll = scroll
        row = [0]  # mutable row counter

        def next_row():
            row[0] += 1
            return row[0]

        SectionHeader(scroll, "Settings", "Preferences & configuration"
                      ).grid(row=next_row(), column=0, sticky="ew", pady=(0, 24))

        # ── Profile ──────────────────────────────────────────────────────────
        profile = self.ctx.profile
        type_label = "Business" if self.ctx.is_business else "Personal"
        self._section(scroll, row=next_row(), title="Profile",
                      desc=f"\"{profile.get('name','Personal')}\" — {type_label} profile. "
                           "Manage linked profiles for cross-profile transfers, or switch profiles.")
        profile_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                    border_width=1, border_color=theme.BORDER)
        profile_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))
        self._build_profile_section(profile_card)

        # ── Base Currency ──────────────────────────────────────────────────────
        self._section(scroll, row=next_row(), title="Base Currency",
                      desc="All balances and net worth are converted to this currency.")

        cur_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
        cur_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))

        crow = ctk.CTkFrame(cur_card, fg_color="transparent")
        crow.pack(fill="x", padx=16, pady=16)

        currencies = [c.code for c in self.ctx.currency.get_all()]
        self._base_combo = make_combo(crow, currencies, width=160)
        current_base = self.ctx.settings.get("base_currency", "USD")
        self._base_combo.set(current_base)
        self._base_combo.pack(side="left")

        ctk.CTkButton(crow, text="Save", width=80, height=36,
                      fg_color=theme.ACCENT, hover_color="#1C6FBF",
                      text_color="#fff", font=("Segoe UI", 12),
                      command=self._save_base_currency).pack(side="left", padx=12)

        # ── Appearance ────────────────────────────────────────────────────────
        self._section(scroll, row=next_row(), title="Appearance",
                      desc="UI theme and display preferences.")

        app_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
        app_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))

        trow = ctk.CTkFrame(app_card, fg_color="transparent")
        trow.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(trow, text="Theme:", font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(side="left")
        theme_combo = make_combo(trow, ["Dark", "Light"], width=120)
        theme_combo.set("Light" if theme.mode == "light" else "Dark")
        theme_combo.pack(side="left", padx=12)
        ctk.CTkButton(trow, text="Apply", width=80, height=36,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 12),
                      command=lambda: self.app.set_theme(theme_combo.get())
                      ).pack(side="left")
        ctk.CTkLabel(trow, text="(also toggleable from the sidebar)", font=("Segoe UI", 10),
                     text_color=theme.TEXT_SEC).pack(side="left", padx=12)

        # Default landing page
        prow = ctk.CTkFrame(app_card, fg_color="transparent")
        prow.pack(fill="x", padx=16, pady=(8, 8))
        ctk.CTkLabel(prow, text="Start on page:", font=("Segoe UI", 12),
                     text_color=theme.TEXT_SEC).pack(side="left")
        from src.ui.app import NAV_ITEMS
        page_labels = {key: label for _, label, key in NAV_ITEMS}
        page_keys = list(page_labels.keys())
        page_combo = make_combo(prow, [page_labels[k] for k in page_keys], width=180)
        current_default = self.ctx.settings.get("default_panel", "dashboard")
        page_combo.set(page_labels.get(current_default, "Dashboard"))
        page_combo.pack(side="left", padx=12)

        def save_default_page():
            label = page_combo.get()
            key = next((k for k, v in page_labels.items() if v == label), "dashboard")
            self.ctx.settings.set("default_panel", key)
            messagebox.showinfo("Saved", f"WealthMap will now open on {label}.")

        ctk.CTkButton(prow, text="Apply", width=80, height=36,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 12),
                      command=save_default_page).pack(side="left")

        # Show base-currency equivalents toggle
        brow = ctk.CTkFrame(app_card, fg_color="transparent")
        brow.pack(fill="x", padx=16, pady=(8, 16))
        show_equiv = ctk.BooleanVar(value=self.ctx.settings.get("show_base_equivalents", True))

        def toggle_equiv():
            self.ctx.settings.set("show_base_equivalents", show_equiv.get())
            self.app.refresh()

        ctk.CTkSwitch(brow, text="Show base-currency equivalents next to foreign-currency amounts",
                      variable=show_equiv, command=toggle_equiv,
                      font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                      progress_color=theme.ACCENT).pack(side="left")

        # ── Custom Categories ────────────────────────────────────────────────
        self._section(scroll, row=next_row(), title="Custom Transaction Categories",
                      desc="Add your own categories alongside the built-in ones.")
        cat_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
        cat_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))
        self._build_categories_section(cat_card)

        # ── Custom Transaction Types ─────────────────────────────────────────
        self._section(scroll, row=next_row(), title="Custom Transaction Types",
                      desc="Define your own transaction types — each is classified as "
                           "increasing your balance, decreasing it, or either (signed amount).")
        type_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                 border_width=1, border_color=theme.BORDER)
        type_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))
        self._build_custom_types_section(type_card)

        # ── Data Management ───────────────────────────────────────────────────
        self._section(scroll, row=next_row(), title="Data Management",
                      desc="Export, backup, or reset your data.")

        data_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                 border_width=1, border_color=theme.BORDER)
        data_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))

        btn_row = ctk.CTkFrame(data_card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=16)

        ctk.CTkButton(btn_row, text="📤 Export CSV", width=140, height=36,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 12),
                      command=self._export_csv).pack(side="left", padx=(0, 12))

        ctk.CTkButton(btn_row, text="💾 Backup DB", width=140, height=36,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.GREEN, font=("Segoe UI", 12),
                      command=self._backup_db).pack(side="left", padx=(0, 12))

        ctk.CTkButton(btn_row, text="🗑 Reset All Data", width=140, height=36,
                      fg_color="transparent", border_color=theme.RED, border_width=1,
                      text_color=theme.RED, font=("Segoe UI", 12),
                      command=self._reset_data).pack(side="left")

        # ── About ──────────────────────────────────────────────────────────────
        self._section(scroll, row=next_row(), title="About WealthMap",
                      desc="Version and technical info.")

        about_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                  border_width=1, border_color=theme.BORDER)
        about_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))

        info = [
            ("Version",        "3.1 — Local Edition"),
            ("Storage",        f"{self.ctx.data_dir}"),
            ("Database",       "SQLite (local, encrypted-ready)"),
            ("Built with",     "Python · CustomTkinter · SQLAlchemy"),
            ("Exchange rates", "exchangerate-api.com (free tier)"),
            ("Market data",    "Yahoo Finance (yfinance) · CoinGecko"),
        ]
        for lbl, val in info:
            row_f = ctk.CTkFrame(about_card, fg_color="transparent")
            row_f.pack(fill="x", padx=16, pady=4)
            ctk.CTkLabel(row_f, text=lbl, font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         width=160, anchor="w").pack(side="left")
            ctk.CTkLabel(row_f, text=val, font=("Segoe UI", 11), text_color=theme.TEXT_PRI,
                         anchor="w").pack(side="left")
        ctk.CTkLabel(about_card, text="", height=8).pack()

    # ── Profile ──────────────────────────────────────────────────────────────

    def _build_profile_section(self, card):
        for w in card.winfo_children():
            w.destroy()

        profile = self.ctx.profile
        registry = self.ctx.registry

        # Rename
        rename_row = ctk.CTkFrame(card, fg_color="transparent")
        rename_row.pack(fill="x", padx=16, pady=(16, 8))
        ctk.CTkLabel(rename_row, text="Name:", font=("Segoe UI", 12),
                     text_color=theme.TEXT_SEC).pack(side="left")
        name_e = make_entry(rename_row, width=240)
        name_e.insert(0, profile.get("name", ""))
        name_e.pack(side="left", padx=8)

        def save_name():
            new_name = name_e.get().strip()
            if not new_name:
                return
            profile["name"] = new_name
            if registry:
                registry.rename_profile(profile["id"], new_name)
            self.app.title(f"WealthMap — {new_name} "
                           f"({'Business' if self.ctx.is_business else 'Personal'})")
            self._rebuild_card_section(None)

        ctk.CTkButton(rename_row, text="Apply", width=80, height=36,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 12),
                      command=save_name).pack(side="left")

        if registry is None:
            ctk.CTkLabel(card, text="Profile linking is unavailable in this context.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC
                         ).pack(anchor="w", padx=16, pady=(0, 16))
            return

        # Linked profiles
        ctk.CTkLabel(card, text="Linked Profiles", font=("Segoe UI", 12, "bold"),
                     text_color=theme.TEXT_PRI).pack(anchor="w", padx=16, pady=(8, 2))
        ctk.CTkLabel(card, text="Linked profiles can send/receive transfers with this "
                                 f"profile's accounts. Only other {profile['type']} profiles "
                                 "can be linked.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     wraplength=700, justify="left").pack(anchor="w", padx=16, pady=(0, 8))

        linked = registry.linked_profiles(profile["id"])
        linkable = registry.linkable_profiles(profile["id"])

        if linked:
            for lp in linked:
                row = ctk.CTkFrame(card, fg_color=theme.ROW_ALT, corner_radius=6)
                row.pack(fill="x", padx=16, pady=2)
                ctk.CTkLabel(row, text=f"🔗 {lp['name']}", font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="Unlink", width=70, height=26,
                              fg_color="transparent", border_color=theme.RED, border_width=1,
                              text_color=theme.RED, font=("Segoe UI", 11),
                              command=lambda lid=lp["id"]: self._unlink(profile, lid)
                              ).pack(side="right", padx=6, pady=2)
        else:
            ctk.CTkLabel(card, text="Not linked with any other profile yet.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC
                         ).pack(anchor="w", padx=16, pady=(0, 4))

        if linkable:
            ctk.CTkLabel(card, text="Available to link:", font=("Segoe UI", 11, "bold"),
                         text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(8, 2))
            for lp in linkable:
                row = ctk.CTkFrame(card, fg_color=theme.ROW_ALT, corner_radius=6)
                row.pack(fill="x", padx=16, pady=2)
                ctk.CTkLabel(row, text=lp["name"], font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="Link", width=70, height=26,
                              fg_color=theme.ACCENT2, hover_color=theme.BG_SELECTED,
                              text_color="#fff", font=("Segoe UI", 11),
                              command=lambda lid=lp["id"]: self._link(profile, lid)
                              ).pack(side="right", padx=6, pady=2)

        ctk.CTkLabel(card, text="", height=4).pack()

        # Switch profile
        switch_row = ctk.CTkFrame(card, fg_color="transparent")
        switch_row.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkButton(switch_row, text="🔄 Switch Profile", height=36, width=160,
                      font=("Segoe UI", 12), fg_color=theme.ACCENT, hover_color="#1C6FBF",
                      text_color="#fff", command=self.app.switch_profile).pack(side="left")
        ctk.CTkLabel(switch_row, text="Returns to the profile picker.",
                     font=("Segoe UI", 10), text_color=theme.TEXT_SEC).pack(side="left", padx=8)

    def _link(self, profile, other_id):
        try:
            self.ctx.registry.link(profile["id"], other_id)
        except Exception as e:
            messagebox.showerror("Error", str(e), parent=self)
        self._rebuild_card_section(None)

    def _unlink(self, profile, other_id):
        self.ctx.registry.unlink(profile["id"], other_id)
        self._rebuild_card_section(None)



    def _build_categories_section(self, card):
        for w in card.winfo_children():
            w.destroy()

        from src.models.database import CustomCategory
        from src.services.core import TRANSACTION_CATEGORIES
        custom = self.ctx.session.query(CustomCategory).order_by(CustomCategory.name).all()

        if custom:
            for c in custom:
                row_f = ctk.CTkFrame(card, fg_color=theme.ROW_ALT, corner_radius=6)
                row_f.pack(fill="x", padx=16, pady=2)
                ctk.CTkLabel(row_f, text=c.name, font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row_f, text="✕", width=28, height=24,
                              fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                              command=lambda name=c.name: self._remove_category(name)
                              ).pack(side="right", padx=4, pady=2)
            ctk.CTkLabel(card, text="", height=4).pack()
        else:
            ctk.CTkLabel(card, text=f"No custom categories yet — {len(TRANSACTION_CATEGORIES)} built-in "
                                     "categories are always available.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(16, 4))

        add_row = ctk.CTkFrame(card, fg_color="transparent")
        add_row.pack(fill="x", padx=16, pady=(4, 16))
        new_cat_e = make_entry(add_row, "e.g. Pet Care")
        new_cat_e.pack(side="left", fill="x", expand=True, padx=(0, 8))

        def add():
            name = new_cat_e.get().strip()
            if not name:
                return
            try:
                self.ctx.customization.add_category(name)
                new_cat_e.delete(0, "end")
                self._build_categories_section(card)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

        ctk.CTkButton(add_row, text="＋ Add Category", height=36, width=140, font=("Segoe UI", 12),
                      fg_color=theme.ACCENT2, hover_color=theme.BG_SELECTED, text_color="#fff",
                      command=add).pack(side="left")

    def _remove_category(self, name):
        if messagebox.askyesno("Remove Category",
                               f"Remove the custom category '{name}'? Existing transactions "
                               "keep this category text, but it won't appear as a suggestion anymore."):
            self.ctx.customization.remove_category(name)
            self._rebuild_card_section(self._build_categories_section)

    # ── Custom transaction types ────────────────────────────────────────────

    def _build_custom_types_section(self, card):
        for w in card.winfo_children():
            w.destroy()

        from src.services.core import CustomizationService
        custom_types = self.ctx.customization.get_custom_types()

        if custom_types:
            for ct in custom_types:
                row_f = ctk.CTkFrame(card, fg_color=theme.ROW_ALT, corner_radius=6)
                row_f.pack(fill="x", padx=16, pady=2)
                ctk.CTkLabel(row_f, text=ct.name, font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI, width=200, anchor="w").pack(side="left", padx=8, pady=6)
                ctk.CTkLabel(row_f, text=CustomizationService.DIRECTION_LABELS.get(ct.direction, ct.direction),
                             font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                             anchor="w").pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row_f, text="✕", width=28, height=24,
                              fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                              command=lambda cid=ct.id: self._remove_custom_type(cid)
                              ).pack(side="right", padx=4, pady=2)
            ctk.CTkLabel(card, text="", height=4).pack()
        else:
            ctk.CTkLabel(card, text="No custom transaction types yet. WealthMap already covers a "
                                     "wide range of types (income, expenses, transfers, fees, "
                                     "interest, gifts, and more) — add your own for anything else.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         wraplength=700, justify="left").pack(anchor="w", padx=16, pady=(16, 4))

        add_row = ctk.CTkFrame(card, fg_color="transparent")
        add_row.pack(fill="x", padx=16, pady=(4, 16))
        new_type_e = make_entry(add_row, "e.g. Crypto Staking Reward")
        new_type_e.pack(side="left", fill="x", expand=True, padx=(0, 8))
        dir_options = list(CustomizationService.DIRECTION_LABELS.values())
        dir_combo = make_combo(add_row, dir_options, width=240)
        dir_combo.set(dir_options[1])  # default: decreases balance
        dir_combo.pack(side="left", padx=(0, 8))

        def add():
            name = new_type_e.get().strip()
            if not name:
                return
            direction = next((k for k, v in CustomizationService.DIRECTION_LABELS.items()
                              if v == dir_combo.get()), "debit")
            try:
                self.ctx.customization.add_custom_type(name, direction)
                new_type_e.delete(0, "end")
                self._rebuild_card_section(self._build_custom_types_section)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=self)

        ctk.CTkButton(add_row, text="＋ Add Type", height=36, width=120, font=("Segoe UI", 12),
                      fg_color=theme.ACCENT2, hover_color=theme.BG_SELECTED, text_color="#fff",
                      command=add).pack(side="left")

    def _remove_custom_type(self, custom_type_id):
        if messagebox.askyesno("Remove Type",
                               "Remove this custom transaction type? Existing transactions "
                               "keep their recorded label, but it won't be selectable anymore."):
            self.ctx.customization.remove_custom_type(custom_type_id)
            self._rebuild_card_section(self._build_custom_types_section)

    def _rebuild_card_section(self, builder):
        # Simplest way to keep row numbering and card references in sync
        # after an add/remove: destroy everything and rebuild the panel.
        for w in self.winfo_children():
            w.destroy()
        self._build()

    # ── Generic helpers ───────────────────────────────────────────────────────

    def _section(self, parent, row: int, title: str, desc: str = ""):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=0, sticky="ew", pady=(0, 6))
        ctk.CTkLabel(frame, text=title,
                     font=("Segoe UI", 15, "bold"), text_color=theme.TEXT_PRI).pack(anchor="w")
        if desc:
            ctk.CTkLabel(frame, text=desc,
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w")

    def _save_base_currency(self):
        code = self._base_combo.get()
        self.ctx.settings.set("base_currency", code)
        self.app.refresh()
        messagebox.showinfo("Saved", f"Base currency set to {code}")

    def _export_csv(self):
        import csv
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Export transactions",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")]
        )
        if not path:
            return
        try:
            txs = self.ctx.transaction.get_recent(10000)
            with open(path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["Date", "Account", "Type", "Description",
                                 "Category", "Payee", "Amount", "Currency",
                                 "Fees/Taxes", "Status", "Notes"])
                for tx in txs:
                    writer.writerow([
                        tx.transaction_date.strftime("%Y-%m-%d"),
                        tx.account.name if tx.account else "",
                        tx.display_type,
                        tx.description or "",
                        tx.category or "",
                        tx.payee or "",
                        tx.amount,
                        tx.currency.code if tx.currency else "",
                        tx.total_fees_taxes,
                        tx.status.value,
                        tx.notes or "",
                    ])
            messagebox.showinfo("Exported", f"Transactions exported to:\n{path}")
        except Exception as e:
            messagebox.showerror("Export Error", str(e))

    def _backup_db(self):
        import shutil
        from tkinter import filedialog
        src = str(self.ctx.data_dir / "wealthmap.db")
        dst = filedialog.asksaveasfilename(
            title="Save database backup",
            defaultextension=".db",
            initialfile="wealthmap_backup.db",
            filetypes=[("SQLite DB", "*.db"), ("All files", "*.*")]
        )
        if dst:
            shutil.copy2(src, dst)
            messagebox.showinfo("Backup Saved", f"Database backed up to:\n{dst}")

    def _reset_data(self):
        confirm = messagebox.askyesno(
            "⚠️ Reset All Data",
            "This will permanently delete ALL your accounts, transactions, "
            "portfolio, loans, receipts, opportunities, and custom "
            "categories/types.\n\nThis cannot be undone.\n\nAre you absolutely sure?",
            icon="warning"
        )
        if not confirm:
            return
        confirm2 = messagebox.askyesno(
            "Final Confirmation",
            "Last chance — delete everything?",
            icon="warning"
        )
        if not confirm2:
            return
        try:
            from src.models.database import (
                Transaction, Account, PortfolioAsset, AssetTrade,
                PersonalLoan, LoanRepayment, Receipt, Attachment,
                ExchangeRate, AppSettings, TransactionCharge, AssetPriceSnapshot,
                Opportunity, CustomCategory, CustomTransactionType
            )
            for model in [Attachment, TransactionCharge, AssetPriceSnapshot,
                          LoanRepayment, AssetTrade, Receipt, Opportunity,
                          Transaction, PortfolioAsset, PersonalLoan,
                          Account, ExchangeRate, AppSettings,
                          CustomCategory, CustomTransactionType]:
                self.ctx.session.query(model).delete()
            self.ctx.session.commit()
            self.ctx.currency.seed_currencies()
            self.ctx.settings.set("initialized", True)
            self.ctx.settings.set("base_currency", "USD")
            messagebox.showinfo("Reset Complete", "All data has been cleared.")
            self.app.navigate("dashboard")
        except Exception as e:
            messagebox.showerror("Reset Error", str(e))
