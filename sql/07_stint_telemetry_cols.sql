-- ============================================================
-- Nachtrag fuer bestehende Datenbanken.
-- stint_telemetry aus einer aelteren Schema-Fassung -> es fehlt
-- mindestens eine Wert-Spalte, die der Client schickt -> HTTP 400.
-- Hier werden ALLE Wert-Spalten idempotent nachgezogen; vorhandene
-- bleiben unveraendert. (lap_id/session_id sind die Schluessel und
-- ohnehin vorhanden.)
-- In Supabase: SQL Editor -> einfuegen -> Run.
-- ============================================================

alter table stint_telemetry add column if not exists fuel_used_l         numeric(7,3);
alter table stint_telemetry add column if not exists fuel_remaining_l    numeric(7,3);
alter table stint_telemetry add column if not exists virtual_energy_pct  numeric(6,3);

alter table stint_telemetry add column if not exists wear_fl             numeric(6,4);
alter table stint_telemetry add column if not exists wear_fr             numeric(6,4);
alter table stint_telemetry add column if not exists wear_rl             numeric(6,4);
alter table stint_telemetry add column if not exists wear_rr             numeric(6,4);

alter table stint_telemetry add column if not exists tyre_temp_fl        numeric(6,2);
alter table stint_telemetry add column if not exists tyre_temp_fr        numeric(6,2);
alter table stint_telemetry add column if not exists tyre_temp_rl        numeric(6,2);
alter table stint_telemetry add column if not exists tyre_temp_rr        numeric(6,2);
alter table stint_telemetry add column if not exists tyre_press_fl       numeric(6,2);
alter table stint_telemetry add column if not exists tyre_press_fr       numeric(6,2);
alter table stint_telemetry add column if not exists tyre_press_rl       numeric(6,2);
alter table stint_telemetry add column if not exists tyre_press_rr       numeric(6,2);

alter table stint_telemetry add column if not exists max_brake_temp_c    numeric(7,2);
alter table stint_telemetry add column if not exists brake_thermal_load  numeric(12,2);
alter table stint_telemetry add column if not exists brake_friction_work numeric(12,2);

alter table stint_telemetry add column if not exists max_speed_kmh       numeric(6,2);
alter table stint_telemetry add column if not exists avg_speed_kmh       numeric(6,2);
alter table stint_telemetry add column if not exists track_temp_c        numeric(5,2);
alter table stint_telemetry add column if not exists ambient_temp_c      numeric(5,2);
alter table stint_telemetry add column if not exists rain_pct            numeric(5,2);
alter table stint_telemetry add column if not exists track_wetness_pct   numeric(5,2);
alter table stint_telemetry add column if not exists damage_index        numeric(5,2);

notify pgrst, 'reload schema';
