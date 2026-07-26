"""JCM Pitwall - gemeinsamer Einstiegspunkt.

Ohne Argumente oeffnet sich das Fahrer-Fenster.
Mit --run-client laeuft der Client im Hintergrund (so ruft das Fenster
sich selbst als eigenen Prozess auf - noetig, damit aus allem eine
einzige .exe werden kann).
"""
import sys

if "--run-client" in sys.argv:
    sys.argv.remove("--run-client")
    import run_client
    sys.exit(run_client.main())
else:
    import gui
    gui.main()