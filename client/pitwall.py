"""JCM Pitwall - gemeinsamer Einstiegspunkt.

Ohne Argumente oeffnet sich das Fahrer-Fenster.
Mit --run-client laeuft der Client im Hintergrund (so ruft das Fenster
sich selbst als eigenen Prozess auf - poetig, damit aus allem eine
einzige .exe werden kann).
"""

import sys
import gui
import run_client

if "--run-client" in sys.argv:
    sys.argv.remove("--run-client")
    run_client.main()
else:
    gui.main()