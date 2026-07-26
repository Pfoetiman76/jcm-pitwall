-- 10_stint_telemetry_rest_cols.sql
-- Nachtrag: stint_telemetry fehlen die REST-Bremsbelag-/Schaden-Spalten, die der
-- Client seit der LMU-REST-Integration (localhost:6397) mitschickt. Fehlen sie,
-- lehnt PostgREST den ganzen Insert mit HTTP 400 ab -> stint_telemetry landet
-- nur im Spool, im Fahrer-Fenster erscheint faelschlich "Kein Netz".
-- Diese sechs Felder waren in keiner frueheren Schema-Fassung (auch nicht in 07).
-- Idempotent (add column if not exists). In Supabase: SQL Editor -> Run.

alter table stint_telemetry add column if not exists brake_pad_fl        numeric(6,2);
alter table stint_telemetry add column if not exists brake_pad_fr        numeric(6,2);
alter table stint_telemetry add column if not exists brake_pad_rl        numeric(6,2);
alter table stint_telemetry add column if not exists brake_pad_rr        numeric(6,2);
alter table stint_telemetry add column if not exists aero_damage_pct     numeric(6,2);
alter table stint_telemetry add column if not exists suspension_max_pct  numeric(6,2);

-- Ohne Reload kommt der 400 nach dem ALTER noch kurz weiter (PostgREST-Cache).
notify pgrst, 'reload schema';
