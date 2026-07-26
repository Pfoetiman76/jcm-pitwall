-- 11_realtime_field_state.sql
-- Schaltet Supabase Realtime fuer field_state frei: das Dashboard abonniert die
-- Tabelle per WebSocket und bekommt jeden Client-Upsert sofort gepusht, statt zu
-- pollen. Latenz = nur noch der Client-Sendetakt, kein Poll-Egress fuer den
-- Feldstand mehr. In Supabase: SQL Editor -> Run.
--
-- Realtime respektiert RLS: der anon-Key darf field_state via SELECT lesen
-- (bestehende Policy), also kommen die Events beim Dashboard an. postgres_changes
-- liefert die komplette neue Zeile in payload.new schon bei REPLICA IDENTITY
-- DEFAULT - kein FULL noetig, weil wir 'old' nicht brauchen.
--
-- Idempotent: doppeltes Hinzufuegen zur Publication wird abgefangen.

do $$
begin
  alter publication supabase_realtime add table public.field_state;
exception
  when duplicate_object then null;   -- schon in der Publication
  when undefined_object then
    raise notice 'Publication supabase_realtime fehlt - Realtime im Supabase-Projekt aktivieren.';
end $$;
