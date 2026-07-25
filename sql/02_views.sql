-- ============================================================
-- JCM Pitwall - Views
-- Ziel: das Dashboard holt pro Refresh 3 flache Endpunkte,
-- statt clientseitig zu joinen.
-- ============================================================

-- Runde + Telemetrie + Fahrername in einer Zeile
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
    t.damage_index
from laps l
left join drivers d        on d.id = l.driver_id
left join stint_telemetry t on t.lap_id = l.id;

-- Verbrauchs-EMA der letzten 5 gueltigen Renn-Runden pro Session.
-- Outlier (In-/Outlap, FCY, ungueltig) fliegen raus - genau wie im Konzept.
create or replace view v_fuel_strategy as
with clean as (
    select
        l.session_id,
        l.lap_num,
        t.fuel_used_l,
        t.fuel_remaining_l,
        row_number() over (partition by l.session_id order by l.lap_num desc) as rn
    from laps l
    join stint_telemetry t on t.lap_id = l.id
    where l.is_valid
      and not l.is_inlap
      and not l.is_outlap
      and not l.under_fcy
      and t.fuel_used_l is not null
      and t.fuel_used_l > 0
)
select
    session_id,
    count(*)                                             as sample_laps,
    round(avg(fuel_used_l)::numeric, 3)                  as avg_fuel_per_lap,
    round(max(fuel_used_l)::numeric, 3)                  as worst_fuel_per_lap,
    round(min(fuel_used_l)::numeric, 3)                  as best_fuel_per_lap,
    round((max(fuel_remaining_l) filter (where rn = 1))::numeric, 3) as fuel_remaining_l,
    round(
        ((max(fuel_remaining_l) filter (where rn = 1)) / nullif(avg(fuel_used_l), 0))::numeric,
        2
    )                                                    as laps_remaining
from clean
where rn <= 5
group by session_id;

-- Fahrer-Lenkzeiten und Bestzeiten je Session
create or replace view v_driver_summary as
select
    l.session_id,
    d.id            as driver_id,
    d.driver_name,
    coalesce(d.short_name, upper(left(d.driver_name, 3))) as short_name,
    d.color,
    d.max_total_min,
    d.max_stint_min,
    count(*)                                          as laps_done,
    round(min(l.lap_time) filter (where l.is_valid and not l.is_inlap and not l.is_outlap), 3) as best_lap,
    round(avg(l.lap_time) filter (where l.is_valid and not l.is_inlap and not l.is_outlap), 3) as avg_lap,
    round((sum(l.lap_time) / 60.0)::numeric, 1)       as drive_time_min,
    max(l.finished_at)                                as last_seen
from laps l
join drivers d on d.id = l.driver_id
group by l.session_id, d.id, d.driver_name, d.short_name, d.color, d.max_total_min, d.max_stint_min;
