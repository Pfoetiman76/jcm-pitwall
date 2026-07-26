-- ============================================================
-- 15_trackmap.sql — echte Streckenkontur aus /rest/watch/trackmap.
-- Der Client laedt sie einmal pro Session hoch; das Dashboard zeichnet sie als
-- Basis (Welt-x/z, deckungsgleich mit den Fahrzeugpositionen).
-- Idempotent. Nicht-sensible Geometrie -> Leserechte wie bei den anderen Tabellen.
-- ============================================================

create table if not exists session_trackmap (
    session_id uuid primary key references sessions(id) on delete cascade,
    line       jsonb not null,          -- [[x,z], ...] Ideallinie (geschlossen)
    pit        jsonb,                    -- [[x,z], ...] Boxengasse (offen)
    created_at timestamptz default now()
);

alter table session_trackmap enable row level security;

-- Lesen fuer alle (Dashboard nutzt den anon-Key) - analog zu laps/stint_telemetry.
drop policy if exists tm_select on session_trackmap;
create policy tm_select on session_trackmap for select using (true);

-- Schreiben/Aktualisieren wie der Client die Runden schreibt (upsert je Session).
drop policy if exists tm_insert on session_trackmap;
create policy tm_insert on session_trackmap for insert with check (true);
drop policy if exists tm_update on session_trackmap;
create policy tm_update on session_trackmap for update using (true) with check (true);

notify pgrst, 'reload schema';
