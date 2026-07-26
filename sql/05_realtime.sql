-- ============================================================
-- JCM Pitwall - 05 Realtime (field_state per WebSocket-Push)
-- Nach 01-04 ausfuehren. Damit bekommt das Dashboard jeden Client-Upsert
-- sofort gepusht statt zu pollen.
-- ============================================================

do $$
begin
  alter publication supabase_realtime add table public.field_state;
exception
  when duplicate_object then null;
  when undefined_object then
    raise notice 'Publication supabase_realtime fehlt - Realtime im Supabase-Projekt aktivieren.';
end $$;

notify pgrst, 'reload schema';
