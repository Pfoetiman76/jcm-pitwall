"""JCM Pitwall - Einrichter.

Das Werkzeug fuer denjenigen, der das Team aufsetzt. Alles, was bisher im
Terminal lief, in einem Fenster:

  * Zugangsdaten eintragen und die komplette Kette pruefen
  * die sechs Fahrer anlegen, umbenennen, entfernen
  * den Team-Code fuer die anderen erzeugen und kopieren
  * die config.js fuer den Kommandostand schreiben

Start: Doppelklick auf EINRICHTER.bat  (oder JCM-Pitwall-Einrichter.exe)
"""

from __future__ import annotations

import json
import os
import sys
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent if (HERE.parent / "client").exists() else HERE
IS_FROZEN = getattr(sys, "frozen", False)

BG = "#0a0b0d"; PANEL = "#14161a"; PANEL2 = "#1b1e24"; LINE = "#262a31"
INK = "#e9ecf1"; MUTED = "#79818d"
ORANGE = "#ff6a13"; TURQ = "#1fd4c3"; GREEN = "#35d07f"; RED = "#ff4d4d"; AMBER = "#ffb020"

FARBEN = ["#ff6a13", "#1fd4c3", "#ffb020", "#7c8cff", "#35d07f", "#ff5d9e"]

TABELLEN = ["drivers", "sessions", "laps", "stint_telemetry", "stints",
            "events", "field_state", "opponent_laps", "weather_log"]
VIEWS = ["v_laps_full", "v_fuel_strategy", "v_driver_summary",
         "v_field_pace", "v_weather_trend"]


def config_path() -> Path:
    """Gleiche Reihenfolge wie in gui.py und config.py.

    Wichtig als EXE: frueher entschied das Vorhandensein eines Ordners
    "client" neben dem Programm. Sobald im Installationsordner so ein
    Ordner liegt, haette der Einrichter die Zugangsdaten woanders
    hingeschrieben, als das Fahrer-Fenster sie liest.
    """
    if IS_FROZEN:
        daneben = Path(sys.executable).resolve().parent / "pitwall_config.json"
        if daneben.exists():                      # portabler Betrieb
            return daneben
    else:
        kandidat = ROOT / "client" / "pitwall_config.json"
        if kandidat.parent.exists():
            return kandidat
    appdata = (os.environ.get("APPDATA")
               or os.environ.get("XDG_CONFIG_HOME")
               or str(Path.home()))
    ordner = Path(appdata) / "JCM Pitwall"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner / "pitwall_config.json"


class Rest:
    """Minimaler Supabase-Zugriff, nur Standardbibliothek."""

    def __init__(self, url: str, key: str):
        self.url = (url or "").rstrip("/")
        self.key = key or ""

    def __call__(self, pfad: str, method: str = "GET", body=None, prefer=None):
        req = urllib.request.Request(
            f"{self.url}/rest/v1/{pfad.lstrip('/')}",
            data=json.dumps(body).encode() if body is not None else None,
            method=method)
        req.add_header("apikey", self.key)
        req.add_header("Authorization", f"Bearer {self.key}")
        req.add_header("Content-Type", "application/json")
        if prefer:
            req.add_header("Prefer", prefer)
        with urllib.request.urlopen(req, timeout=15) as resp:
            roh = resp.read().decode("utf-8")
        return json.loads(roh) if roh.strip() else []


class Einrichter:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.cfg = self._load()
        root.title("JCM Pitwall - Einrichter")
        root.configure(bg=BG)
        root.geometry("880x760")
        root.minsize(760, 640)
        self._build()
        self._fahrer_laden()

    # ----------------------------------------------------------------
    def _load(self) -> dict:
        p = config_path()
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {}

    def _save(self):
        p = config_path()
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(self.cfg, indent=2, ensure_ascii=False), encoding="utf-8")
        except Exception as exc:
            messagebox.showerror("Speichern fehlgeschlagen", str(exc))

    def rest(self, anon: bool = False) -> Rest:
        return Rest(self.url.get(), self.anon.get() if anon else self.key.get())

    # ----------------------------------------------------------------
    def _build(self):
        kopf = tk.Frame(self.root, bg=BG); kopf.pack(fill="x", padx=24, pady=(20, 8))
        tk.Frame(kopf, bg=ORANGE, width=5, height=40).pack(side="left", padx=(0, 12))
        box = tk.Frame(kopf, bg=BG); box.pack(side="left")
        tk.Label(box, text="JCM PITWALL", bg=BG, fg=INK,
                 font=("Bahnschrift Condensed", 24, "bold")).pack(anchor="w")
        tk.Label(box, text="EINRICHTER", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")

        stil = ttk.Style()
        try:
            stil.theme_use("clam")
        except Exception:
            pass
        stil.configure("TNotebook", background=BG, borderwidth=0)
        stil.configure("TNotebook.Tab", background=PANEL, foreground=MUTED,
                       padding=(18, 9), borderwidth=0)
        stil.map("TNotebook.Tab", background=[("selected", PANEL2)],
                 foreground=[("selected", INK)])

        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=24, pady=(10, 0))
        self._tab_zugang()
        self._tab_fahrer()
        self._tab_verteilen()

        self.status = tk.Label(self.root, text="", bg=BG, fg=MUTED, anchor="w",
                               font=("Segoe UI", 9), wraplength=820, justify="left")
        self.status.pack(fill="x", padx=24, pady=12)

    # -- Reiter 1: Zugang --------------------------------------------
    def _tab_zugang(self):
        f = tk.Frame(self.tabs, bg=BG); self.tabs.add(f, text="1 · Zugang")
        self.url = tk.StringVar(value=self.cfg.get("supabase_url", ""))
        self.key = tk.StringVar(value=self.cfg.get("supabase_key", ""))
        self.anon = tk.StringVar(value=self.cfg.get("anon_key", ""))

        karte = tk.Frame(f, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        karte.pack(fill="x", pady=(16, 0))
        tk.Label(karte, bg=PANEL, fg=MUTED, justify="left", wraplength=760,
                 font=("Segoe UI", 9),
                 text="Alle drei Werte stehen in Supabase unter Project Settings → API. "
                      "Der service_role-Schlüssel darf alles und bleibt auf den Fahrer-PCs. "
                      "Der anon-Schlüssel darf nur lesen und geht in den Kommandostand."
                 ).pack(anchor="w", padx=18, pady=(16, 4))

        for label, var, hinweis in (
                ("Projekt-URL", self.url, "https://xxxxxxxx.supabase.co"),
                ("service_role secret", self.key, "schreibt · nur für die Fahrer-PCs"),
                ("anon public", self.anon, "liest · für den Kommandostand")):
            zeile = tk.Frame(karte, bg=PANEL); zeile.pack(fill="x", padx=18, pady=6)
            tk.Label(zeile, text=label.upper(), bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 8, "bold"), width=20, anchor="w").pack(side="left")
            tk.Entry(zeile, textvariable=var, bg=BG, fg=INK, insertbackground=INK,
                     relief="flat", font=("Consolas", 9)).pack(
                side="left", fill="x", expand=True, ipady=6, padx=(0, 10))
            tk.Label(zeile, text=hinweis, bg=PANEL, fg=MUTED,
                     font=("Segoe UI", 8), width=30, anchor="w").pack(side="left")

        leiste = tk.Frame(karte, bg=PANEL); leiste.pack(fill="x", padx=18, pady=(10, 18))
        tk.Button(leiste, text="PRÜFEN", command=self._pruefen, bg=ORANGE, fg="#12100e",
                  relief="flat", font=("Bahnschrift Condensed", 16, "bold"),
                  cursor="hand2").pack(side="left", ipadx=22, ipady=7)
        tk.Button(leiste, text="Speichern", command=self._zugang_speichern, bg=PANEL2,
                  fg=INK, relief="flat", font=("Segoe UI", 9),
                  cursor="hand2").pack(side="left", padx=10, ipadx=12, ipady=8)

        tk.Label(f, text="ERGEBNIS", bg=BG, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(18, 6))
        rahmen = tk.Frame(f, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        rahmen.pack(fill="both", expand=True, pady=(0, 16))
        self.pruef = tk.Text(rahmen, bg=PANEL, fg=MUTED, relief="flat", state="disabled",
                             font=("Consolas", 9), padx=14, pady=12)
        self.pruef.pack(fill="both", expand=True)

    def _zugang_speichern(self):
        self.cfg.update({"supabase_url": self.url.get().strip(),
                         "supabase_key": self.key.get().strip(),
                         "anon_key": self.anon.get().strip()})
        self.cfg.setdefault("driver_name", "")
        self._save()
        self._melden("Zugangsdaten gespeichert.", GREEN)

    def _log(self, text: str, reset: bool = False):
        self.pruef.configure(state="normal")
        if reset:
            self.pruef.delete("1.0", "end")
        self.pruef.insert("end", text + "\n")
        self.pruef.see("end")
        self.pruef.configure(state="disabled")
        self.root.update_idletasks()

    def _pruefen(self):
        self._zugang_speichern()
        self._log("Prüfe …", reset=True)
        threading.Thread(target=self._pruefen_thread, daemon=True).start()

    def _pruefen_thread(self):
        ok, warn = 0, 0
        r = self.rest()
        if not self.url.get().startswith("https://") or ".supabase.co" not in self.url.get():
            self._log("[FEHLER] Die URL sieht nicht nach einem Supabase-Projekt aus.")
            return
        try:
            r("sessions?select=id&limit=1")
            self._log("[  OK  ] Verbindung zur Datenbank"); ok += 1
        except urllib.error.HTTPError as exc:
            self._log(f"[FEHLER] Verbindung: HTTP {exc.code}")
            if exc.code == 401:
                self._log("         Der Schlüssel passt nicht. Steht dort der service_role-Key?")
            return
        except Exception as exc:
            self._log(f"[FEHLER] Verbindung: {exc}")
            self._log("         Kein Netz, falsche URL, oder das Projekt ist pausiert.")
            return

        fehlt = []
        for t in TABELLEN + VIEWS:
            try:
                r(f"{t}?select=*&limit=1")
            except Exception:
                fehlt.append(t)
        if fehlt:
            self._log(f"[FEHLER] Es fehlen: {', '.join(fehlt)}")
            self._log("         sql/00_setup_all.sql im Supabase SQL-Editor ausführen.")
            return
        self._log(f"[  OK  ] Schema: {len(TABELLEN)} Tabellen, {len(VIEWS)} Views"); ok += 1

        test = None
        try:
            zeilen = r("sessions", "POST", {"sim": "LMU", "track_name": "SETUP-TEST",
                                            "planned_hours": 0, "is_active": False},
                       prefer="return=representation")
            test = zeilen[0]["id"]
            self._log("[  OK  ] Schreibrecht"); ok += 1
        except Exception:
            self._log("[FEHLER] Kein Schreibrecht - steht oben der anon- statt service_role-Key?")
            return

        try:
            lap = r("laps", "POST", {"session_id": test, "lap_num": 1, "lap_time": 95.1},
                    prefer="return=representation")
            r("stint_telemetry", "POST", {"lap_id": lap[0]["id"], "session_id": test,
                                          "fuel_used_l": 3.2}, prefer="return=representation")
            geprueft = r(f"v_laps_full?session_id=eq.{test}&select=fuel_used_l")
            if geprueft and geprueft[0].get("fuel_used_l") is not None:
                self._log("[  OK  ] Datenkette bis in die Auswertung"); ok += 1
            else:
                self._log("[FEHLER] Die Auswertung liefert keine Telemetrie")
        except Exception as exc:
            self._log(f"[FEHLER] Datenkette: {exc}")

        if self.anon.get():
            try:
                self.rest(anon=True)("sessions?select=id&limit=1")
                self._log("[  OK  ] Kommandostand-Schlüssel liest"); ok += 1
            except Exception:
                self._log("[FEHLER] Der anon-Schlüssel kommt nicht durch")
            try:
                self.rest(anon=True)("sessions", "POST", {"track_name": "X", "is_active": False},
                                     prefer="return=representation")
                self._log("[FEHLER] Der anon-Schlüssel darf SCHREIBEN - 00_setup_all.sql nochmal ausführen")
            except urllib.error.HTTPError as exc:
                if exc.code in (401, 403, 404):
                    self._log("[  OK  ] Kommandostand-Schlüssel kann nicht schreiben"); ok += 1
        else:
            self._log("[ HINW ] Kein anon-Schlüssel eingetragen - nicht geprüft"); warn += 1

        if test:
            try:
                r(f"sessions?id=eq.{test}", "DELETE")
                self._log("[  OK  ] Testdaten aufgeräumt")
            except Exception:
                self._log("[ HINW ] Testsession konnte nicht gelöscht werden"); warn += 1

        self._log("")
        self._log("Alles bereit." if not warn else f"Bereit, mit {warn} Hinweis(en).")
        self.root.after(0, self._fahrer_laden)

    # -- Reiter 2: Fahrer --------------------------------------------
    def _tab_fahrer(self):
        f = tk.Frame(self.tabs, bg=BG); self.tabs.add(f, text="2 · Fahrer")
        tk.Label(f, bg=BG, fg=MUTED, justify="left", wraplength=780, font=("Segoe UI", 9),
                 text="Diese Namen erscheinen im Auswahlfeld der Fahrer und in der "
                      "Auswertung. Die Fahrzeit ist das Lenkzeitlimit aus eurem Reglement "
                      "in Minuten."
                 ).pack(anchor="w", pady=(16, 10))

        rahmen = tk.Frame(f, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        rahmen.pack(fill="both", expand=True)
        spalten = ("name", "kurz", "limit")
        self.liste = ttk.Treeview(rahmen, columns=spalten, show="headings", height=10)
        for spalte, text, breite in (("name", "Fahrer", 300), ("kurz", "Kürzel", 100),
                                     ("limit", "Fahrzeit-Limit (min)", 180)):
            self.liste.heading(spalte, text=text)
            self.liste.column(spalte, width=breite, anchor="w")
        stil = ttk.Style()
        stil.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=INK,
                       borderwidth=0, rowheight=28)
        stil.configure("Treeview.Heading", background=PANEL2, foreground=MUTED,
                       borderwidth=0, font=("Segoe UI", 8, "bold"))
        stil.map("Treeview", background=[("selected", PANEL2)])
        self.liste.pack(fill="both", expand=True, padx=2, pady=2)

        leiste = tk.Frame(f, bg=BG); leiste.pack(fill="x", pady=14)
        for text, befehl in (("Hinzufügen", self._fahrer_neu),
                             ("Umbenennen", self._fahrer_umbenennen),
                             ("Entfernen", self._fahrer_weg),
                             ("Neu laden", self._fahrer_laden)):
            tk.Button(leiste, text=text, command=befehl, bg=PANEL2, fg=INK, relief="flat",
                      font=("Segoe UI", 9), cursor="hand2").pack(
                side="left", padx=(0, 8), ipadx=12, ipady=7)

    def _fahrer_laden(self):
        for eintrag in self.liste.get_children():
            self.liste.delete(eintrag)
        if not self.url.get() or not self.key.get():
            return
        try:
            zeilen = self.rest()("drivers?select=driver_name,short_name,max_total_min&order=driver_name")
        except Exception as exc:
            self._melden(f"Fahrer konnten nicht geladen werden: {exc}", AMBER)
            return
        for z in zeilen:
            self.liste.insert("", "end", values=(z["driver_name"], z.get("short_name") or "",
                                                 z.get("max_total_min") or 840))
        self._melden(f"{len(zeilen)} Fahrer geladen.", MUTED)

    def _fahrer_neu(self):
        name = self._frage("Neuer Fahrer", "Name, genau wie er angezeigt werden soll:")
        if not name:
            return
        anzahl = len(self.liste.get_children())
        try:
            self.rest()("drivers", "POST", {
                "driver_name": name, "short_name": name[:3].upper(),
                "color": FARBEN[anzahl % len(FARBEN)], "max_total_min": 840},
                prefer="return=representation")
            self._fahrer_laden()
        except Exception as exc:
            messagebox.showerror("Ging nicht", f"Fahrer anlegen fehlgeschlagen:\n{exc}")

    def _auswahl(self) -> str | None:
        sel = self.liste.selection()
        if not sel:
            messagebox.showinfo("Nichts ausgewählt", "Bitte erst einen Fahrer anklicken.")
            return None
        return self.liste.item(sel[0])["values"][0]

    def _fahrer_umbenennen(self):
        alt = self._auswahl()
        if not alt:
            return
        neu = self._frage("Umbenennen", f"Neuer Name für „{alt}“:", alt)
        if not neu or neu == alt:
            return
        try:
            self.rest()(f"drivers?driver_name=eq.{urllib.parse.quote(alt)}", "PATCH",
                        {"driver_name": neu, "short_name": neu[:3].upper()})
            self._fahrer_laden()
        except Exception as exc:
            messagebox.showerror("Ging nicht", str(exc))

    def _fahrer_weg(self):
        name = self._auswahl()
        if not name:
            return
        if not messagebox.askyesno(
                "Wirklich entfernen?",
                f"„{name}“ aus der Fahrerliste entfernen?\n\n"
                "Bereits gefahrene Runden bleiben erhalten, verlieren aber "
                "die Zuordnung zu diesem Namen."):
            return
        try:
            self.rest()(f"drivers?driver_name=eq.{urllib.parse.quote(name)}", "DELETE")
            self._fahrer_laden()
        except Exception as exc:
            messagebox.showerror("Ging nicht", str(exc))

    def _frage(self, titel: str, text: str, vorgabe: str = "") -> str | None:
        fenster = tk.Toplevel(self.root); fenster.configure(bg=BG); fenster.title(titel)
        fenster.transient(self.root); fenster.grab_set(); fenster.resizable(False, False)
        tk.Label(fenster, text=text, bg=BG, fg=INK, font=("Segoe UI", 10)).pack(
            padx=24, pady=(22, 10), anchor="w")
        var = tk.StringVar(value=vorgabe)
        eingabe = tk.Entry(fenster, textvariable=var, bg=PANEL, fg=INK, relief="flat",
                           insertbackground=INK, font=("Segoe UI", 12), width=34)
        eingabe.pack(padx=24, ipady=7); eingabe.focus_set(); eingabe.select_range(0, "end")
        ergebnis = {}
        def ok():
            ergebnis["v"] = var.get().strip(); fenster.destroy()
        tk.Button(fenster, text="OK", command=ok, bg=ORANGE, fg="#12100e", relief="flat",
                  font=("Bahnschrift Condensed", 14, "bold"), cursor="hand2").pack(
            pady=18, ipadx=26, ipady=5)
        eingabe.bind("<Return>", lambda _e: ok())
        self.root.wait_window(fenster)
        return ergebnis.get("v") or None

    # -- Reiter 3: Verteilen -----------------------------------------
    def _tab_verteilen(self):
        f = tk.Frame(self.tabs, bg=BG); self.tabs.add(f, text="3 · Verteilen")

        karte = tk.Frame(f, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        karte.pack(fill="x", pady=(16, 12))
        tk.Label(karte, text="TEAM-CODE FÜR DIE ANDEREN FAHRER", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=18, pady=(16, 6))
        tk.Label(karte, bg=PANEL, fg=MUTED, justify="left", wraplength=760,
                 font=("Segoe UI", 9),
                 text="Jeder installiert denselben Installer und fügt beim ersten Start "
                      "diesen Code ein. Danach nie wieder. Der Code enthält den "
                      "service_role-Schlüssel — direkt verschicken, nicht in einen "
                      "offenen Kanal."
                 ).pack(anchor="w", padx=18)
        self.code = tk.Text(karte, height=4, bg=BG, fg=TURQ, relief="flat", wrap="char",
                            font=("Consolas", 8), padx=12, pady=10)
        self.code.pack(fill="x", padx=18, pady=12)
        leiste = tk.Frame(karte, bg=PANEL); leiste.pack(fill="x", padx=18, pady=(0, 18))
        tk.Button(leiste, text="CODE ERZEUGEN", command=self._code_erzeugen, bg=ORANGE,
                  fg="#12100e", relief="flat", font=("Bahnschrift Condensed", 15, "bold"),
                  cursor="hand2").pack(side="left", ipadx=18, ipady=6)
        tk.Button(leiste, text="In Zwischenablage", command=self._code_kopieren, bg=PANEL2,
                  fg=INK, relief="flat", font=("Segoe UI", 9), cursor="hand2").pack(
            side="left", padx=10, ipadx=12, ipady=8)

        karte2 = tk.Frame(f, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        karte2.pack(fill="x")
        tk.Label(karte2, text="KOMMANDOSTAND", bg=PANEL, fg=MUTED,
                 font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=18, pady=(16, 6))
        tk.Label(karte2, bg=PANEL, fg=MUTED, justify="left", wraplength=760,
                 font=("Segoe UI", 9),
                 text="Schreibt die config.js neben die index.html. Danach zeigt der "
                      "Kommandostand sofort Daten, ohne dass jemand einen Schlüssel "
                      "eintippt. Es wird nur der anon-Schlüssel eingetragen — der darf "
                      "nur lesen."
                 ).pack(anchor="w", padx=18)
        tk.Button(karte2, text="config.js schreiben", command=self._dashboard_config,
                  bg=PANEL2, fg=INK, relief="flat", font=("Segoe UI", 9),
                  cursor="hand2").pack(anchor="w", padx=18, pady=16, ipadx=12, ipady=8)

    def _code_erzeugen(self):
        if not self.url.get() or not self.key.get():
            messagebox.showinfo("Fehlt noch", "Erst unter „1 · Zugang“ die Daten eintragen.")
            return
        namen = [self.liste.item(e)["values"][0] for e in self.liste.get_children()]
        sys.path.insert(0, str(ROOT / "client"))
        try:
            import teamcode
        except ImportError:
            messagebox.showerror("Fehlt", "teamcode.py wurde nicht gefunden.")
            return
        code = teamcode.encode(self.url.get(), self.key.get(), namen)
        self.code.delete("1.0", "end"); self.code.insert("1.0", code)
        self._melden(f"Code erzeugt ({len(code)} Zeichen, {len(namen)} Fahrer).", GREEN)

    def _code_kopieren(self):
        code = self.code.get("1.0", "end").strip()
        if not code:
            self._code_erzeugen()
            code = self.code.get("1.0", "end").strip()
        if code:
            self.root.clipboard_clear(); self.root.clipboard_append(code)
            self._melden("Team-Code liegt in der Zwischenablage.", GREEN)

    def _dashboard_config(self):
        if not self.anon.get():
            messagebox.showinfo("Fehlt noch", "Trag unter „1 · Zugang“ den anon-Schlüssel ein.")
            return
        ziel = ROOT / "dashboard"
        if not (ziel / "index.html").exists():
            gewaehlt = filedialog.askdirectory(title="Ordner mit der index.html wählen")
            if not gewaehlt:
                return
            ziel = Path(gewaehlt)
        inhalt = (
            "window.PITWALL_CONFIG = {\n"
            f'  supabaseUrl: "{self.url.get().rstrip("/")}",\n'
            f'  supabaseKey: "{self.anon.get()}",\n'
            '  sessionId: "",\n  refreshMs: 5000,\n  stintMinutes: 65,\n'
            '  tyreFloorPct: 20,\n  brakeLoadWarn: 1500,\n  brakeLoadCrit: 3000,\n'
            '  ownCarNumber: "76"\n};\n')
        try:
            (ziel / "config.js").write_text(inhalt, encoding="utf-8")
            self._melden(f"config.js geschrieben nach {ziel}", GREEN)
        except Exception as exc:
            messagebox.showerror("Ging nicht", str(exc))

    # ----------------------------------------------------------------
    def _melden(self, text: str, farbe: str = MUTED):
        self.status.configure(text=text, fg=farbe)


def main():
    root = tk.Tk()
    Einrichter(root)
    root.mainloop()


if __name__ == "__main__":
    main()
