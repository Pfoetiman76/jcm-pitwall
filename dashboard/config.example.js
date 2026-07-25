// In config.js umbenennen und neben index.html legen.
// Diese Datei gehört NICHT ins Repo (steht in .gitignore).
window.PITWALL_CONFIG = {
  supabaseUrl: "https://xxxxxxxxxxxx.supabase.co",
  supabaseKey: "eyJhbGciOi...",   // anon public key
  sessionId: "",                  // leer = automatisch die aktive Session
  refreshMs: 5000,                // Abfrageintervall des Dashboards
  stintMinutes: 65,               // geplante Stintlänge für die Sprit-Empfehlung
  tyreFloorPct: 20,               // Restprofil, ab dem gewechselt wird
  brakeLoadWarn: 1200,            // Hitzeintegral °C·s: Warnung
  brakeLoadCrit: 2600             // Hitzeintegral °C·s: Fading-Gefahr
};
