-- 12_damage_view.sql
-- Datengrundlage fuer den Schadens-Schirm.
--  1. Suspension je Ecke in stint_telemetry (der Client schickt jetzt
--     suspension_fl/fr/rl/rr zusaetzlich zum bisherigen suspension_max_pct).
--  2. v_laps_full um alle Schadensfelder erweitern - vorher kamen nur wear_*
--     durch, die REST-Felder (Bremsbelag, Aero, Suspension) fehlten im View.
-- In Supabase: SQL Editor -> Run. Idempotent.

alter table stint_telemetry add column if not exists suspension_fl numeric(6,2);
alter table stint_telemetry add column if not exists suspension_fr numeric(6,2);
alter table stint_telemetry add column if not exists suspension_rl numeric(6,2);
alter table stint_telemetry add column if not exists suspension_rr numeric(6,2);

create or replace view v_laps_full as
select
    l.id,
    l.session_id,
    l.lap_num,
    l.lap_time,
    l.s1, l.s2, l.s3,
    l.is_valid, l.is_inlap, l.is_outlap, l.under_fcy,
    l.position, l.gap_to_leader, l.race_time_s, l.finished_at,
    d.id                as driver_id,
    d.driver_name,
    coalesce(d.short_name, upper(left(d.driver_name, 3))) as short_name,
    d.color             as driver_color,
    t.fuel_used_l, t.fuel_remaining_l, t.virtual_energy_pct,
    t.wear_fl, t.wear_fr, t.wear_rl, t.wear_rr,
    t.tyre_temp_fl, t.tyre_temp_fr, t.tyre_temp_rl, t.tyre_temp_rr,
    t.tyre_press_fl, t.tyre_press_fr, t.tyre_press_rl, t.tyre_press_rr,
    t.max_brake_temp_c, t.brake_thermal_load, t.brake_friction_work,
    t.max_speed_kmh, t.avg_speed_kmh,
    t.track_temp_c, t.ambient_temp_c, t.rain_pct, t.track_wetness_pct,
    t.damage_index,
    t.brake_pad_fl, t.brake_pad_fr, t.brake_pad_rl, t.brake_pad_rr,
    t.aero_damage_pct,
    t.suspension_fl, t.suspension_fr, t.suspension_rl, t.suspension_rr,
    t.suspension_max_pct
from laps l
left join drivers d        on d.id = l.driver_id
left join stint_telemetry t on t.lap_id = l.id;

-- create or replace setzt View-Optionen zurueck -> security_invoker erneut setzen
-- (sonst kommt der Security-Advisor-Fehler "Security Definer View" zurueck).
alter view v_laps_full set (security_invoker = true);

notify pgrst, 'reload schema';
