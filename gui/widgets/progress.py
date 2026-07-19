"""Dual progress bars + status labels."""

import tkinter as tk
from tkinter import ttk


class ProgressPanel(ttk.Frame):
    def __init__(self, parent, total_progress_var, file_progress_var,
                 status_var, file_status_var):
        super().__init__(parent, padding=(12, 0, 12, 8))
        self.columnconfigure(1, weight=1)
        self.columnconfigure(3, weight=1)

        ttk.Label(self, textvariable=status_var, width=28).grid(row=0, column=0, sticky="w")
        ttk.Progressbar(self, variable=total_progress_var, maximum=100).grid(
            row=0, column=1, sticky="ew", padx=(8, 16))
        ttk.Label(self, textvariable=file_status_var, width=34).grid(row=0, column=2, sticky="w")
        ttk.Progressbar(self, variable=file_progress_var, maximum=100).grid(
            row=0, column=3, sticky="ew", padx=(8, 0))
