"""JCM Pitwall - Fahrer-Fenster.

Ein Fenster, ein Knopf. Kein Terminal, keine Konfigurationsdatei, keine
Kommandozeilenschalter.

Start:  Doppelklick auf START_HIER.bat  (oder JCM-Pitwall.exe)

Technisch: tkinter, weil das bei jeder Python-Installation dabei ist und
nichts nachinstalliert werden muss. Der eigentliche Client laeuft in einem
eigenen Prozess - stuerzt er ab, faengt das Fenster das ab und startet neu,
statt dass mitten im Rennen alles steht.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox

HERE = Path(__file__).resolve().parent
IS_FROZEN = getattr(sys, "frozen", False)
BASE = Path(sys.executable).parent if IS_FROZEN else HERE


def _config_path() -> Path:
    """Wo die Konfiguration liegt.

    Installiert liegt das Programm unter "Programme" und darf dort nicht
    schreiben - die Konfiguration gehoert deshalb ins Benutzerprofil.
    Liegt eine Datei direkt neben dem Programm, gewinnt die (fuer den
    portablen Betrieb vom USB-Stick).
    """
    daneben = BASE / "pitwall_config.json"
    if daneben.exists():
        return daneben
    lokal = HERE / "pitwall_config.json"
    if lokal.exists() and not IS_FROZEN:
        return lokal
    appdata = os.environ.get("APPDATA") or os.environ.get("XDG_CONFIG_HOME") or str(Path.home())
    ordner = Path(appdata) / "JCM Pitwall"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner / "pitwall_config.json"


CONFIG_PATH = _config_path()

BG = "#0a0b0d"; PANEL = "#14161a"; LINE = "#262a31"
INK = "#e9ecf1"; MUTED = "#79818d"
ORANGE = "#ff6a13"; TURQ = "#1fd4c3"; GREEN = "#35d07f"; RED = "#ff4d4d"; AMBER = "#ffb020"


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict):
    try:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        pass


def fetch_drivers(cfg: dict) -> list[str]:
    """Fahrernamen aus der Datenbank holen, damit die Liste immer stimmt."""
    url, key = cfg.get("supabase_url", ""), cfg.get("supabase_key", "")
    if not url or not key:
        return []
    try:
        req = urllib.request.Request(
            url.rstrip("/") + "/rest/v1/drivers?select=driver_name&order=driver_name")
        req.add_header("apikey", key)
        req.add_header("Authorization", f"Bearer {key}")
        with urllib.request.urlopen(req, timeout=8) as resp:
            return [r["driver_name"] for r in json.loads(resp.read().decode())]
    except Exception:
        return []


class TeamCodeDialog(tk.Toplevel):
    """Erster Start: Team-Code einfuegen. Danach nie wieder."""

    def __init__(self, parent, vorhandener: str = ""):
        super().__init__(parent)
        self.result: dict | None = None
        self.title("Team-Code einfügen")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        tk.Label(self, text="TEAM-CODE", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=24, pady=(22, 8))
        tk.Label(self, bg=BG, fg=INK, justify="left", wraplength=440,
                 font=("Segoe UI", 10),
                 text="Marcel hat dir einen langen Code geschickt, der mit JCM1- "
                      "anfängt. Kopier ihn komplett und füg ihn hier ein.").pack(
            anchor="w", padx=24)

        self.text = tk.Text(self, height=5, width=54, bg=PANEL, fg=INK,
                            insertbackground=INK, relief="flat", wrap="char",
                            font=("Consolas", 9), padx=10, pady=8)
        self.text.pack(padx=24, pady=14)
        if vorhandener:
            self.text.insert("1.0", vorhandener)

        self.fehler = tk.Label(self, text="", bg=BG, fg=RED, wraplength=440,
                               justify="left", font=("Segoe UI", 9))
        self.fehler.pack(anchor="w", padx=24)

        leiste = tk.Frame(self, bg=BG); leiste.pack(fill="x", padx=24, pady=(14, 22))
        tk.Button(leiste, text="Einfügen aus Zwischenablage", command=self._paste,
                  bg=PANEL, fg=INK, relief="flat", font=("Segoe UI", 9),
                  cursor="hand2").pack(side="left", ipadx=8, ipady=5)
        tk.Button(leiste, text="ÜBERNEHMEN", command=self._ok, bg=ORANGE, fg="#12100e",
                  relief="flat", font=("Bahnschrift Condensed", 15, "bold"),
                  cursor="hand2").pack(side="right", ipadx=18, ipady=6)

        self.text.focus_set()
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.update_idletasks()
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - self.winfo_width()) // 2)
        y = parent.winfo_rooty() + 70
        self.geometry(f"+{x}+{y}")

    def _paste(self):
        try:
            self.text.delete("1.0", "end")
            self.text.insert("1.0", self.clipboard_get())
        except Exception:
            self.fehler.configure(text="In der Zwischenablage ist kein Text.")

    def _ok(self):
        import teamcode
        try:
            self.result = teamcode.decode(self.text.get("1.0", "end"))
        except ValueError as exc:
            self.fehler.configure(text=str(exc))
            return
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = load_config()
        self.proc: subprocess.Popen | None = None
        self.queue: queue.Queue[str] = queue.Queue()
        self.running = False
        self.laps_sent = 0
        self.want_restart = True

        root.title("JCM Pitwall - Fahrer")
        root.configure(bg=BG)
        root.geometry("620x680")
        root.minsize(540, 560)

        self._build()
        self._load_drivers()
        self._check_ready()
        root.after(120, self._pump)
        root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ----------------------------------------------------------------
    def _build(self):
        head = tk.Frame(self.root, bg=BG); head.pack(fill="x", padx=22, pady=(20, 6))
        tk.Frame(head, bg=ORANGE, width=5, height=42).pack(side="left", padx=(0, 12))
        box = tk.Frame(head, bg=BG); box.pack(side="left", anchor="w")
        tk.Label(box, text="JCM PITWALL", bg=BG, fg=INK,
                 font=("Bahnschrift Condensed", 26, "bold")).pack(anchor="w")
        tk.Label(box, text="FAHRER-CLIENT", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")
        tk.Button(head, text="Team-Code", command=lambda: self.ask_team_code(False),
                  bg=PANEL, fg=MUTED, relief="flat", font=("Segoe UI", 9),
                  cursor="hand2").pack(side="right", ipadx=10, ipady=4)

        # Fahrerauswahl
        card = tk.Frame(self.root, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        card.pack(fill="x", padx=22, pady=(18, 0))
        tk.Label(card, text="WER FÄHRT?", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=16, pady=(14, 6))
        self.driver = tk.StringVar(value=self.cfg.get("driver_name", ""))
        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("P.TCombobox", fieldbackground=BG, background=BG,
                        foreground=INK, arrowcolor=INK, bordercolor=LINE, lightcolor=LINE,
                        darkcolor=LINE, selectbackground=BG, selectforeground=INK)
        self.combo = ttk.Combobox(card, textvariable=self.driver, state="readonly",
                                  style="P.TCombobox", font=("Segoe UI", 13))
        self.combo.pack(fill="x", padx=16, pady=(0, 16), ipady=6)

        # Startknopf
        self.btn = tk.Button(self.root, text="START", command=self.toggle,
                             bg=ORANGE, fg="#12100e", activebackground=ORANGE,
                             font=("Bahnschrift Condensed", 26, "bold"),
                             relief="flat", cursor="hand2", height=1)
        self.btn.pack(fill="x", padx=22, pady=18, ipady=16)

        # Status
        st = tk.Frame(self.root, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        st.pack(fill="x", padx=22)
        inner = tk.Frame(st, bg=PANEL); inner.pack(fill="x", padx=16, pady=14)
        self.dot = tk.Canvas(inner, width=14, height=14, bg=PANEL, highlightthickness=0)
        self.dot.pack(side="left", padx=(0, 10))
        self.dot_id = self.dot.create_oval(2, 2, 12, 12, fill=MUTED, outline="")
        self.status = tk.Label(inner, text="Bereit", bg=PANEL, fg=INK,
                               font=("Segoe UI", 11), anchor="w", justify="left")
        self.status.pack(side="left", fill="x", expand=True)

        # Protokoll
        tk.Label(self.root, text="WAS GERADE PASSIERT", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=22, pady=(18, 6))
        lf = tk.Frame(self.root, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        lf.pack(fill="both", expand=True, padx=22, pady=(0, 10))
        self.log = tk.Text(lf, bg=PANEL, fg=MUTED, insertbackground=INK, relief="flat",
                           font=("Consolas", 9), wrap="none", state="disabled",
                           padx=12, pady=10)
        sb = tk.Scrollbar(lf, command=self.log.yview, bg=PANEL, troughcolor=PANEL,
                          relief="flat", bd=0)
        self.log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); self.log.pack(fill="both", expand=True)

        foot = tk.Frame(self.root, bg=BG); foot.pack(fill="x", padx=22, pady=(0, 14))
        self.hint = tk.Label(foot, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8),
                             anchor="w", justify="left", wraplength=560)
        self.hint.pack(fill="x")

    # ----------------------------------------------------------------
    def _load_drivers(self):
        names = fetch_drivers(self.cfg)
        if not names:
            names = self.cfg.get("driver_list") or []
        if not names:
            names = [self.cfg.get("driver_name") or "Fahrer"]
        self.combo["values"] = names
        if self.driver.get() not in names:
            self.driver.set(names[0])

    def ask_team_code(self, erstmalig: bool = True):
        dlg = TeamCodeDialog(self.root)
        self.root.wait_window(dlg)
        if dlg.result:
            alt = self.cfg.get("driver_name", "")
            self.cfg = dlg.result
            if alt and alt in (self.cfg.get("driver_list") or []):
                self.cfg["driver_name"] = alt
            save_config(self.cfg)
            self._load_drivers()
            self._check_ready()
            self._write("--- Team-Code übernommen ---")
            return True
        return False

    def _check_ready(self):
        if not self.cfg.get("supabase_url") or not self.cfg.get("supabase_key"):
            self._set_state("err", "Noch kein Team-Code eingefügt")
            self.hint.configure(
                text="Oben rechts auf „Team-Code“ klicken und den Code von Marcel einfügen.")
            self.btn.configure(state="disabled", bg=LINE, fg=MUTED)
            return False
        if not self.running:
            self.btn.configure(state="normal", bg=ORANGE, fg="#12100e", text="START")
            self._set_state("off", "Bereit - Namen wählen und START drücken")
        self.hint.configure(
            text="Das Fenster kann offen im Hintergrund bleiben - es stört das Spiel nicht. "
                 "Erst schließen, wenn du fertig gefahren bist.")
        return True

    def _set_state(self, kind: str, text: str):
        colors = {"off": MUTED, "ok": GREEN, "warn": AMBER, "err": RED, "wait": TURQ}
        self.dot.itemconfig(self.dot_id, fill=colors.get(kind, MUTED))
        self.status.configure(text=text)

    def _write(self, line: str):
        self.log.configure(state="normal")
        self.log.insert("end", line.rstrip() + "\n")
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 400:
            self.log.delete("1.0", f"{lines-400}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    # ----------------------------------------------------------------
    def toggle(self):
        if self.running:
            self.stop()
        else:
            self.start()

    def start(self):
        if not self._check_ready():
            if not self.ask_team_code():
                return
            if not self._check_ready():
                return
        name = self.driver.get().strip()
        if not name:
            messagebox.showwarning("Kein Fahrer", "Bitte oben deinen Namen auswählen.")
            return
        self.cfg["driver_name"] = name
        save_config(self.cfg)

        self.running = True
        self.want_restart = True
        self.laps_sent = 0
        self.btn.configure(text="STOPP", bg=LINE, fg=INK)
        self.combo.configure(state="disabled")
        self._set_state("wait", "Starte … warte auf Telemetrie aus dem Spiel")
        self._write(f"--- Start als {name} ---")
        threading.Thread(target=self._supervise, args=(name,), daemon=True).start()

    def stop(self):
        self.want_restart = False
        self.running = False
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.btn.configure(text="START", bg=ORANGE, fg="#12100e")
        self.combo.configure(state="readonly")
        self._set_state("off", "Gestoppt")
        self._write("--- Gestoppt ---")

    def _command(self, name: str) -> list[str]:
        if IS_FROZEN:
            return [sys.executable, "--run-client", "--driver", name]
        return [sys.executable, str(HERE / "run_client.py"), "--driver", name]

    def _supervise(self, name: str):
        """Startet den Client neu, falls er abstuerzt. 24h heisst 24h."""
        attempts = 0
        while self.want_restart:
            try:
                self.proc = subprocess.Popen(
                    self._command(name), cwd=str(HERE),
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1, encoding="utf-8", errors="replace",
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
            except Exception as exc:
                self.queue.put(f"!! Start fehlgeschlagen: {exc}")
                self.queue.put("!!STATE!!err!!Python oder Client nicht gefunden")
                return
            for line in self.proc.stdout:
                if not self.want_restart:
                    break
                self.queue.put(line)
            code = self.proc.wait()
            if not self.want_restart:
                return
            attempts += 1
            self.queue.put(f"!! Client beendet (Code {code}) - Neustart in 5 Sekunden "
                           f"(Versuch {attempts})")
            self.queue.put("!!STATE!!warn!!Verbindung unterbrochen - startet neu")
            for _ in range(50):
                if not self.want_restart:
                    return
                time.sleep(0.1)

    def _pump(self):
        try:
            while True:
                line = self.queue.get_nowait()
                if line.startswith("!!STATE!!"):
                    kind, _, text = line[len("!!STATE!!"):].partition("!!")
                    self._set_state(kind.strip(), text.strip())
                    continue
                self._write(line)
                self._interpret(line)
        except queue.Empty:
            pass
        self.root.after(150, self._pump)

    def _interpret(self, line: str):
        """Rohausgabe in eine Aussage uebersetzen, die jeder versteht."""
        if "[Runde" in line:
            self.laps_sent += 1
            self._set_state("ok", f"Läuft - {self.laps_sent} Runden übertragen")
        elif "An laufende Session angedockt" in line:
            self._set_state("ok", "Verbunden mit dem laufenden Rennen")
        elif "Neue Session angelegt" in line:
            self._set_state("ok", "Neues Rennen gestartet - du bist der Erste")
        elif "warte auf Telemetrie" in line:
            self._set_state("wait", "Warte auf das Spiel - setz dich ins Auto")
        elif "gespoolt" in line or "OFFLINE" in line:
            self._set_state("warn", "Kein Netz - Runden werden zwischengespeichert")
        elif "Keine Supabase-Zugangsdaten" in line:
            self._set_state("err", "Zugangsdaten fehlen")
        elif "Telemetrie-Baustein" in line:
            self._set_state("err", "Telemetrie-Baustein fehlt - bei Marcel melden")
            self.want_restart = False
        elif "Unerwarteter Fehler" in line:
            self._set_state("err", "Fehler - Screenshot an Marcel")

    def _on_close(self):
        if self.running:
            if not messagebox.askokcancel(
                    "Wirklich schließen?",
                    "Der Client läuft noch. Wenn du jetzt schließt, "
                    "werden keine Runden mehr übertragen."):
                return
            self.stop()
        self.root.destroy()


def main():
    root = tk.Tk()
    try:
        root.iconbitmap(default=str(HERE / "jcm.ico"))
    except Exception:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
