"""Log tab — buffered text output for download logs."""

import tkinter as tk
from tkinter import ttk


class LogTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=0)
        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)

        self.text = tk.Text(self, wrap="word", state="disabled", font=("Consolas", 9))
        self.text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self, orient="vertical", command=self.text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=scroll.set)

        # ── buffering ────────────────────────────────────────────
        self._buffer: list[str] = []
        self._flush_pending = False

    def append(self, text: str):
        """Append text with batch flushing for performance."""
        self._buffer.append(text)
        if not self._flush_pending:
            self._flush_pending = True
            self.after(150, self._flush)

    def _flush(self):
        if not self._buffer:
            self._flush_pending = False
            return
        combined = "".join(self._buffer)
        self._buffer.clear()
        self._flush_pending = False
        self.text.configure(state="normal")
        self.text.insert("end", combined)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self._buffer.clear()
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")
