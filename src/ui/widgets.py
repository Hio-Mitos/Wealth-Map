"""
WealthMap – Shared UI Widgets
All colours are resolved from `theme` at *construction time* — rebuilding a
panel after a theme switch automatically re-applies the new palette.
"""

import tkinter as tk
import customtkinter as ctk
from typing import Callable, Optional, List, Tuple

from src.ui.theme import theme

# Re-export so existing `from src.ui.widgets import BG_DARK` style imports in
# legacy code still resolve at *import* time to *something* — but all new
# code should use `from src.ui.theme import theme` and `theme.BG_DARK`.
# These module-level names are intentionally NOT used internally anymore.


def fmt_money(amount: float, symbol: str = "", decimals: int = 2) -> str:
    sign = "-" if amount < 0 else ""
    return f"{sign}{symbol}{abs(amount):,.{decimals}f}"


def fmt_money_base(ctx, amount: float, currency_code: str, decimals: int = 2) -> str:
    """
    Format `amount` in its own currency, and if that currency differs from
    the user's base currency, append the converted equivalent in
    parentheses, e.g. "€92.50 (≈ $100.00)" — unless the user has turned this
    off in Settings (show_base_equivalents).
    """
    cur = ctx.currency.get_by_code(currency_code) if currency_code else None
    sym = cur.symbol if cur else ""
    text = fmt_money(amount, sym, decimals)

    if not ctx.settings.get("show_base_equivalents", True):
        return text

    base = ctx.settings.get("base_currency", "USD")
    if not currency_code or currency_code == base:
        return text

    converted = ctx.currency.convert(amount, currency_code, base)
    if converted is None:
        return text
    base_cur = ctx.currency.get_by_code(base)
    base_sym = base_cur.symbol if base_cur else ""
    return f"{text}  (≈ {fmt_money(converted, base_sym, decimals)})"


def color_for_amount(amount: float) -> str:
    if amount > 0:
        return theme.GREEN
    elif amount < 0:
        return theme.RED
    return theme.TEXT_SEC


# ── Tooltip ───────────────────────────────────────────────────────────────────

class Tooltip:
    """
    Lightweight hover tooltip. Attach to any widget:
        Tooltip(widget, lambda: "dynamic text")
    The text function is called fresh on every hover, so it can reflect
    a combobox's current selection.
    """
    def __init__(self, widget, text_fn: Callable[[], str], delay_ms: int = 350):
        self.widget = widget
        self.text_fn = text_fn
        self.delay = delay_ms
        self._after_id = None
        self._tip = None
        widget.bind("<Enter>", self._schedule, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<Destroy>", self._hide, add="+")

    def _schedule(self, event=None):
        self._cancel()
        self._after_id = self.widget.after(self.delay, self._show)

    def _cancel(self):
        if self._after_id:
            try:
                self.widget.after_cancel(self._after_id)
            except Exception:
                pass
            self._after_id = None

    def _show(self):
        text = ""
        try:
            text = self.text_fn()
        except Exception:
            text = ""
        if not text:
            return
        try:
            x = self.widget.winfo_rootx() + 12
            y = self.widget.winfo_rooty() + self.widget.winfo_height() + 6
        except Exception:
            return
        self._hide()
        self._tip = tk.Toplevel(self.widget)
        self._tip.wm_overrideredirect(True)
        self._tip.wm_geometry(f"+{x}+{y}")
        self._tip.attributes("-topmost", True)
        frame = tk.Frame(self._tip, bg=theme.BG_HOVER,
                         highlightbackground=theme.BORDER, highlightthickness=1)
        frame.pack()
        tk.Label(frame, text=text, bg=theme.BG_HOVER, fg=theme.TEXT_PRI,
                font=("Segoe UI", 9), justify="left", padx=8, pady=4).pack()

    def _hide(self, event=None):
        self._cancel()
        if self._tip is not None:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


def currency_tooltip_text(ctx, code: str) -> str:
    """Build 'Country • Common Name' tooltip text for a currency code."""
    cur = ctx.currency.get_by_code(code)
    if not cur:
        return ""
    parts = []
    if cur.country:
        parts.append(cur.country)
    if cur.common_name:
        parts.append(f"a.k.a. {cur.common_name}")
    if not parts:
        return cur.name
    return f"{cur.name}\n" + "  •  ".join(parts)


def attach_currency_tooltip(combo: ctk.CTkComboBox, ctx):
    """Attach a hover tooltip to a currency combobox showing country & nickname."""
    Tooltip(combo, lambda: currency_tooltip_text(ctx, combo.get()))


# ── Searchable Currency Picker ──────────────────────────────────────────────────

# Extra search terms for currencies whose common nationality adjective
# doesn't literally appear in their code/name/common_name/country text —
# e.g. "american" doesn't appear anywhere in USD's data (country is
# "United States"), so without this, typing "american dollar" would find
# nothing. Deliberately not exhaustive: currencies not listed here still
# search fine by code, name, common nickname, and country as-is (e.g.
# "Naira" or "Nigeria" both already find NGN with no alias needed).
CURRENCY_SEARCH_ALIASES = {
    "USD": ["american", "usa", "us"],
    "EUR": ["european", "europe"],
    "GBP": ["british", "britain", "england", "english", "uk"],
    "JPY": ["japanese"],
    "CHF": ["swiss"],
    "CAD": ["canadian"],
    "AUD": ["australian"],
    "NZD": ["kiwi"],
    "CNY": ["chinese", "china", "renminbi", "rmb"],
    "INR": ["indian"],
    "ZAR": ["south african"],
    "MXN": ["mexican"],
    "BRL": ["brazilian"],
    "RUB": ["russian"],
    "KRW": ["korean", "south korean"],
    "SAR": ["saudi"],
    "AED": ["emirati", "dubai"],
    "TRY": ["turkish"],
    "SGD": ["singaporean"],
    "HKD": ["hong konger"],
    "SEK": ["swedish"],
    "NOK": ["norwegian"],
    "DKK": ["danish"],
    "PLN": ["polish"],
    "THB": ["thai"],
    "IDR": ["indonesian"],
    "MYR": ["malaysian"],
    "VND": ["vietnamese"],
    "PHP": ["filipino", "philippine"],
    "NGN": ["nigerian"],
    "KES": ["kenyan"],
    "EGP": ["egyptian"],
    "ILS": ["israeli"],
    "PKR": ["pakistani"],
    "BDT": ["bangladeshi"],
}


class CurrencySearchEntry(ctk.CTkEntry):
    """
    A currency picker styled like a normal text field, with live
    search-as-you-type across each currency's code, official name, common
    nickname, issuing country, and a few nationality aliases (see
    CURRENCY_SEARCH_ALIASES) — so typing "dollar" surfaces every
    dollar-named currency, "USD" finds it directly, and "american dollar"
    narrows the list to just USD.

    `.get()` always returns a plain, valid currency code (never
    unresolved free text) and `.set(code)` sets it — a drop-in
    replacement anywhere a `make_combo([...codes...])` was used for
    currency selection.
    """
    _MAX_VISIBLE_ROWS = 8

    def __init__(self, parent, ctx, width: int = 160, initial_code: Optional[str] = None,
                 on_pick: Optional[Callable[[str], None]] = None, **kw):
        self._ctx = ctx
        self._on_pick = on_pick
        self._currencies = list(ctx.currency.get_all())  # already ordered by code
        self._by_code = {c.code: c for c in self._currencies}
        self._current_code = initial_code if initial_code in self._by_code else (
            self._currencies[0].code if self._currencies else "")

        super().__init__(
            parent, width=width, height=36,
            fg_color=theme.BG_INPUT, border_color=theme.BORDER,
            text_color=theme.TEXT_PRI, placeholder_text_color=theme.TEXT_SEC,
            font=("Segoe UI", 12), **kw
        )
        if self._current_code:
            self.insert(0, self._current_code)

        self._popup = None
        self._filtered: List = []
        self._highlight_idx = -1

        self.bind("<KeyRelease>", self._on_key, add="+")
        self.bind("<FocusIn>", self._on_focus_in, add="+")
        self.bind("<FocusOut>", self._on_focus_out, add="+")
        self.bind("<Down>", self._on_arrow_down, add="+")
        self.bind("<Up>", self._on_arrow_up, add="+")
        self.bind("<Return>", self._on_return, add="+")
        self.bind("<Escape>", self._on_escape, add="+")
        self.bind("<Destroy>", lambda e: self._close_popup(), add="+")

    # ── Public API ───────────────────────────────────────────────────────

    def get(self) -> str:
        return self._current_code

    def set(self, code: str):
        cur = self._by_code.get(code)
        if not cur:
            return
        self._current_code = code
        self.delete(0, "end")
        self.insert(0, code)
        self._close_popup()

    def resolve(self):
        """Forces whatever's currently typed to resolve to a valid code
        (best match, or reverts to the last valid one) without waiting
        for the field to lose focus first. Call this before reading
        .get() from a button handler (e.g. Save) in case the field still
        has focus with unresolved search text in it."""
        self._validate_and_close()

    def raw_text(self) -> str:
        """The literal text currently typed in the field (may not be a
        valid code yet, e.g. mid-search)."""
        return ctk.CTkEntry.get(self)

    # ── Search / ranking ─────────────────────────────────────────────────

    def _haystack(self, cur) -> str:
        parts = [cur.code, cur.name, cur.common_name or "", cur.country or ""]
        parts.extend(CURRENCY_SEARCH_ALIASES.get(cur.code, []))
        return " ".join(parts).lower()

    def _rank(self, cur, query_lower: str, words: List[str]) -> Optional[int]:
        haystack = self._haystack(cur)
        if not all(w in haystack for w in words):
            return None
        if cur.code.lower() == query_lower:
            return 0
        if cur.code.lower().startswith(query_lower):
            return 1
        if cur.name.lower().startswith(query_lower):
            return 2
        if (cur.common_name or "").lower().startswith(query_lower):
            return 3
        return 4

    def _filter(self, query: str) -> List:
        query = query.strip()
        if not query:
            return self._currencies
        words = query.lower().split()
        scored = []
        for cur in self._currencies:
            rank = self._rank(cur, query.lower(), words)
            if rank is not None:
                scored.append((rank, cur.code, cur))
        scored.sort(key=lambda t: (t[0], t[1]))
        return [t[2] for t in scored]

    # ── Popup ────────────────────────────────────────────────────────────

    def _on_key(self, event=None):
        if event is not None and event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        self._filtered = self._filter(self.raw_text())
        self._highlight_idx = 0 if self._filtered else -1
        self._render_popup()

    def _on_focus_in(self, event=None):
        try:
            self.select_range(0, "end")
        except Exception:
            pass
        self._filtered = self._filter(self.raw_text())
        self._highlight_idx = 0 if self._filtered else -1
        self._render_popup()

    def _on_focus_out(self, event=None):
        # Delay so a click on a popup row (which briefly steals focus)
        # gets to fire its own handler first.
        try:
            self.after(150, self._validate_and_close)
        except Exception:
            self._close_popup()

    def _validate_and_close(self):
        typed = self.raw_text()
        if typed != self._current_code:
            filtered = self._filter(typed)
            if typed and filtered:
                self.set(filtered[0].code)
            else:
                self.set(self._current_code)
        self._close_popup()

    def _on_arrow_down(self, event=None):
        if not self._popup:
            self._on_key()
            return "break"
        self._highlight_idx = min(self._highlight_idx + 1,
                                  min(len(self._filtered), self._MAX_VISIBLE_ROWS) - 1)
        self._render_popup()
        return "break"

    def _on_arrow_up(self, event=None):
        if not self._popup:
            return "break"
        self._highlight_idx = max(self._highlight_idx - 1, 0)
        self._render_popup()
        return "break"

    def _on_return(self, event=None):
        if self._filtered:
            idx = max(self._highlight_idx, 0)
            self._pick(self._filtered[idx].code)
        return "break"

    def _on_escape(self, event=None):
        self.set(self._current_code)
        self._close_popup()
        return "break"

    def _pick(self, code: str):
        self.set(code)
        if self._on_pick:
            try:
                self._on_pick(code)
            except Exception:
                pass

    def _render_popup(self):
        self._close_popup()
        if not self._filtered:
            return
        try:
            x = self.winfo_rootx()
            y = self.winfo_rooty() + self.winfo_height()
        except Exception:
            return

        self._popup = tk.Toplevel(self)
        self._popup.wm_overrideredirect(True)
        self._popup.wm_geometry(f"+{x}+{y}")
        try:
            self._popup.attributes("-topmost", True)
        except Exception:
            pass

        outer = tk.Frame(self._popup, bg=theme.BORDER, highlightthickness=0)
        outer.pack()
        inner = tk.Frame(outer, bg=theme.BG_CARD)
        inner.pack(padx=1, pady=1)

        shown = self._filtered[:self._MAX_VISIBLE_ROWS]
        for i, cur in enumerate(shown):
            is_hl = (i == self._highlight_idx)
            row_bg = theme.BG_SELECTED if is_hl else theme.BG_CARD
            label_text = f"{cur.code}  —  {cur.name}"
            if cur.common_name:
                label_text += f"  ({cur.common_name})"
            row = tk.Frame(inner, bg=row_bg, cursor="hand2")
            row.pack(fill="x")
            lbl = tk.Label(row, text=label_text, bg=row_bg, fg=theme.TEXT_PRI,
                           font=("Segoe UI", 11), anchor="w", padx=10, pady=6, width=40)
            lbl.pack(fill="x")
            for w in (row, lbl):
                w.bind("<Button-1>", lambda e, code=cur.code: self._pick(code))
                w.bind("<Enter>", lambda e, idx=i: self._set_highlight(idx))

        if len(self._filtered) > self._MAX_VISIBLE_ROWS:
            more = len(self._filtered) - self._MAX_VISIBLE_ROWS
            tk.Label(inner, text=f"+{more} more — keep typing to narrow it down",
                    bg=theme.BG_CARD, fg=theme.TEXT_SEC, font=("Segoe UI", 9),
                    anchor="w", padx=10, pady=4).pack(fill="x")

    def _set_highlight(self, idx: int):
        self._highlight_idx = idx
        self._render_popup()

    def _close_popup(self):
        if self._popup is not None:
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None


# ── Section Header ─────────────────────────────────────────────────────────────

class SectionHeader(ctk.CTkFrame):
    def __init__(self, parent, title: str, subtitle: str = "",
                 btn_text: Optional[str] = None, btn_cmd: Optional[Callable] = None,
                 extra_buttons: Optional[List[Tuple[str, Callable]]] = None, **kw):
        """`extra_buttons`: optional list of (text, command) pairs rendered as
        secondary (outlined) buttons to the left of the primary btn_text
        button — for a section that has more than one header-level action
        (e.g. "New Transaction" + "Import Payslip")."""
        super().__init__(parent, fg_color="transparent", **kw)
        self.grid_columnconfigure(0, weight=1)

        left = ctk.CTkFrame(self, fg_color="transparent")
        left.grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(left, text=title,
                     font=("Segoe UI", 22, "bold"), text_color=theme.TEXT_PRI).pack(anchor="w")
        if subtitle:
            ctk.CTkLabel(left, text=subtitle,
                         font=("Segoe UI", 12), text_color=theme.TEXT_SEC).pack(anchor="w")

        right = ctk.CTkFrame(self, fg_color="transparent")
        right.grid(row=0, column=1, sticky="e")

        for txt, cmd in (extra_buttons or []):
            ctk.CTkButton(right, text=txt, command=cmd,
                          fg_color="transparent", border_color=theme.BORDER, border_width=1,
                          text_color=theme.TEXT_PRI, hover_color=theme.BG_HOVER,
                          font=("Segoe UI", 13), height=34, corner_radius=8,
                          ).pack(side="left", padx=(0, 8))

        if btn_text and btn_cmd:
            ctk.CTkButton(right, text=btn_text, command=btn_cmd,
                          fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
                          text_color="#fff", font=("Segoe UI", 13),
                          height=34, corner_radius=8,
                          ).pack(side="left")


# ── Stat Card ─────────────────────────────────────────────────────────────────

class StatCard(ctk.CTkFrame):
    """
    A clickable summary card. Pass `on_click` to navigate somewhere when
    the card (or any part of it) is clicked.
    """
    def __init__(self, parent, label: str, value: str, sub: str = "",
                 accent: Optional[str] = None, icon: str = "",
                 on_click: Optional[Callable] = None, **kw):
        accent = accent or theme.ACCENT
        super().__init__(parent, fg_color=theme.BG_CARD, corner_radius=12,
                         border_width=1, border_color=theme.BORDER, **kw)
        self.configure(cursor="hand2" if on_click else "arrow")
        pad = dict(padx=16, pady=12)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(**pad, fill="x")
        if icon:
            ctk.CTkLabel(top, text=icon, font=("Segoe UI", 20),
                         text_color=accent).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(top, text=label.upper(),
                     font=("Segoe UI", 10, "bold"), text_color=theme.TEXT_SEC).pack(side="left")

        ctk.CTkLabel(self, text=value,
                     font=("Segoe UI", 24, "bold"), text_color=accent,
                     anchor="w").pack(padx=16, pady=(0, 4), anchor="w")
        if sub:
            ctk.CTkLabel(self, text=sub,
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC,
                         anchor="w").pack(padx=16, pady=(0, 12), anchor="w")

        if on_click:
            self._bind_click(self, on_click)

    def _bind_click(self, widget, cmd):
        widget.bind("<Button-1>", lambda e: cmd())
        for child in widget.winfo_children():
            self._bind_click(child, cmd)


# ── Data Table ────────────────────────────────────────────────────────────────

class DataTable(ctk.CTkScrollableFrame):
    """Lightweight scrollable table, optionally with inline row editing."""

    HEADER_H   = 36
    ROW_H      = 38

    def __init__(self, parent, columns: List[dict], **kw):
        """
        columns: [{"key": str, "label": str, "width": int, "anchor": str}]
        """
        super().__init__(parent, fg_color=theme.BG_CARD, corner_radius=10, **kw)
        self.columns  = columns
        self._rows    = []
        self._row_widgets = []
        self._on_select = None
        self._editable_cols = {}
        self._on_row_save = None
        self._editing_index = None

        self._build_header()

    def _build_header(self):
        hdr = ctk.CTkFrame(self, fg_color=theme.BG_HOVER, corner_radius=0, height=self.HEADER_H)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        for col in self.columns:
            ctk.CTkLabel(
                hdr, text=col.get("label", ""),
                font=("Segoe UI", 11, "bold"), text_color=theme.TEXT_SEC,
                width=col.get("width", 120), anchor=col.get("anchor", "w")
            ).pack(side="left", padx=8)
        if self.columns:
            ctk.CTkLabel(hdr, text="", font=("Segoe UI", 11, "bold"),
                         text_color=theme.TEXT_SEC, width=70).pack(side="left", padx=8)

    def set_rows(self, rows: List[dict], on_select: Optional[Callable] = None,
                 editable_cols: Optional[List[dict]] = None,
                 on_row_save: Optional[Callable] = None):
        """
        rows: list of dicts keyed by column 'key'. For editable columns, also
        provide '_raw_<key>' with the unformatted value to seed the editor.

        editable_cols: [{"key": str, "editor": "entry"|"combo"|"date",
                         "options": [...] (for combo)}]
        on_row_save(row, new_values_dict) -> called when the user clicks ✓.
        Should persist changes and may raise to show an error (the row stays
        in edit mode); on success the caller is expected to refresh the table
        (which exits edit mode for all rows).
        """
        self._rows = rows
        self._on_select = on_select
        self._editable_cols = {c["key"]: c for c in (editable_cols or [])}
        self._on_row_save = on_row_save
        self._editing_index = None
        self._redraw()

    def _redraw(self):
        for w in self._row_widgets:
            w.destroy()
        self._row_widgets.clear()
        for i, row in enumerate(self._rows):
            self._render_row(i, row)

    def _row_bg(self, i):
        return theme.BG_CARD if i % 2 == 0 else theme.ROW_ALT

    def _render_row(self, i, row):
        bg = self._row_bg(i)
        rf = ctk.CTkFrame(self, fg_color=bg, corner_radius=0, height=self.ROW_H)
        rf.pack(fill="x")
        rf.pack_propagate(False)
        cell_widgets = {}
        for col in self.columns:
            val = str(row.get(col["key"], ""))
            color = row.get(f"_color_{col['key']}", theme.TEXT_PRI)
            lbl = ctk.CTkLabel(
                rf, text=val,
                font=("Segoe UI", 12), text_color=color,
                width=col.get("width", 120), anchor=col.get("anchor", "w")
            )
            lbl.pack(side="left", padx=8)
            cell_widgets[col["key"]] = lbl

        def _click(event, r=row, f=rf):
            if self._on_select:
                self._on_select(r)
            for w in self._row_widgets:
                w.configure(fg_color=self._row_bg(self._row_widgets.index(w)))
            f.configure(fg_color=theme.BG_SELECTED)
        rf.bind("<Button-1>", _click)
        for child in rf.winfo_children():
            child.bind("<Button-1>", _click)

        if self._editable_cols and self._on_row_save:
            edit_btn = ctk.CTkButton(rf, text="✎ Edit", width=66, height=26,
                                     fg_color="transparent", border_width=1,
                                     border_color=theme.BORDER, text_color=theme.ACCENT,
                                     font=("Segoe UI", 11),
                                     command=lambda idx=i, r=row, f=rf, cw=cell_widgets:
                                         self._enter_edit_mode(idx, r, f, cw))
            edit_btn.pack(side="right", padx=8)

        self._row_widgets.append(rf)

    def _enter_edit_mode(self, i, row, rf, cell_widgets):
        if self._editing_index is not None:
            return  # only one row editable at a time
        self._editing_index = i
        for w in rf.winfo_children():
            w.destroy()

        editors = {}
        for col in self.columns:
            key = col["key"]
            spec = self._editable_cols.get(key)
            width = col.get("width", 120)
            if not spec:
                val = str(row.get(key, ""))
                color = row.get(f"_color_{key}", theme.TEXT_PRI)
                ctk.CTkLabel(rf, text=val, font=("Segoe UI", 12), text_color=color,
                             width=width, anchor=col.get("anchor", "w")).pack(side="left", padx=8)
                continue
            raw_val = row.get(f"_raw_{key}", row.get(key, ""))
            if spec.get("editor") == "combo":
                w = make_combo(rf, spec.get("options", []), width=width)
                w.set(str(raw_val))
            else:
                w = make_entry(rf, width=width)
                w.insert(0, str(raw_val))
            w.pack(side="left", padx=4)
            editors[key] = w

        def do_save():
            new_values = {key: w.get() for key, w in editors.items()}
            try:
                self._on_row_save(row, new_values)
            except Exception as e:
                from tkinter import messagebox
                messagebox.showerror("Error", str(e))
                return
            # On success the panel typically reloads the table — or, in some
            # panels, rebuilds the whole panel (destroying this table). Guard
            # against acting on a now-destroyed widget.
            if not self.winfo_exists():
                return
            self._editing_index = None
            self._redraw()

        def do_cancel():
            self._editing_index = None
            self._redraw()

        ctk.CTkButton(rf, text="✓", width=30, height=26, fg_color=theme.GREEN,
                      text_color="#fff", font=("Segoe UI", 12), command=do_save).pack(side="right", padx=2)
        ctk.CTkButton(rf, text="✕", width=30, height=26, fg_color=theme.RED,
                      text_color="#fff", font=("Segoe UI", 12), command=do_cancel).pack(side="right", padx=2)


# ── Loading Overlay ─────────────────────────────────────────────────────────

class LoadingOverlay(ctk.CTkFrame):
    """
    A brief animated "futuristic" loading indicator — a rotating dual-arc
    ring with a pulsing core, scanning baseline, and animated status text —
    shown while a panel is being (re)built.
    """

    def __init__(self, parent, label: str = "Loading"):
        super().__init__(parent, fg_color=theme.BG_DARK, corner_radius=0)
        self._running = True
        self._angle = 0
        self._pulse = 0
        self._dots = 0

        center = ctk.CTkFrame(self, fg_color="transparent")
        center.place(relx=0.5, rely=0.5, anchor="center")

        self._size = 96
        self.canvas = tk.Canvas(center, width=self._size, height=self._size,
                                bg=theme.BG_DARK, highlightthickness=0)
        self.canvas.pack()

        self._label_text = label.upper()
        self.label = ctk.CTkLabel(center, text=self._label_text,
                                  font=("Consolas", 13, "bold"), text_color=theme.ACCENT)
        self.label.pack(pady=(14, 0))

        self.scan = tk.Canvas(center, width=180, height=4, bg=theme.BG_DARK, highlightthickness=0)
        self.scan.pack(pady=(8, 0))

        self._draw_spinner()
        self._draw_scan()
        self._tick()

    def _draw_spinner(self):
        s = self._size
        cx = cy = s / 2
        r_outer = s / 2 - 4
        self.canvas.delete("all")
        # Faint static ring
        self.canvas.create_oval(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer,
                                outline=theme.BORDER, width=2)
        # Two rotating arcs, offset, in accent colors
        self.canvas.create_arc(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer,
                               start=self._angle, extent=110,
                               style="arc", outline=theme.ACCENT, width=4)
        self.canvas.create_arc(cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer,
                               start=self._angle + 180, extent=50,
                               style="arc", outline=theme.ACCENT2, width=4)
        # Pulsing core
        pulse_r = 5 + 3 * abs(((self._pulse % 20) - 10) / 10)
        self.canvas.create_oval(cx - pulse_r, cy - pulse_r, cx + pulse_r, cy + pulse_r,
                                fill=theme.ACCENT, outline="")

    def _draw_scan(self):
        w, h = 180, 4
        self.scan.delete("all")
        self.scan.create_rectangle(0, 0, w, h, fill=theme.BORDER, outline="")
        pos = (self._pulse * 6) % (w + 40) - 20
        self.scan.create_rectangle(max(0, pos), 0, min(w, pos + 40), h,
                                   fill=theme.ACCENT, outline="")

    def _tick(self):
        if not self._running:
            return
        self._angle = (self._angle + 9) % 360
        self._pulse += 1
        self._draw_spinner()
        self._draw_scan()
        if self._pulse % 4 == 0:
            self._dots = (self._dots + 1) % 4
            self.label.configure(text=f"{self._label_text}{'.' * self._dots}{' ' * (3 - self._dots)}")
        self.after(30, self._tick)

    def stop(self):
        self._running = False


# ── Attachment Section ──────────────────────────────────────────────────────

DEFAULT_ATTACH_FILETYPES = [
    ("All files", "*.*"),
    ("Documents & images", "*.pdf *.png *.jpg *.jpeg *.gif *.webp *.doc *.docx *.xls *.xlsx *.csv *.txt"),
]


class AttachmentSection(ctk.CTkFrame):
    """
    A "📎 Attachments" block for create/edit modals: lets the user attach any
    number of files of any type, and remove any of them, before saving.

    - If `entity` is given (an object with `.id` and `.attachments`), files
      are attached/removed immediately against that entity.
    - If `entity` is None (creating something new that doesn't have an id
      yet), files are *staged* in `self.staged` (a list of
      {"path", "filename"} dicts) and shown with "(will attach on save)".
      After the new entity is created and committed, call
      `section.commit(new_entity.id)` to upload the staged files.
    """

    def __init__(self, parent, ctx, owner_type: str, entity=None,
                title: str = "📎 Attachments", filetypes=None, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.ctx = ctx
        self.owner_type = owner_type
        self.entity = entity
        self.staged: List[dict] = []
        self.filetypes = filetypes or DEFAULT_ATTACH_FILETYPES

        ctk.CTkLabel(self, text=title, font=("Segoe UI", 12, "bold"),
                     text_color=theme.ACCENT).pack(anchor="w", pady=(8, 4))
        self.list_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.list_frame.pack(fill="x", pady=(0, 4))
        ctk.CTkButton(self, text="＋ Attach File", height=30, font=("Segoe UI", 11),
                      fg_color="transparent", border_color=theme.BORDER, border_width=1,
                      text_color=theme.ACCENT, command=self._attach).pack(anchor="w", pady=(2, 8))
        self.refresh()

    def _attach(self):
        from tkinter import filedialog, messagebox
        path = filedialog.askopenfilename(
            title="Attach file (any type — statements, photos, contracts, scans…)",
            filetypes=self.filetypes)
        if not path:
            return
        if self.entity is not None:
            try:
                self.ctx.attachment.save_file(path, self.ctx.session, self.owner_type, self.entity.id)
                self.ctx.session.refresh(self.entity)
            except Exception as e:
                messagebox.showerror("Error", str(e))
                return
        else:
            import os
            self.staged.append({"path": path, "filename": os.path.basename(path)})
        self.refresh()

    def refresh(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        items = []
        if self.entity is not None:
            items += [("existing", a) for a in self.entity.attachments]
        items += [("staged", s) for s in self.staged]

        if not items:
            ctk.CTkLabel(self.list_frame, text="No files attached yet.",
                         font=("Segoe UI", 11), text_color=theme.TEXT_SEC).pack(anchor="w", pady=2)
            return

        for kind, item in items:
            row = ctk.CTkFrame(self.list_frame, fg_color=theme.ROW_ALT, corner_radius=6)
            row.pack(fill="x", pady=2)
            if kind == "existing":
                fname = item.original_filename
            else:
                fname = f"{item['filename']}  (will attach on save)"
            ctk.CTkLabel(row, text=f"📎 {fname}", font=("Segoe UI", 11),
                         text_color=theme.ACCENT).pack(side="left", padx=8, pady=4)
            if kind == "existing":
                ctk.CTkButton(row, text="Open", width=60, height=24,
                              fg_color="transparent", text_color=theme.ACCENT, font=("Segoe UI", 11),
                              command=lambda a=item: self.ctx.attachment.open_file(a)
                              ).pack(side="right", padx=4, pady=2)
            ctk.CTkButton(row, text="✕", width=28, height=24,
                          fg_color="transparent", text_color=theme.RED, font=("Segoe UI", 11),
                          command=lambda k=kind, it=item: self._remove(k, it)
                          ).pack(side="right", pady=2)

    def _remove(self, kind, item):
        from tkinter import messagebox
        if kind == "existing":
            if messagebox.askyesno("Delete Attachment", f"Remove '{item.original_filename}'?"):
                self.ctx.attachment.delete_file(item, self.ctx.session)
                self.ctx.session.refresh(self.entity)
                self.refresh()
        else:
            self.staged.remove(item)
            self.refresh()

    def commit(self, entity_id: int):
        """Upload any staged files now that the new entity has an id."""
        for s in self.staged:
            try:
                self.ctx.attachment.save_file(s["path"], self.ctx.session, self.owner_type, entity_id)
            except Exception:
                pass
        self.staged.clear()


# ── Modal Base ────────────────────────────────────────────────────────────────

class Modal(ctk.CTkToplevel):
    def __init__(self, parent, title: str, width: int = 520, height: int = 600):
        super().__init__(parent)
        self.title(title)
        self.geometry(f"{width}x{height}")
        self.configure(fg_color=theme.BG_DARK)
        self.resizable(True, True)
        self.minsize(380, 320)
        self.grab_set()
        self.lift()

        # Header
        hdr = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=0, height=52)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text=title,
                     font=("Segoe UI", 15, "bold"), text_color=theme.TEXT_PRI).pack(
            side="left", padx=20, pady=14)
        ctk.CTkButton(hdr, text="✕", width=30, height=30,
                      fg_color="transparent", hover_color=theme.RED,
                      text_color=theme.TEXT_SEC, command=self.destroy).pack(
            side="right", padx=10, pady=10)

        self.body = ctk.CTkScrollableFrame(self, fg_color=theme.BG_DARK, corner_radius=0)
        self.body.pack(fill="both", expand=True, padx=20, pady=16)

        self.footer = ctk.CTkFrame(self, fg_color=theme.BG_CARD, corner_radius=0, height=60)
        self.footer.pack(fill="x", side="bottom")
        self.footer.pack_propagate(False)

    def add_field(self, label: str, widget_factory: Callable, pady=8) -> ctk.CTkBaseClass:
        row = ctk.CTkFrame(self.body, fg_color="transparent")
        row.pack(fill="x", pady=(0, pady))
        ctk.CTkLabel(row, text=label, font=("Segoe UI", 12),
                     text_color=theme.TEXT_SEC, anchor="w").pack(fill="x")
        w = widget_factory(row)
        w.pack(fill="x", pady=(2, 0))
        return w

    def add_buttons(self, confirm_text: str, confirm_cmd: Callable,
                    cancel_text: str = "Cancel", extra: Optional[List[tuple]] = None):
        """extra: list of (label, command, color) tuples for additional buttons (e.g. Delete)."""
        ctk.CTkButton(
            self.footer, text=cancel_text, command=self.destroy,
            fg_color="transparent", border_color=theme.BORDER, border_width=1,
            text_color=theme.TEXT_SEC, font=("Segoe UI", 13), height=36, width=120
        ).pack(side="left", padx=16, pady=12)

        if extra:
            for lbl, cmd, color in extra:
                ctk.CTkButton(
                    self.footer, text=lbl, command=cmd,
                    fg_color="transparent", border_color=color, border_width=1,
                    text_color=color, font=("Segoe UI", 13), height=36, width=120
                ).pack(side="left", padx=(0, 8), pady=12)

        ctk.CTkButton(
            self.footer, text=confirm_text, command=confirm_cmd,
            fg_color=theme.ACCENT, hover_color=theme.BG_SELECTED,
            text_color="#fff", font=("Segoe UI", 13, "bold"),
            height=36, width=140
        ).pack(side="right", padx=16, pady=12)


# ── Form helpers ──────────────────────────────────────────────────────────────

def make_entry(parent, placeholder="", **kw) -> ctk.CTkEntry:
    return ctk.CTkEntry(
        parent, placeholder_text=placeholder,
        fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        text_color=theme.TEXT_PRI, placeholder_text_color=theme.TEXT_SEC,
        font=("Segoe UI", 12), height=36, **kw
    )


def make_combo(parent, values: List[str], **kw) -> ctk.CTkComboBox:
    return ctk.CTkComboBox(
        parent, values=values,
        fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        button_color=theme.BG_INPUT, dropdown_fg_color=theme.BG_CARD,
        text_color=theme.TEXT_PRI, dropdown_text_color=theme.TEXT_PRI,
        font=("Segoe UI", 12), height=36, **kw
    )


def make_textbox(parent, height=80, **kw) -> ctk.CTkTextbox:
    return ctk.CTkTextbox(
        parent, height=height,
        fg_color=theme.BG_INPUT, border_color=theme.BORDER,
        text_color=theme.TEXT_PRI, font=("Segoe UI", 12), **kw
    )


# ── Responsive helpers ─────────────────────────────────────────────────────────

def responsive_columns(width_px: int, min_col_width: int = 320, max_cols: int = 4) -> int:
    """Given an available width, return how many columns a card grid should use."""
    if width_px <= 0:
        return 1
    cols = max(1, width_px // min_col_width)
    return min(cols, max_cols)


def safe_rebuild(widget, build_fn):
    """
    Destroy all *non-Toplevel* children of `widget` and call `build_fn()`
    again. Open Modal dialogs (CTkToplevel/Toplevel) are left alone — this
    prevents a resize-triggered (or otherwise spurious) rebuild from
    silently destroying a dialog the user just opened.
    """
    for w in widget.winfo_children():
        if isinstance(w, tk.Toplevel):
            continue
        w.destroy()
    build_fn()
