"""
WealthMap – Settings Panel
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime

from src.ui.widgets import (
    SectionHeader,
    make_entry,
    make_combo,
    Modal,
    CurrencySearchEntry,
    attach_currency_tooltip,
)
from src.ui.theme import theme
from src.services.backup_service import GoogleDriveBackupService


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
                      desc="All balances and net worth are converted to this currency. "
                           "Start typing a code, name, or nickname (e.g. \"dollar\" or "
                           "\"american dollar\") to search.")

        cur_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                border_width=1, border_color=theme.BORDER)
        cur_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))

        crow = ctk.CTkFrame(cur_card, fg_color="transparent")
        crow.pack(fill="x", padx=16, pady=16)

        current_base = self.ctx.settings.get("base_currency", "USD")
        self._base_combo = CurrencySearchEntry(crow, self.ctx, width=220, initial_code=current_base)
        self._base_combo.pack(side="left")
        attach_currency_tooltip(self._base_combo, self.ctx)

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

        # ── Backup & Sync (Google Drive) ─────────────────────────────────────
        self._section(scroll, row=next_row(), title="Backup & Sync",
                      desc="Automatically back up ALL your profiles (accounts, transactions, "
                           "attachments — everything) to your own Google Drive, so you can "
                           "restore them on a new computer.")
        backup_card = ctk.CTkFrame(scroll, fg_color=theme.BG_CARD, corner_radius=12,
                                   border_width=1, border_color=theme.BORDER)
        backup_card.grid(row=next_row(), column=0, sticky="ew", pady=(0, 20))
        self._backup_card = backup_card
        self._build_backup_section(backup_card)

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
        self._base_combo.resolve()  # in case the field still has focus with unresolved search text
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

    # ── Backup & Sync (Google Drive) ────────────────────────────────────────

    def _build_backup_section(self, card):
        for w in card.winfo_children():
            w.destroy()

        backup = self.ctx.backup
        if backup is None:
            ctk.CTkLabel(card, text="Backup isn't available in this context.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC
                         ).pack(anchor="w", padx=16, pady=16)
            return

        # ── Connection status ────────────────────────────────────────────
        status_row = ctk.CTkFrame(card, fg_color="transparent")
        status_row.pack(fill="x", padx=16, pady=(16, 4))
        connected = backup.is_connected()
        status_text = "✅ Connected to Google Drive" if connected else "○ Not connected"
        status_color = theme.GREEN if connected else theme.TEXT_SEC
        ctk.CTkLabel(status_row, text=status_text, font=("Segoe UI", 13, "bold"),
                     text_color=status_color).pack(side="left")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=16, pady=(0, 12))
        if connected:
            mode = backup.config.get("connect_mode")
            mode_label = "Quick Connect" if mode == "quick" else "your own Google Cloud project"
            ctk.CTkLabel(card, text=f"Connected via {mode_label}.", font=("Segoe UI", 11),
                         text_color=theme.TEXT_SEC).pack(anchor="w", padx=16, pady=(0, 8))
            ctk.CTkButton(btn_row, text="Disconnect", width=120, height=32,
                          fg_color="transparent", border_color=theme.RED, border_width=1,
                          text_color=theme.RED, font=("Segoe UI", 11),
                          command=self._gdrive_disconnect).pack(side="left")
        else:
            ctk.CTkLabel(card, text="Backups use your own Google account directly — no "
                                     "Google Drive desktop app needed.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         wraplength=700, justify="left").pack(anchor="w", padx=16, pady=(0, 10))

            quick_col = ctk.CTkFrame(card, fg_color=theme.BG_HOVER, corner_radius=8)
            quick_col.pack(fill="x", padx=16, pady=(0, 8))
            ctk.CTkLabel(quick_col, text="Quick Connect  (recommended)", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_PRI).pack(anchor="w", padx=12, pady=(10, 2))
            ctk.CTkLabel(quick_col, text="Sign in with your Google account — that's it. WealthMap "
                                         "generates and remembers a secure backup key for you, so "
                                         "backups just run automatically from then on.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         wraplength=650, justify="left").pack(anchor="w", padx=12, pady=(0, 8))
            if not GoogleDriveBackupService.is_bundled_client_available():
                ctk.CTkLabel(quick_col, text="First time on this computer: you'll be asked for a "
                                             "client_secret.json once, then never again — not just "
                                             "for you, for anyone else using this install too.",
                             font=("Segoe UI", 10), text_color=theme.TEXT_SEC,
                             wraplength=650, justify="left").pack(anchor="w", padx=12, pady=(0, 6))
            ctk.CTkButton(quick_col, text="Connect Google Drive", width=200, height=34,
                          fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                          font=("Segoe UI", 12), command=self._gdrive_quick_connect
                          ).pack(anchor="w", padx=12, pady=(0, 12))

            adv_col = ctk.CTkFrame(card, fg_color="transparent")
            adv_col.pack(fill="x", padx=16, pady=(0, 4))
            ctk.CTkLabel(adv_col, text="Advanced: use my own Google Cloud project",
                         font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_PRI
                         ).pack(anchor="w", pady=(4, 2))
            ctk.CTkLabel(adv_col, text="For your own isolated OAuth client instead of the shared "
                                       "one — needs a client_secret.json from Google Cloud Console.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         wraplength=650, justify="left").pack(anchor="w", pady=(0, 6))
            ctk.CTkButton(adv_col, text="Connect with my own client_secret.json", height=32,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.ACCENT, font=("Segoe UI", 11),
                          command=self._gdrive_advanced_connect).pack(anchor="w")

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).pack(fill="x", padx=16, pady=8)

        # ── Password / recovery key ──────────────────────────────────────
        key_mode = backup.config.get("key_mode")
        pw_row = ctk.CTkFrame(card, fg_color="transparent")
        pw_row.pack(fill="x", padx=16, pady=4)
        if not backup.config.has_password:
            pw_status, pw_color = "⚠️ No backup password set yet", theme.GOLD
        elif key_mode == "auto":
            pw_status = "🔑 Recovery key" + (
                "  •  remembered on this PC" if backup.is_unlocked else "  •  not readable on this PC")
            pw_color = theme.GREEN if backup.is_unlocked else theme.GOLD
        elif key_mode == "google_managed":
            pw_status = "🔑 Automatic (Google account)" + (
                "  •  remembered on this PC" if backup.is_unlocked else "")
            pw_color = theme.GREEN if backup.is_unlocked else theme.GOLD
        else:
            pw_status = "🔒 Password set" + ("  •  unlocked this session" if backup.is_unlocked else "")
            pw_color = theme.TEXT_PRI
        ctk.CTkLabel(pw_row, text=pw_status, font=("Segoe UI", 12), text_color=pw_color
                     ).pack(side="left")

        pw_btn_row = ctk.CTkFrame(card, fg_color="transparent")
        pw_btn_row.pack(fill="x", padx=16, pady=(0, 12))
        if key_mode == "auto":
            ctk.CTkLabel(card, text="This key is stored securely on this PC only — you won't be "
                                     "asked for it here again. To restore on a *different* PC "
                                     "you'll need the recovery key shown when you first connected.",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC,
                         wraplength=700, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        elif key_mode == "google_managed":
            ctk.CTkLabel(card, text="Restoring on any PC just needs signing into this same Google "
                                     "account — no key to save. Anyone with access to that account "
                                     "can also read your backups; see the README if you'd rather "
                                     "switch to a separate recovery key.",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC,
                         wraplength=700, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
        else:
            ctk.CTkLabel(card, text="Backups are encrypted with this password before they leave "
                                     "your computer — WealthMap never stores it, so write it down "
                                     "somewhere safe. You'll need it to restore on a new PC.",
                         font=("Segoe UI", 10), text_color=theme.TEXT_SEC,
                         wraplength=700, justify="left").pack(anchor="w", padx=16, pady=(0, 8))
            if backup.config.has_password and not backup.is_unlocked:
                ctk.CTkButton(pw_btn_row, text="Unlock This Session", width=160, height=32,
                              fg_color="transparent", border_color=theme.BORDER, border_width=1,
                              text_color=theme.ACCENT, font=("Segoe UI", 11),
                              command=self._gdrive_unlock).pack(side="left", padx=(0, 8))

        # Always available, in every mode — this is the answer to "can I
        # change this later": yes, at any time, to any of the three.
        ctk.CTkButton(pw_btn_row,
                      text="Change How Backups Are Protected" if backup.config.has_password
                           else "Set Up Backup Protection",
                      height=32, fg_color="transparent",
                      border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11),
                      command=self._gdrive_change_protection).pack(side="left")

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).pack(fill="x", padx=16, pady=8)

        # ── Triggers (multiple can be on at once) ───────────────────────────
        ctk.CTkLabel(card, text="Back up automatically when:", font=("Segoe UI", 12, "bold"),
                     text_color=theme.TEXT_PRI).pack(anchor="w", padx=16, pady=(4, 4))
        trig_frame = ctk.CTkFrame(card, fg_color="transparent")
        trig_frame.pack(fill="x", padx=16, pady=(0, 8))

        current_triggers = set(backup.config.triggers)
        self._trigger_vars = {}
        trigger_labels = [
            ("on_change", "My data changes (a minute or so after the last edit)"),
            ("daily",     "Once a day"),
            ("on_close",  "I close WealthMap"),
        ]
        for key, label in trigger_labels:
            var = tk.BooleanVar(value=key in current_triggers)
            ctk.CTkCheckBox(trig_frame, text=label, variable=var,
                           font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
                           fg_color=theme.ACCENT).pack(anchor="w", pady=3)
            self._trigger_vars[key] = var

        ctk.CTkButton(card, text="Save", width=100, height=32,
                      fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                      font=("Segoe UI", 11),
                      command=self._gdrive_save_triggers).pack(anchor="w", padx=16, pady=(0, 12))

        ctk.CTkFrame(card, height=1, fg_color=theme.BORDER).pack(fill="x", padx=16, pady=8)

        # ── Manual backup + status ──────────────────────────────────────────
        last_at = backup.config.get("last_backup_at")
        last_err = backup.config.get("last_backup_error")
        if last_at:
            try:
                dt = datetime.fromisoformat(last_at)
                last_text = f"Last backup: {dt.strftime('%d %b %Y, %H:%M')} UTC"
            except Exception:
                last_text = f"Last backup: {last_at}"
        else:
            last_text = "No backup has been made yet."
        ctk.CTkLabel(card, text=last_text, font=("Segoe UI", 11), text_color=theme.TEXT_SEC
                     ).pack(anchor="w", padx=16, pady=(4, 0))
        if last_err:
            ctk.CTkLabel(card, text=f"Last attempt failed: {last_err}", font=("Segoe UI", 11),
                         text_color=theme.RED, wraplength=700, justify="left"
                         ).pack(anchor="w", padx=16, pady=(2, 0))

        self._backup_progress = ctk.CTkProgressBar(card, height=6, progress_color=theme.ACCENT)
        self._backup_progress.set(0)

        self._backup_status_label = ctk.CTkLabel(card, text="", font=("Segoe UI", 11),
                                                  text_color=theme.ACCENT)
        self._backup_status_label.pack(anchor="w", padx=16, pady=(4, 0))

        backup.set_status_callback(self._on_backup_status)
        if backup.is_running:
            self._show_backup_progress(True)
            self._set_backup_status("Backing up…")

        manual_row = ctk.CTkFrame(card, fg_color="transparent")
        manual_row.pack(fill="x", padx=16, pady=(8, 16))
        ctk.CTkButton(manual_row, text="⬆ Back Up Now", width=140, height=36,
                      fg_color=theme.ACCENT2, hover_color=theme.BG_SELECTED, text_color="#fff",
                      font=("Segoe UI", 12), command=self._gdrive_backup_now).pack(side="left")
        ctk.CTkLabel(manual_row, text="Restoring a backup (e.g. on a new PC) is done from the "
                                       "profile picker screen — use Switch Profile below, then "
                                       "\"Restore from Google Drive\" there.",
                     font=("Segoe UI", 10), text_color=theme.TEXT_SEC,
                     wraplength=520, justify="left").pack(side="left", padx=12)

    def _gdrive_quick_connect(self):
        """One click, every time after the first: sign in with Google via
        the bundled shared client, then — if no password/key exists yet —
        auto-generate a recovery key, show it once, and turn on sensible
        default triggers. The very first time on a given install, there's
        no bundled client yet, so this asks for a client_secret.json once
        and installs it as that shared client before continuing — nobody,
        including colleagues afterwards, has to do that step again."""
        backup = self.ctx.backup

        if not GoogleDriveBackupService.is_bundled_client_available():
            from tkinter import filedialog
            messagebox.showinfo(
                "One-Time Setup",
                "Since this is the first time Quick Connect is being used on this "
                "install, pick the client_secret.json from your Google Cloud project "
                "next. After this, Quick Connect is just \"sign in\" — for you and "
                "anyone else using WealthMap here.",
                parent=self
            )
            path = filedialog.askopenfilename(
                title="Select your Google OAuth client_secret.json",
                filetypes=[("JSON", "*.json"), ("All files", "*.*")]
            )
            if not path:
                return
            try:
                GoogleDriveBackupService.install_bundled_client(path)
            except Exception as e:
                messagebox.showerror("Setup Failed", str(e), parent=self)
                return
            self._rebuild_backup_section()

        self._set_backup_status("Opening browser to sign in to Google…")

        def run():
            try:
                backup.connect_quick()
            except Exception as e:
                msg = str(e)
                self.after(0, lambda: messagebox.showerror("Connection Failed", msg, parent=self))
                return
            self.after(0, self._after_quick_connect)

        import threading
        threading.Thread(target=run, daemon=True).start()

    def _after_quick_connect(self):
        backup = self.ctx.backup
        if not backup.config.has_password:
            self._gdrive_change_protection(first_time=True)
        else:
            self._rebuild_backup_section()

    def _gdrive_change_protection(self, first_time: bool = False):
        """Lets the person choose (or change, any time later — not just
        on first connect) how backups get protected: tied to their Google
        account only, a separate recovery key, or a plain manual password.
        Switching modes takes effect on the *next* backup onward; it
        doesn't touch backups already sitting in Drive, which still need
        whatever protected them at the time."""
        from src.services.backup_service import DEFAULT_QUICK_CONNECT_TRIGGERS
        backup = self.ctx.backup
        title = "How Should Restoring Work?" if first_time else "Change Backup Protection"
        modal = Modal(self, title, width=480, height=520)
        if not first_time:
            ctk.CTkLabel(modal.body, text="This changes how future backups are protected. "
                                           "Backups already in Drive still need whatever "
                                           "protected them when they were made.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         wraplength=420, justify="left").pack(anchor="w", pady=(0, 12))

        auto_col = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
        auto_col.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(auto_col, text="Automatic — my Google account only  (recommended)",
                     font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_PRI
                     ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(auto_col, text="Restoring on a new PC needs nothing but signing into this "
                                     "same Google account — no key to save. Trade-off: anyone "
                                     "who ever gains access to this Google account can also "
                                     "read your backups.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     wraplength=420, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        key_col = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
        key_col.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(key_col, text="Recovery key — separate secret",
                     font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_PRI
                     ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(key_col, text="WealthMap generates a key and shows it to you once. "
                                    "Restoring on a new PC needs the Google account AND that "
                                    "key — a compromised Google account alone can't expose "
                                    "your data.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     wraplength=420, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        manual_col = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=8)
        manual_col.pack(fill="x", pady=(0, 10))
        ctk.CTkLabel(manual_col, text="Manual password — you choose it",
                     font=("Segoe UI", 12, "bold"), text_color=theme.TEXT_PRI
                     ).pack(anchor="w", padx=12, pady=(10, 2))
        ctk.CTkLabel(manual_col, text="Pick your own password. Nothing is remembered for you — "
                                       "you'll re-enter it once per session for automatic "
                                       "backups to run, and to restore anywhere.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     wraplength=420, justify="left").pack(anchor="w", padx=12, pady=(0, 10))

        def finish_common():
            if first_time:
                backup.config.set_triggers(DEFAULT_QUICK_CONNECT_TRIGGERS)
            self._rebuild_backup_section()

        def choose_auto():
            try:
                backup.enable_google_managed_key()
            except Exception as e:
                messagebox.showerror("Couldn't Finish Setup", str(e), parent=modal)
                return
            modal.destroy()
            finish_common()

        def choose_key():
            try:
                recovery_key = backup.generate_and_store_key()
            except Exception as e:
                messagebox.showerror("Couldn't Finish Setup", str(e), parent=modal)
                return
            modal.destroy()
            self._show_recovery_key(recovery_key)
            finish_common()

        def choose_manual():
            modal.destroy()
            self._gdrive_set_password(after=finish_common)

        ctk.CTkButton(auto_col, text="Use Automatic", height=32,
                      fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                      font=("Segoe UI", 11), command=choose_auto
                      ).pack(anchor="w", padx=12, pady=(0, 12))
        ctk.CTkButton(key_col, text="Use Recovery Key", height=32,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11), command=choose_key
                      ).pack(anchor="w", padx=12, pady=(0, 12))
        ctk.CTkButton(manual_col, text="Use Manual Password", height=32,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, font=("Segoe UI", 11), command=choose_manual
                      ).pack(anchor="w", padx=12, pady=(0, 12))

    def _show_recovery_key(self, recovery_key: str):
        modal = Modal(self, "Save Your Recovery Key", width=460, height=340)
        ctk.CTkLabel(modal.body, text="Backups on this PC will now happen automatically — you "
                                       "won't be asked for anything else here.",
                     font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                     wraplength=400, justify="left").pack(anchor="w", pady=(0, 12))
        ctk.CTkLabel(modal.body, text="But to restore this on a DIFFERENT PC, you'll need this "
                                       "recovery key. WealthMap can't show it to you again after "
                                       "this — save it somewhere safe now (a password manager, a "
                                       "note somewhere secure, etc.).",
                     font=("Segoe UI", 12, "bold"), text_color=theme.GOLD,
                     wraplength=400, justify="left").pack(anchor="w", pady=(0, 12))

        key_box = make_entry(modal.body)
        key_box.insert(0, recovery_key)
        key_box.configure(state="readonly")
        key_box.pack(fill="x", pady=(0, 8))

        def copy_key():
            self.clipboard_clear()
            self.clipboard_append(recovery_key)
            copy_btn.configure(text="Copied ✓")

        copy_btn = ctk.CTkButton(modal.body, text="Copy to Clipboard", height=32,
                                 fg_color="transparent", border_color=theme.BORDER, border_width=1,
                                 text_color=theme.ACCENT, font=("Segoe UI", 11), command=copy_key)
        copy_btn.pack(anchor="w")

        confirm_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(modal.body, text="I've saved this recovery key somewhere safe",
                        variable=confirm_var, font=("Segoe UI", 12),
                        text_color=theme.TEXT_PRI, fg_color=theme.ACCENT
                        ).pack(anchor="w", pady=(16, 0))

        def finish():
            if not confirm_var.get():
                messagebox.showinfo("Hold on", "Please confirm you've saved the recovery key first.",
                                    parent=modal)
                return
            modal.destroy()

        # A single "Done" button — deliberately no separate Cancel, since
        # this key is shown exactly once and skipping past it unsaved
        # would be easy to regret later.
        ctk.CTkButton(
            modal.footer, text="Done", command=finish,
            fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
            text_color="#fff", font=("Segoe UI", 13, "bold"),
            height=36, width=140
        ).pack(side="right", padx=16, pady=12)

    def _gdrive_advanced_connect(self):
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Select your Google OAuth client_secret.json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")]
        )
        if not path:
            return
        backup = self.ctx.backup
        self._set_backup_status("Opening browser to sign in to Google…")

        def done(err):
            if err:
                self.after(0, lambda: messagebox.showerror("Connection Failed", str(err), parent=self))
            else:
                self.after(0, lambda: self._rebuild_backup_section())

        def run():
            try:
                backup.connect(path, mode="advanced")
                done(None)
            except Exception as e:
                done(e)

        import threading
        threading.Thread(target=run, daemon=True).start()

    def _gdrive_disconnect(self):
        if not messagebox.askyesno("Disconnect Google Drive",
                                   "Stop backing up to this Google account? Existing backups "
                                   "already on Drive are not deleted.", parent=self):
            return
        self.ctx.backup.disconnect()
        self._rebuild_backup_section()

    def _gdrive_set_password(self, after=None):
        modal = Modal(self, "Set Backup Password", width=420, height=300)
        ctk.CTkLabel(modal.body, text="Choose a password to encrypt your backups with. "
                                       "WealthMap never stores it — you'll need it again "
                                       "to restore on a new PC, so keep it somewhere safe.",
                     font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                     wraplength=360, justify="left").pack(anchor="w", pady=(0, 12))
        pw1 = make_entry(modal.body, placeholder="New password", show="•")
        pw1.pack(fill="x", pady=(0, 8))
        pw2 = make_entry(modal.body, placeholder="Confirm password", show="•")
        pw2.pack(fill="x")

        def save():
            p1, p2 = pw1.get(), pw2.get()
            if not p1:
                messagebox.showerror("Error", "Password can't be empty.", parent=modal)
                return
            if p1 != p2:
                messagebox.showerror("Error", "Passwords don't match.", parent=modal)
                return
            # Switching away from a generated/remembered key onto a
            # manual one — drop the old one from the OS credential store
            # so it's not left behind pointing at a password that's no
            # longer current.
            self.ctx.backup.clear_stored_key()
            self.ctx.backup.set_password(p1)
            modal.destroy()
            if after:
                after()
            else:
                self._rebuild_backup_section()

        modal.add_buttons("Save", save)

    def _gdrive_unlock(self):
        modal = Modal(self, "Unlock Backups", width=400, height=220)
        ctk.CTkLabel(modal.body, text="Enter your backup password to unlock automatic "
                                       "backups for this session.",
                     font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                     wraplength=340, justify="left").pack(anchor="w", pady=(0, 12))
        pw = make_entry(modal.body, placeholder="Backup password", show="•")
        pw.pack(fill="x")

        def try_unlock():
            try:
                if self.ctx.backup.verify_and_unlock(pw.get()):
                    modal.destroy()
                    self._rebuild_backup_section()
                else:
                    messagebox.showerror("Incorrect Password", "That doesn't match.", parent=modal)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Unlock", try_unlock, cancel_text="Cancel")

    def _gdrive_save_triggers(self):
        selected = [k for k, v in self._trigger_vars.items() if v.get()]
        self.ctx.backup.config.set_triggers(selected)
        if selected and not self.ctx.backup.is_unlocked and self.ctx.backup.config.has_password:
            messagebox.showinfo("Saved", "Triggers saved. Unlock this session (below) so "
                                          "automatic backups can actually run.", parent=self)
        self._rebuild_backup_section()

    def _gdrive_backup_now(self):
        backup = self.ctx.backup
        if not backup.is_connected():
            messagebox.showinfo("Not Connected", "Connect Google Drive first.", parent=self)
            return
        if not backup.is_unlocked:
            if not backup.config.has_password:
                messagebox.showinfo("No Password Set", "Set a backup password first.", parent=self)
                return
            self._gdrive_unlock()
            if not backup.is_unlocked:
                return

        self._set_backup_status("Backing up…")
        self._show_backup_progress(True)

        def done(err):
            if err:
                msg = str(err)
                self.after(0, lambda: messagebox.showerror("Backup Failed", msg, parent=self))
            self.after(0, self._show_backup_progress, False)
            self.after(0, self._rebuild_backup_section)

        backup.backup_now_async(on_done=done)

    def _on_backup_status(self, msg: str):
        """Called from the backup service's background thread — must hop
        back onto the main thread before touching any Tk widget."""
        self.after(0, lambda: self._set_backup_status(msg))

    def _set_backup_status(self, text):
        if hasattr(self, "_backup_status_label"):
            try:
                self._backup_status_label.configure(text=text)
            except Exception:
                pass

    def _show_backup_progress(self, active: bool):
        bar = getattr(self, "_backup_progress", None)
        if bar is None:
            return
        try:
            if active:
                bar.pack(fill="x", padx=16, pady=(4, 0))
                bar.configure(mode="indeterminate")
                bar.start()
            else:
                bar.stop()
                bar.pack_forget()
        except Exception:
            pass

    def _rebuild_backup_section(self):
        if getattr(self, "_backup_card", None) is not None:
            try:
                self._build_backup_section(self._backup_card)
                return
            except Exception:
                pass
        # Fallback: just rebuild the whole panel
        for w in self.winfo_children():
            w.destroy()
        self._build()
