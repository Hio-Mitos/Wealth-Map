"""
WealthMap – Theme Manager
Provides a single source of truth for colours across the whole app.
Panels read colours via `theme.XXX` (attribute access) at *build* time, so
switching modes + rebuilding the UI re-applies the new palette everywhere.
"""

from typing import Callable, List

DARK = {
    "BG_DARK":    "#0D1117",
    "BG_CARD":    "#161B22",
    "BG_SIDEBAR": "#0D1117",
    "BG_HOVER":   "#1C2128",
    "BG_INPUT":   "#161B22",
    "BG_SELECTED":"#1C3A5C",
    "ACCENT":     "#58A6FF",
    "ACCENT2":    "#3FB950",
    "ACCENT3":    "#F78166",
    "TEXT_PRI":   "#E6EDF3",
    "TEXT_SEC":   "#8B949E",
    "BORDER":     "#30363D",
    "GOLD":       "#E3B341",
    "RED":        "#F85149",
    "GREEN":      "#3FB950",
    "ROW_ALT":    "#1A2130",
}

LIGHT = {
    "BG_DARK":    "#F6F8FA",
    "BG_CARD":    "#FFFFFF",
    "BG_SIDEBAR": "#FFFFFF",
    "BG_HOVER":   "#EAEEF2",
    "BG_INPUT":   "#FFFFFF",
    "BG_SELECTED":"#DBEAFE",
    "ACCENT":     "#1F6FEB",
    "ACCENT2":    "#1A7F37",
    "ACCENT3":    "#D1453B",
    "TEXT_PRI":   "#1F2328",
    "TEXT_SEC":   "#57606A",
    "BORDER":     "#D0D7DE",
    "GOLD":       "#9A6700",
    "RED":        "#CF222E",
    "GREEN":      "#1A7F37",
    "ROW_ALT":    "#F6F8FA",
}


class ThemeManager:
    def __init__(self):
        self.mode = "dark"
        self._listeners: List[Callable[[], None]] = []

    @property
    def palette(self):
        return DARK if self.mode == "dark" else LIGHT

    def __getattr__(self, name):
        pal = DARK if self.mode == "dark" else LIGHT
        if name in pal:
            return pal[name]
        raise AttributeError(f"No theme colour '{name}'")

    def set_mode(self, mode: str):
        mode = "light" if mode.lower().startswith("l") else "dark"
        if mode != self.mode:
            self.mode = mode
            for cb in self._listeners:
                try:
                    cb()
                except Exception:
                    pass

    def toggle(self):
        self.set_mode("light" if self.mode == "dark" else "dark")

    def on_change(self, callback: Callable[[], None]):
        self._listeners.append(callback)

    # CustomTkinter appearance mode mapping
    @property
    def ctk_mode(self):
        return "Dark" if self.mode == "dark" else "Light"


# Singleton — import this everywhere
theme = ThemeManager()
