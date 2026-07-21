"""
WealthMap – Main Application Window
CustomTkinter shell with sidebar navigation, theme switching, and
responsive layout.
"""

import tkinter as tk
from tkinter import messagebox
import customtkinter as ctk
from datetime import datetime, timezone
from typing import Optional

from src.ui.theme import theme
from src.ui.widgets import LoadingOverlay

ctk.set_appearance_mode(theme.ctk_mode)
ctk.set_default_color_theme("blue")

NAV_ITEMS_PERSONAL = [
    ("🏠",  "Dashboard",    "dashboard"),
    ("🏦",  "Accounts",     "accounts"),
    ("↕",   "Transactions", "transactions"),
    ("📈",  "Portfolio",    "portfolio"),
    ("💸",  "Loans",        "loans"),
    ("🧾",  "Receipts",     "receipts"),
    ("💱",  "Exchange",     "exchange"),
    ("📊",  "Wealth Journey","analytics"),
    ("🎯",  "Opportunities","opportunities"),
    ("📄",  "Reports",      "reports"),
    ("⚙️", "Settings",     "settings"),
]

NAV_ITEMS_BUSINESS = [
    ("🏠",  "Dashboard",    "dashboard"),
    ("🚀",  "Cash Flow",    "cashflow"),
    ("🏦",  "Accounts",     "accounts"),
    ("↕",   "Transactions", "transactions"),
    ("🏢",  "Departments",  "departments"),
    ("📈",  "Portfolio",    "portfolio"),
    ("📑",  "Receivables & Payables", "loans"),
    ("🧾",  "Receipts",     "receipts"),
    ("💱",  "Exchange",     "exchange"),
    ("📊",  "Financial Journey","analytics"),
    ("🎯",  "Opportunities","opportunities"),
    ("📄",  "Reports",      "reports"),
    ("⚙️", "Settings",     "settings"),
]

# Backwards-compatible default (personal) — prefer app.nav_items for an
# instance that knows its profile type.
NAV_ITEMS = NAV_ITEMS_PERSONAL


def get_nav_items(is_business: bool):
    return NAV_ITEMS_BUSINESS if is_business else NAV_ITEMS_PERSONAL


ICON_MAP = {
    "bank":        "🏦",
    "wallet":      "👛",
    "portfolio":   "📈",
    "savings":     "🐷",
    "crypto":      "🪙",
    "cash":        "💵",
    "credit_card": "💳",
}


class WealthMapApp(ctk.CTk):
    def __init__(self, ctx):
        super().__init__()
        self.ctx = ctx
        profile_name = ctx.profile.get("name", "Personal")
        profile_kind = "Business" if ctx.is_business else "Personal"
        self.title(f"WealthMap — {profile_name} ({profile_kind})")
        self.geometry("1400x860")
        self.minsize(1000, 640)
        self.configure(fg_color=theme.BG_DARK)

        self.switch_profile_requested = False
        self.target_profile_id = None
        self.nav_items = get_nav_items(ctx.is_business)
        self._panels = {}
        self._active_nav = None
        self._nav_kwargs = {}

        self._build_layout()
        self._build_sidebar()
        default_panel = self.ctx.settings.get("default_panel", "dashboard")
        valid_keys = {key for _, _, key in self.nav_items}
        self.navigate(default_panel if default_panel in valid_keys else "dashboard")

        # Background rate fetch
        self.after(1500, self.ctx.fetch_rates_background)
        self.after(3000, self._update_status_bar)

        # Google Drive backup: offer to unlock this session (once) if
        # automatic backups are configured, then let the daily trigger
        # check for itself whether it's actually due.
        self.after(2000, self._maybe_prompt_backup_unlock)

        # Ask the window manager to route the close ("X") button through
        # us so an on-close backup can run first, instead of just tearing
        # the window down immediately.
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Responsive: notify current panel on resize
        self.bind("<Configure>", self._on_resize)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)

        self.sidebar_frame = ctk.CTkFrame(
            self, width=220, fg_color=theme.BG_SIDEBAR,
            corner_radius=0, border_width=1, border_color=theme.BORDER
        )
        self.sidebar_frame.grid(row=0, column=0, rowspan=2, sticky="nsew")

        self.content_frame = ctk.CTkFrame(
            self, fg_color=theme.BG_DARK, corner_radius=0
        )
        self.content_frame.grid(row=0, column=1, sticky="nsew", padx=0, pady=0)
        self.content_frame.grid_columnconfigure(0, weight=1)
        self.content_frame.grid_rowconfigure(0, weight=1)

        self.status_bar = ctk.CTkFrame(
            self, height=26, fg_color=theme.BG_CARD, corner_radius=0
        )
        self.status_bar.grid(row=1, column=1, sticky="ew")
        self.status_label = ctk.CTkLabel(
            self.status_bar, text="", text_color=theme.TEXT_SEC, font=("Segoe UI", 11)
        )
        self.status_label.pack(side="left", padx=12)
        self.rate_label = ctk.CTkLabel(
            self.status_bar, text="", text_color=theme.ACCENT, font=("Segoe UI", 11)
        )
        self.rate_label.pack(side="right", padx=12)

    def _build_sidebar(self):
        for w in self.sidebar_frame.winfo_children():
            w.destroy()
        self.sidebar_frame.configure(fg_color=theme.BG_SIDEBAR, border_color=theme.BORDER)
        self.sidebar_frame.pack_propagate(False)

        # Scrollable nav area so it never overflows on short screens
        nav_scroll = ctk.CTkScrollableFrame(
            self.sidebar_frame, fg_color="transparent",
            corner_radius=0, scrollbar_button_color=theme.BORDER
        )
        nav_scroll.pack(fill="both", expand=True)

        # Logo / brand
        logo_frame = ctk.CTkFrame(nav_scroll, fg_color="transparent")
        logo_frame.pack(padx=16, pady=(20, 8), fill="x")
        ctk.CTkLabel(
            logo_frame, text="💰 WealthMap",
            font=("Segoe UI", 20, "bold"), text_color=theme.ACCENT
        ).pack(anchor="w")
        ctk.CTkLabel(
            logo_frame, text=f"{self.ctx.profile.get('name','Personal')} · "
                             f"{'Business' if self.ctx.is_business else 'Personal'}",
            font=("Segoe UI", 11), text_color=theme.TEXT_SEC
        ).pack(anchor="w")

        ctk.CTkButton(
            logo_frame, text="🔀 Switch / New Profile", anchor="w",
            fg_color="transparent", hover_color=theme.BG_HOVER,
            border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
            height=28, command=self._open_profile_switcher
        ).pack(anchor="w", fill="x", pady=(8, 0))

        ctk.CTkFrame(nav_scroll, height=1, fg_color=theme.BORDER).pack(fill="x", padx=12, pady=(4, 12))

        self._nav_buttons = {}
        for icon, label, key in self.nav_items:
            active = (key == self._active_nav)
            btn = ctk.CTkButton(
                nav_scroll,
                text=f"  {icon}  {label}",
                anchor="w",
                fg_color=theme.BG_HOVER if active else "transparent",
                hover_color=theme.BG_HOVER,
                text_color=theme.ACCENT if active else theme.TEXT_SEC,
                font=("Segoe UI", 13),
                height=38,
                corner_radius=8,
                command=lambda k=key: self.navigate(k)
            )
            btn.pack(padx=10, pady=2, fill="x")
            self._nav_buttons[key] = btn

        # Theme toggle
        ctk.CTkFrame(nav_scroll, height=1, fg_color=theme.BORDER).pack(fill="x", padx=12, pady=(12, 8))
        toggle_row = ctk.CTkFrame(nav_scroll, fg_color="transparent")
        toggle_row.pack(fill="x", padx=14, pady=(0, 8))
        ctk.CTkLabel(toggle_row, text="☀ / 🌙  Theme",
                     font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(side="left")
        self._theme_switch = ctk.CTkSwitch(
            toggle_row, text="", width=46, height=22,
            progress_color=theme.ACCENT,
            command=self._toggle_theme
        )
        if theme.mode == "light":
            self._theme_switch.select()
        else:
            self._theme_switch.deselect()
        self._theme_switch.pack(side="right")

        # Net worth widget at bottom of sidebar
        self._nw_frame = ctk.CTkFrame(
            self.sidebar_frame, fg_color=theme.BG_CARD, corner_radius=10,
            cursor="hand2"
        )
        self._nw_frame.pack(side="bottom", padx=12, pady=(8, 16), fill="x")
        ctk.CTkLabel(
            self._nw_frame, text="NET WORTH  •  tap for details",
            font=("Segoe UI", 9, "bold"), text_color=theme.TEXT_SEC
        ).pack(padx=12, pady=(10, 0), anchor="w")
        self._nw_value_label = ctk.CTkLabel(
            self._nw_frame, text="…",
            font=("Segoe UI", 20, "bold"), text_color=theme.GOLD
        )
        self._nw_value_label.pack(padx=12, pady=(0, 10), anchor="w")
        for w in (self._nw_frame, self._nw_value_label):
            w.bind("<Button-1>", lambda e: self.navigate("analytics"))

    # ── Theme ─────────────────────────────────────────────────────────────────

    def _toggle_theme(self):
        theme.toggle()
        self._apply_theme()

    def set_theme(self, mode: str):
        """mode: 'dark' or 'light'"""
        theme.set_mode(mode)
        self._apply_theme()

    def _apply_theme(self):
        ctk.set_appearance_mode(theme.ctk_mode)
        self.ctx.settings.set("theme_mode", theme.mode)
        self.configure(fg_color=theme.BG_DARK)
        self.content_frame.configure(fg_color=theme.BG_DARK)
        self.status_bar.configure(fg_color=theme.BG_CARD)
        self.status_label.configure(text_color=theme.TEXT_SEC)
        self.rate_label.configure(text_color=theme.ACCENT)
        self._build_sidebar()
        self._reload_current_panel()

    # ── Navigation ────────────────────────────────────────────────────────────

    def navigate(self, key: str, **kwargs):
        self._nav_kwargs = kwargs
        # Deactivate old
        if self._active_nav and self._active_nav in self._nav_buttons:
            self._nav_buttons[self._active_nav].configure(
                fg_color="transparent", text_color=theme.TEXT_SEC
            )
        # Activate new
        if key in self._nav_buttons:
            self._nav_buttons[key].configure(
                fg_color=theme.BG_HOVER, text_color=theme.ACCENT
            )
        self._active_nav = key
        self._reload_current_panel()
        self._update_net_worth()

    def _reload_current_panel(self):
        for w in self.content_frame.winfo_children():
            w.destroy()

        label = next((lbl for _, lbl, key in self.nav_items if key == self._active_nav),
                     self._active_nav or "")
        overlay = LoadingOverlay(self.content_frame, label=label)
        overlay.pack(fill="both", expand=True)
        self.update_idletasks()

        self._nav_token = getattr(self, "_nav_token", 0) + 1
        token = self._nav_token

        def finish():
            overlay.stop()
            if token != self._nav_token:
                return  # superseded by a newer navigation before this fired
            for w in self.content_frame.winfo_children():
                w.destroy()
            self._panels = {}
            panel = self._load_panel(self._active_nav, **self._nav_kwargs)
            if panel:
                panel.pack(fill="both", expand=True)
                self._panels[self._active_nav] = panel

        self.after(260, finish)

    def _load_panel(self, key: str, **kwargs):
        # Import lazily to keep startup fast
        if key == "dashboard":
            from src.ui.dashboard import DashboardPanel
            return DashboardPanel(self.content_frame, self.ctx, self)
        elif key == "accounts":
            from src.ui.accounts import AccountsPanel
            return AccountsPanel(self.content_frame, self.ctx, self)
        elif key == "transactions":
            from src.ui.transactions import TransactionsPanel
            return TransactionsPanel(self.content_frame, self.ctx, self, **kwargs)
        elif key == "portfolio":
            from src.ui.portfolio import PortfolioPanel
            return PortfolioPanel(self.content_frame, self.ctx, self)
        elif key == "loans":
            from src.ui.loans import LoansPanel
            return LoansPanel(self.content_frame, self.ctx, self)
        elif key == "receipts":
            from src.ui.receipts import ReceiptsPanel
            return ReceiptsPanel(self.content_frame, self.ctx, self)
        elif key == "exchange":
            from src.ui.exchange import ExchangePanel
            return ExchangePanel(self.content_frame, self.ctx, self)
        elif key == "analytics":
            from src.ui.analytics import AnalyticsPanel
            return AnalyticsPanel(self.content_frame, self.ctx, self, **kwargs)
        elif key == "opportunities":
            from src.ui.opportunities import OpportunitiesPanel
            return OpportunitiesPanel(self.content_frame, self.ctx, self)
        elif key == "departments":
            from src.ui.departments import DepartmentsPanel
            return DepartmentsPanel(self.content_frame, self.ctx, self)
        elif key == "cashflow":
            from src.ui.cashflow import CashFlowPanel
            return CashFlowPanel(self.content_frame, self.ctx, self)
        elif key == "reports":
            from src.ui.reports_panel import ReportsPanel
            return ReportsPanel(self.content_frame, self.ctx, self)
        elif key == "settings":
            from src.ui.settings_panel import SettingsPanel
            return SettingsPanel(self.content_frame, self.ctx, self)
        return None

    # ── Status / Net worth ────────────────────────────────────────────────────

    def _update_net_worth(self):
        try:
            base = self.ctx.settings.get("base_currency", "USD")
            snap = self.ctx.account.net_worth_snapshot(base)
            port = self.ctx.portfolio.portfolio_summary(base)
            loan = self.ctx.loan.summary(base)
            total = snap["total"] + port["total_value"] + loan["owed_to_me"] - loan["i_owe"]
            cur = self.ctx.currency.get_by_code(base)
            sym = cur.symbol if cur else ""
            self._nw_value_label.configure(text=f"{sym}{total:,.2f}")
        except Exception:
            self._nw_value_label.configure(text="—")

    def _update_status_bar(self):
        try:
            last = self.ctx.settings.get("last_rate_fetch")
            if last:
                ts = datetime.fromisoformat(last)
                age = (datetime.now(timezone.utc) - ts.replace(tzinfo=timezone.utc))
                mins = int(age.total_seconds() // 60)
                self.rate_label.configure(text=f"Rates updated {mins}m ago")
            base = self.ctx.settings.get("base_currency", "USD")
            self.status_label.configure(
                text=f"Base currency: {base}  •  {datetime.now().strftime('%d %b %Y')}"
            )
        except Exception:
            pass
        self.after(60_000, self._update_status_bar)

    # ── Responsive ────────────────────────────────────────────────────────────

    def _on_resize(self, event):
        if event.widget is not self:
            return
        panel = self._panels.get(self._active_nav)
        if panel and hasattr(panel, "on_resize"):
            try:
                panel.on_resize(event.width)
            except Exception:
                pass

    def refresh(self):
        """Called by child panels after data mutations."""
        self._update_net_worth()

    # ── Google Drive backup ──────────────────────────────────────────────────

    def _maybe_prompt_backup_unlock(self):
        """If automatic backups are configured (connected + password set +
        at least one trigger on) but not yet unlocked for this run of the
        app: first try a silent, local-only unlock (both generated-key
        modes cache a copy in the OS credential store, so most people —
        anyone who used Quick Connect — never see a prompt at all). If
        that's unavailable and the key is Google-account-managed, fall
        back to fetching it from Drive over the network (still no prompt
        — it only needs the Google sign-in that's already in place). Only
        a manually-chosen password ever needs asking for, once; declining
        just means automatic backups sit out this session."""
        backup = self.ctx.backup
        if not backup:
            return
        if backup.is_unlocked or backup.try_silent_unlock():
            backup.maybe_daily_backup()
            return
        if not (backup.is_connected() and backup.config.has_password and backup.config.triggers):
            return

        if backup.config.get("key_mode") == "google_managed":
            def run():
                backup.try_google_managed_unlock()
                self.after(0, lambda: backup.maybe_daily_backup() if backup.is_unlocked else None)
            import threading
            threading.Thread(target=run, daemon=True).start()
            return

        from src.ui.widgets import Modal
        from src.ui.theme import theme

        modal = Modal(self, "Unlock Google Drive Backups", width=420, height=260)
        ctk.CTkLabel(modal.body, text="Enter your backup password to enable automatic "
                                       "backups for this session. This isn't stored — "
                                       "you'll be asked again next time you open WealthMap.",
                     font=("Segoe UI", 12), text_color=theme.TEXT_SEC,
                     wraplength=360, justify="left").pack(anchor="w", pady=(0, 12))
        from src.ui.widgets import make_entry
        pw_entry = make_entry(modal.body, placeholder="Backup password", show="•")
        pw_entry.pack(fill="x")

        def try_unlock():
            pw = pw_entry.get()
            if not pw:
                return
            try:
                if backup.verify_and_unlock(pw):
                    modal.destroy()
                    backup.maybe_daily_backup()
                else:
                    messagebox.showerror("Incorrect Password",
                                         "That doesn't match your backup password.", parent=modal)
            except Exception as e:
                messagebox.showerror("Error", str(e), parent=modal)

        modal.add_buttons("Unlock", try_unlock, cancel_text="Not now")

    def _on_close(self):
        """Routed here via WM_DELETE_WINDOW so an on-close backup (if
        enabled) gets a chance to run before the window actually goes
        away. Bounded by a short timeout so a slow/failed upload can
        never prevent the app from closing."""
        backup = self.ctx.backup
        if backup and "on_close" in backup.config.triggers and not backup.is_unlocked:
            backup.try_silent_unlock()
            if not backup.is_unlocked and backup.config.get("key_mode") == "google_managed":
                # Worth one network round-trip here since we're about to
                # do network I/O for the backup itself anyway.
                backup.try_google_managed_unlock()
        if backup and "on_close" in backup.config.triggers and backup.is_unlocked:
            overlay = None
            try:
                from src.ui.widgets import LoadingOverlay
                overlay = LoadingOverlay(self.content_frame, label="Backing up to Google Drive")
                overlay.place(relx=0, rely=0, relwidth=1, relheight=1)
                self.update_idletasks()
            except Exception:
                overlay = None
            try:
                backup.backup_on_close_blocking(timeout=8.0)
            except Exception:
                pass
            if overlay:
                try:
                    overlay.stop()
                except Exception:
                    pass
        self.switch_profile_requested = False
        self.target_profile_id = None
        self.withdraw()
        self.update_idletasks()
        self.quit()

    def switch_profile(self):
        """Close this window and return to the profile launcher."""
        self.switch_profile_requested = True
        self.withdraw()
        self.update_idletasks()
        self.quit()

    def switch_to_profile(self, profile_id: str):
        """Close this window and reopen directly on a different profile,
        bypassing the launcher."""
        self.target_profile_id = profile_id
        self.withdraw()
        self.update_idletasks()
        self.quit()

    def _open_profile_switcher(self):
        """Small popup (top-left) listing all profiles to switch to, plus
        options to create a new Personal/Business profile."""
        if not self.ctx.registry:
            messagebox.showinfo("Profiles", "Profile switching isn't available in this context.")
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Switch Profile")
        popup.geometry("300x420")
        popup.configure(fg_color=theme.BG_CARD)
        popup.transient(self)
        try:
            x = self.winfo_rootx() + 16
            y = self.winfo_rooty() + 80
            popup.geometry(f"+{x}+{y}")
        except Exception:
            pass

        scroll = ctk.CTkScrollableFrame(popup, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12, pady=12)

        registry = self.ctx.registry
        current_id = self.ctx.profile["id"]

        for ptype, label in (("personal", "👤 Personal"), ("business", "🏢 Business")):
            profiles = registry.list_profiles(ptype)
            if not profiles:
                continue
            ctk.CTkLabel(scroll, text=label, font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_PRI).pack(anchor="w", pady=(6, 2))
            for p in profiles:
                row = ctk.CTkFrame(scroll, fg_color=theme.BG_HOVER if p["id"] != current_id else theme.BG_SELECTED,
                                   corner_radius=6)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=p["name"], font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI, anchor="w").pack(side="left", padx=8, pady=6)
                if p["id"] == current_id:
                    ctk.CTkLabel(row, text="current", font=("Segoe UI", 10),
                                 text_color=theme.ACCENT).pack(side="right", padx=8)
                else:
                    ctk.CTkButton(row, text="Open", width=60, height=26,
                                  fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                                  font=("Segoe UI", 11),
                                  command=lambda pid=p["id"]: (popup.destroy(), self.switch_to_profile(pid))
                                  ).pack(side="right", padx=6, pady=2)

        ctk.CTkFrame(scroll, height=1, fg_color=theme.BORDER).pack(fill="x", pady=10)

        ctk.CTkLabel(scroll, text="New profile", font=("Segoe UI", 12, "bold"),
                     text_color=theme.TEXT_PRI).pack(anchor="w", pady=(0, 4))

        def new_profile(ptype):
            from src.ui.launcher import quick_create_profile
            profile = quick_create_profile(popup, registry, ptype)
            if profile:
                popup.destroy()
                self.switch_to_profile(profile["id"])

        ctk.CTkButton(scroll, text="＋ New Personal Profile", height=34, font=("Segoe UI", 12),
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT,
                      command=lambda: new_profile("personal")).pack(fill="x", pady=2)
        ctk.CTkButton(scroll, text="＋ New Business Profile", height=34, font=("Segoe UI", 12),
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT,
                      command=lambda: new_profile("business")).pack(fill="x", pady=2)

        ctk.CTkButton(scroll, text="Manage Profiles…", height=34, font=("Segoe UI", 12),
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC,
                      command=lambda: (popup.destroy(), self.switch_profile())
                      ).pack(fill="x", pady=(10, 2))
