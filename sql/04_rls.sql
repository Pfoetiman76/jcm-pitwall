-- ============================================================
-- JCM Pitwall - 04 Zugriffsrechte (RLS)
-- Nach 01 + 02 ausfuehren. anon: nur lesen. service_role umgeht RLS.
-- ============================================================

do $$
declare t text;
begin
  foreach t in array array['drivers','sessions','laps','stint_telemetry','stints',
                           'events','field_state','opponent_laps','weather_log']
  loop
    execute format('alter table %I enable row level security', t);
    execute format('drop policy if exists %I on %I', t || '_insert', t);
    execute format('drop policy if exists %I on %I', t || '_update', t);
    execute format('drop policy if exists %I on %I', t || '_read', t);
    execute format('create policy %I on %I for select to anon, authenticated using (true)',
                   t || '_read', t);
  end loop;
end $$;
