"""Einzige Versionsquelle des Clients.
Der CI-Build schreibt client/_version.py mit dem Release-Tag -> hat Vorrang.
Der Fallback hier gilt nur fuer lokale Laeufe OHNE _version.py und wird
NICHT automatisch ueberschrieben; er darf ruhig hinterherhinken."""
try:
    from _version import VERSION        # vom CI erzeugt (client/_version.py)
except Exception:
    VERSION = "1.1.0"                    # Fallback nur fuer lokale Laeufe