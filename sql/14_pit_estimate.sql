-- ============================================================
-- 14_pit_estimate.sql — Live geplante Boxenstoppdauer aus
-- /rest/strategy/pitstop-estimate (Sekunden je Bestandteil).
-- Selbststaendig: bringt die Dent-/Flat-Spalten aus 13 sicherheitshalber mit
-- (add if not exists) und baut v_laps_full mit dem kompletten Satz neu.
-- Idempotent, Daten bleiben. Ersetzt 13 mit, wenn beide laufen ist es egal.
-- ============================================================

-- Karosserieschaden (aus 13, defensiv wiederholt)
alter table stint_telemetry add column if not exists dent_front smallint;
alter table stint_telemetry add column if not exists dent_rear  smallint;
alter table stint_telemetry add column if not exists detached   boolean;
alter table stint_telemetry add column if not exists flat_fl    boolean;
alter table stint_telemetry add column if not exists flat_fr    boolean;
alter table stint_telemetry add column if not exists flat_rl    boolean;
alter table stint_telemetry add column if not exists flat_rr    boolean;

-- Live-Boxenstopp
alter table stint_telemetry add column if not exists pit_estimate_s real;
alter table stint_telemetry add column if not exists pit_est_fuel   real;
alter table stint_telemetry add column if not exists pit_est_tires  real;
alter table stint_telemetry add column if not exists pit_est_damage real;
alter table stint_telemetry add column if not exists pit_est_driver real;

drop view if exists v_laps_full;
create view v_laps_full as
select
    l.id, l.session_id, l.lap_num, l.lap_time,
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
    t.suspension_max_pct,
    t.dent_front, t.dent_rear, t.detached,
    t.flat_fl, t.flat_fr, t.flat_rl, t.flat_rr,
    t.pit_estimate_s, t.pit_est_fuel, t.pit_est_tires, t.pit_est_damage, t.pit_est_driver
from laps l
left join drivers d        on d.id = l.driver_id
left join stint_telemetry t on t.lap_id = l.id;

alter view v_laps_full set (security_invoker = true);

notify pgrst, 'reload schema';