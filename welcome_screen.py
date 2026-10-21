"""Welcome screen: offers JSON selection and file parsing."""
import os
import tkinter as tk
from tkinter import ttk

from helpers import load_recent_paths
from platform_utils import make_font


class WelcomeScreen(ttk.Frame):
    """Full-window welcome card with two buttons and their descriptions."""

    def __init__(self, master, on_select_json, on_select_recent,
                 on_parse_logs):
        super().__init__(master)
        self.on_select_json = on_select_json
        self.on_select_recent = on_select_recent
        self.on_parse_logs = on_parse_logs

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        card_bg = "#f7f9fc"
        card = tk.Frame(self, bd=2, relief="groove",
                        bg=card_bg, padx=40, pady=30)
        card.grid(row=0, column=0)

        tk.Label(card, text="The ORCA Data Processor",
                 font=make_font(18, weight="bold"),
                 bg=card_bg, fg="#1a2230").grid(
            row=0, column=0, columnspan=2, pady=(0, 26))

        # ---- Row 1: Select JSON / Recent ----
        btn_frame = ttk.Frame(card)
        btn_frame.grid(row=1, column=0, padx=(0, 26), pady=10, sticky="ew")

        ttk.Button(btn_frame, text="Select JSON", width=22,
                   command=self.on_select_json).pack(fill=tk.X)

        self._recent_btn = ttk.Menubutton(btn_frame,
                                           text="Recent JSON…",
                                           width=22)
        self._rebuild_recent_menu()
        self._recent_btn.pack(fill=tk.X, pady=(4, 0))

        tk.Label(
            card,
            text=("Load a JSON file that was already parsed by this "
                  "program, and browse the data stored inside."),
            bg=card_bg, fg="#444", font=make_font(10),
            wraplength=380, justify=tk.LEFT
        ).grid(row=1, column=1, pady=10, sticky="w")

        # ---- Row 2: Parse files ----
        ttk.Button(card, text="Parse files", width=22,
                   command=self.on_parse_logs).grid(
            row=2, column=0, padx=(0, 26), pady=10, sticky="ew")

        tk.Label(
            card,
            text=("Scan a folder for files with a chosen extension "
                  "(.log, .out or any other text extension), extract "
                  "the selected data using the available parser "
                  "methods, and save the result as a JSON file in the "
                  "'data' folder next to these scripts."),
            bg=card_bg, fg="#444", font=make_font(10),
            wraplength=380, justify=tk.LEFT
        ).grid(row=2, column=1, pady=10, sticky="w")

        card.columnconfigure(0, weight=0)
        card.columnconfigure(1, weight=1)

    def _rebuild_recent_menu(self):
        menu = tk.Menu(self._recent_btn, tearoff=0)
        paths = load_recent_paths()
        if not paths:
            menu.add_command(label="(no recent files)", state="disabled")
        else:
            for p in paths:
                label = os.path.basename(p) + "  —  " + os.path.dirname(p)
                menu.add_command(
                    label=label,
                    command=lambda pp=p: self.on_select_recent(pp))
        self._recent_btn["menu"] = menu