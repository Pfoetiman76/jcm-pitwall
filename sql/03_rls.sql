-- ============================================================
-- JCM Pitwall - Row Level Security
--
-- Annahme (bewusst getroffen): der anon-Key liegt auf 6 Fahrer-PCs
-- und im Dashboard. Er kann damit schreiben und lesen, aber NICHT
-- loeschen oder aendern. Das ist der pragmatische Kompromiss fuer
-- ein Team-Tool - kein Login-Flow fuer 6 Leute um 3 Uhr nachts.
--
-- Wer haerter absichern will: service_role-Key nur im Client,
-- anon-Key nur lesend, und die Insert-Policies unten streichen.
-- ============================================================

alter table drivers          enable row level security;
alter table sessions         enable row level security;
alter table laps             enable row level security;
alter table stint_telemetry  enable row level security;
alter table stints           enable row level security;
alter table events           enable row level security;

-- Lesen: alle Tabellen offen fuer anon
do $$
declare t text;
begin
  foreach t in array array['drivers','sessions','laps','stint_telemetry','stints','events']
  loop
    execute format('drop policy if exists %I on %I', t || '_read', t);
    execute format('create policy %I on %I for select using (true)', t || '_read', t);

    execute format('drop policy if exists %I on %I', t || '_insert', t);
    execute format('create policy %I on %I for insert with check (true)', t || '_insert', t);
  end loop;
end $$;

-- Update nur dort, wo der Client es braucht (Session beenden, Stint schliessen)
drop policy if exists sessions_update on sessions;
create policy sessions_update on sessions for update using (true) with check (true);

drop policy if exists stints_update on stints;
create policy stints_update on stints for update using (true) with check (true);

-- Kein DELETE fuer anon. Bewusst. Nichts loescht dir mitten im
-- 24h-Rennen aus Versehen die Rundendaten.
