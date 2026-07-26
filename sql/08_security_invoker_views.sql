-- 08_security_invoker_views.sql
-- Fix fuer Supabase Security Advisor: "Security Definer View" (5 Fehler).
--
-- Problem: Views sind per Postgres-Default SECURITY DEFINER, laufen also mit
-- den Rechten des Owners (postgres) und umgehen damit die RLS der Basistabellen.
-- Fix: security_invoker = true -> View laeuft mit den Rechten des Aufrufers
-- (anon), RLS greift normal. Rein additiv, aendert nur die View-Option, nicht
-- die View-Definition. Idempotent (ALTER ... SET ist wiederholbar).
--
-- Voraussetzung: Postgres 15+ (Supabase erfuellt das). Falls eine View hier
-- nicht existiert, die betreffende Zeile einfach ueberspringen.

alter view public.v_laps_full      set (security_invoker = true);
alter view public.v_fuel_strategy  set (security_invoker = true);
alter view public.v_driver_summary set (security_invoker = true);
alter view public.v_field_pace     set (security_invoker = true);
alter view public.v_weather_trend  set (security_invoker = true);

-- PostgREST-Schema-Cache neu laden (wie bei 06/07), damit die API sofort greift.
notify pgrst, 'reload schema';
