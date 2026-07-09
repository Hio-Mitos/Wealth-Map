"""
WealthMap – Profile Launcher
Shown on startup: choose an existing Personal/Business profile to open, or
create a new one. Profiles of the same type can be linked here (or later,
from Settings) to enable cross-profile transfers.
"""

import tkinter as tk
from tkinter import messagebox, simpledialog
import customtkinter as ctk
from datetime import datetime

from src.ui.theme import theme
from src.ui.widgets import make_entry, make_combo, Modal, LoadingOverlay
from src.services.profiles import ProfileRegistry, PROFILE_TYPES

ctk.set_appearance_mode(theme.ctk_mode)
ctk.set_default_color_theme("blue")


class ProfileLauncher(ctk.CTk):
    def __init__(self, registry: ProfileRegistry):
        super().__init__()
        self.registry = registry
        self.selected_profile = None

        self.title("WealthMap — Select Profile")
        self.geometry("980x640")
        self.minsize(720, 480)
        self.configure(fg_color=theme.BG_DARK)
        self._build()

    # ── Layout ───────────────────────────────────────────────────────────

    def _build(self):
        for w in self.winfo_children():
            w.destroy()

        hdr = ctk.CTkFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        hdr.pack(fill="x", padx=32, pady=(28, 8))
        ctk.CTkLabel(hdr, text="💠 WealthMap", font=("Segoe UI", 28, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w")
        ctk.CTkLabel(hdr, text="Choose a profile to open, or create a new one. "
                              "Profiles of the same type can be linked for cross-profile transfers.",
                     font=("Segoe UI", 13), text_color=theme.TEXT_SEC).pack(anchor="w", pady=(2, 0))

        body = ctk.CTkFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        body.pack(fill="both", expand=True, padx=32, pady=(8, 24))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=1)

        self._section(body, "👤 Personal Profiles",
                      "Everyday accounts, budgeting, portfolio & loans.",
                      "personal", 0)
        self._section(body, "🏢 Business Profiles",
                      "Departments, cash-flow command center, AR/AP, and more.",
                      "business", 1)

    def _section(self, parent, title, subtitle, ptype, col):
        outer = ctk.CTkFrame(parent, fg_color=theme.BG_CARD, corner_radius=12,
                             border_width=1, border_color=theme.BORDER)
        outer.grid(row=0, column=col, sticky="nsew",
                  padx=(0 if col == 0 else 8, 8 if col == 0 else 0), pady=4)

        ctk.CTkLabel(outer, text=title, font=("Segoe UI", 16, "bold"),
                     text_color=theme.TEXT_PRI).pack(anchor="w", padx=18, pady=(18, 0))
        ctk.CTkLabel(outer, text=subtitle, font=("Segoe UI", 11),
                     text_color=theme.TEXT_SEC).pack(anchor="w", padx=18, pady=(0, 12))

        scroll = ctk.CTkScrollableFrame(outer, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=12)

        profiles = self.registry.list_profiles(ptype)
        if not profiles:
            ctk.CTkLabel(scroll, text="No profiles yet — create one below.",
                         font=("Segoe UI", 12), text_color=theme.TEXT_SEC
                         ).pack(anchor="w", padx=6, pady=8)
        for p in profiles:
            self._profile_card(scroll, p)

        type_label = "Personal" if ptype == "personal" else "Business"
        ctk.CTkButton(outer, text=f"＋ New {type_label} Profile", height=40,
                      font=("Segoe UI", 13, "bold"),
                      fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                      command=lambda: self._create_profile(ptype)
                      ).pack(fill="x", padx=18, pady=(8, 18))

    def _profile_card(self, parent, p):
        card = ctk.CTkFrame(parent, fg_color=theme.BG_HOVER, corner_radius=10,
                            border_width=1, border_color=theme.BORDER)
        card.pack(fill="x", pady=4, padx=4)

        top = ctk.CTkFrame(card, fg_color="transparent")
        top.pack(fill="x", padx=12, pady=(10, 2))
        ctk.CTkLabel(top, text=p["name"], font=("Segoe UI", 14, "bold"),
                     text_color=theme.TEXT_PRI, anchor="w").pack(side="left")

        sub_parts = []
        try:
            created = datetime.fromisoformat(p.get("created_at", ""))
            sub_parts.append(f"Created {created.strftime('%d %b %Y')}")
        except Exception:
            pass
        linked = self.registry.linked_profiles(p["id"])
        if linked:
            names = ", ".join(lp["name"] for lp in linked)
            sub_parts.append(f"🔗 linked with {names}")
        ctk.CTkLabel(card, text="  •  ".join(sub_parts), font=("Segoe UI", 10),
                     text_color=theme.TEXT_SEC, anchor="w").pack(fill="x", padx=12, pady=(0, 6))

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(btn_row, text="Open", width=80, height=32,
                      fg_color=theme.ACCENT, hover_color="#1C6FBF", text_color="#fff",
                      font=("Segoe UI", 12), command=lambda: self._open(p)
                      ).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="🔗 Links", width=70, height=32,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=lambda: self._manage_links(p)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="✎ Rename", width=80, height=32,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.TEXT_SEC, font=("Segoe UI", 11),
                      command=lambda: self._rename(p)).pack(side="left", padx=(0, 6))
        ctk.CTkButton(btn_row, text="🗑", width=36, height=32,
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.RED, font=("Segoe UI", 12),
                      command=lambda: self._delete(p)).pack(side="left")

    # ── Actions ──────────────────────────────────────────────────────────

    def _open(self, profile):
        self.selected_profile = profile
        self.registry.set_last_opened(profile["id"])

        # Hide immediately so this window doesn't linger as a "ghost" frame
        # while the next window is built, then exit our mainloop. We use
        # quit() rather than destroy(): quit() reliably returns control to
        # main.py even if this window's widget tree can't be fully torn
        # down cleanly (destroy() is attempted afterward, best-effort).
        self.withdraw()
        self.update_idletasks()
        self.quit()

    def _create_profile(self, ptype):
        type_label = "Personal" if ptype == "personal" else "Business"
        name = simpledialog.askstring(f"New {type_label} Profile",
                                      f"Name for this {type_label.lower()} profile:",
                                      parent=self)
        if not name or not name.strip():
            return

        for w in self.winfo_children():
            w.destroy()
        overlay = LoadingOverlay(self, label=f"Creating {name.strip()}")
        overlay.pack(fill="both", expand=True)
        self.update_idletasks()

        try:
            profile = self.registry.create_profile(name.strip(), ptype)
        except Exception as e:
            overlay.stop()
            self._build()
            messagebox.showerror("Error", str(e), parent=self)
            return

        def finish():
            overlay.stop()
            self._build()
            # Offer to link with existing same-type profiles right away.
            linkable = self.registry.linkable_profiles(profile["id"])
            if linkable:
                self._offer_links(profile, linkable)

        self.after(200, finish)

    def _offer_links(self, profile, linkable):
        offer_links_dialog(self, self.registry, profile, linkable,
                          on_done=self._build)

    def _manage_links(self, profile):
        modal = Modal(self, f"Linked Profiles — {profile['name']}", width=460, height=480)
        ctk.CTkLabel(modal.body, text="Linked profiles can send/receive transfers with "
                                       f"this profile's accounts. Only {profile['type']} "
                                       "profiles can be linked together.",
                     font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                     wraplength=400, justify="left").pack(anchor="w", pady=(0, 12))

        linked = self.registry.linked_profiles(profile["id"])
        linkable = self.registry.linkable_profiles(profile["id"])

        if linked:
            ctk.CTkLabel(modal.body, text="Currently linked", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_PRI).pack(anchor="w", pady=(4, 4))
            for lp in linked:
                row = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=6)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=lp["name"], font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="Unlink", width=70, height=26,
                              fg_color="transparent", border_color=theme.RED, border_width=1,
                              text_color=theme.RED, font=("Segoe UI", 11),
                              command=lambda lid=lp["id"]: (
                                  self.registry.unlink(profile["id"], lid),
                                  modal.destroy(), self._manage_links(profile))
                              ).pack(side="right", padx=6, pady=2)

        if linkable:
            ctk.CTkLabel(modal.body, text="Available to link", font=("Segoe UI", 12, "bold"),
                         text_color=theme.TEXT_PRI).pack(anchor="w", pady=(12, 4))
            for lp in linkable:
                row = ctk.CTkFrame(modal.body, fg_color=theme.BG_HOVER, corner_radius=6)
                row.pack(fill="x", pady=2)
                ctk.CTkLabel(row, text=lp["name"], font=("Segoe UI", 12),
                             text_color=theme.TEXT_PRI).pack(side="left", padx=8, pady=6)
                ctk.CTkButton(row, text="Link", width=70, height=26,
                              fg_color=theme.ACCENT2, hover_color=theme.BG_SELECTED,
                              text_color="#fff", font=("Segoe UI", 11),
                              command=lambda lid=lp["id"]: (
                                  self.registry.link(profile["id"], lid),
                                  modal.destroy(), self._manage_links(profile))
                              ).pack(side="right", padx=6, pady=2)

        if not linked and not linkable:
            ctk.CTkLabel(modal.body, text=f"No other {profile['type']} profiles to link with yet.",
                         font=("Segoe UI", 12), text_color=theme.TEXT_SEC
                         ).pack(anchor="w", pady=8)

        modal.add_buttons("Done", lambda: (modal.destroy(), self._build()))

    def _rename(self, profile):
        new_name = simpledialog.askstring("Rename Profile", "New name:",
                                          initialvalue=profile["name"], parent=self)
        if new_name and new_name.strip():
            self.registry.rename_profile(profile["id"], new_name.strip())
            self._build()

    def _delete(self, profile):
        if messagebox.askyesno("Delete Profile",
                               f"Permanently delete '{profile['name']}' and ALL of its data "
                               "(accounts, transactions, portfolio, everything)?\n\n"
                               "This cannot be undone.", icon="warning", parent=self):
            self.registry.delete_profile(profile["id"])
            self._build()


# ── Reusable helpers (also used by the in-app profile switcher) ────────────

def offer_links_dialog(parent, registry: ProfileRegistry, profile, linkable, on_done=None):
    """Show a small dialog offering to link `profile` with other same-type
    profiles. `parent` is any Tk widget/window to use as the dialog's
    parent. Calls `on_done()` (if given) after the dialog closes."""
    modal = Modal(parent, f"Link '{profile['name']}'?", width=420, height=380)
    ctk.CTkLabel(modal.body, text=f"Link '{profile['name']}' with other "
                                   f"{profile['type']} profiles?",
                 font=("Segoe UI", 13, "bold"), text_color=theme.TEXT_PRI,
                 wraplength=360, justify="left").pack(anchor="w", pady=(0, 4))
    ctk.CTkLabel(modal.body, text="Linked profiles can transfer money to each "
                                   "other's accounts. You can change this anytime "
                                   "from Settings.",
                 font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                 wraplength=360, justify="left").pack(anchor="w", pady=(0, 12))

    vars_map = {}
    for lp in linkable:
        var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(modal.body, text=lp["name"], variable=var,
                       font=("Segoe UI", 12), text_color=theme.TEXT_PRI,
                       fg_color=theme.ACCENT).pack(anchor="w", pady=4)
        vars_map[lp["id"]] = var

    def apply_links():
        for lid, var in vars_map.items():
            if var.get():
                registry.link(profile["id"], lid)
        modal.destroy()
        if on_done:
            on_done()

    modal.add_buttons("Save", apply_links)


def quick_create_profile(parent, registry: ProfileRegistry, ptype: str):
    """
    Prompt for a name and create a new, empty profile of the given type
    ('personal' or 'business'). Optionally offers to link it with existing
    same-type profiles. Returns the new profile dict, or None if cancelled.
    """
    type_label = "Personal" if ptype == "personal" else "Business"
    name = simpledialog.askstring(f"New {type_label} Profile",
                                  f"Name for this {type_label.lower()} profile:",
                                  parent=parent)
    if not name or not name.strip():
        return None
    profile = registry.create_profile(name.strip(), ptype)
    linkable = registry.linkable_profiles(profile["id"])
    if linkable:
        offer_links_dialog(parent, registry, profile, linkable)
    return profile
