-- ============================================================
-- JCM Pitwall - 03 Views (flache Endpunkte fuers Dashboard)
-- Nach 01 + 02 ausfuehren. security_invoker=true -> Security Advisor bleibt
-- gruen und die anon-RLS greift korrekt.
-- ============================================================

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
    t.suspension_max_pct
from laps l
left join drivers d        on d.id = l.driver_id
left join stint_telemetry t on t.lap_id = l.id;

create or replace view v_fuel_strategy as
with clean as (
    select
        l.session_id, l.lap_num, t.fuel_used_l, t.fuel_remaining_l,
        row_number() over (partition by l.session_id order by l.lap_num desc) as rn
    from laps l
    join stint_telemetry t on t.lap_id = l.id
    where l.is_valid and not l.is_inlap and not l.is_outlap and not l.under_fcy
      and t.fuel_used_l is not null and t.fuel_used_l > 0
)
select
    session_id,
    count(*)                                             as sample_laps,
    round(avg(fuel_used_l)::numeric, 3)                  as avg_fuel_per_lap,
    round(max(fuel_used_l)::numeric, 3)                  as worst_fuel_per_lap,
    round(min(fuel_used_l)::numeric, 3)                  as best_fuel_per_lap,
    round((max(fuel_remaining_l) filter (where rn = 1))::numeric, 3) as fuel_remaining_l,
    round(((max(fuel_remaining_l) filter (where rn = 1)) / nullif(avg(fuel_used_l), 0))::numeric, 2) as laps_remaining
from clean
where rn <= 5
group by session_id;

create or replace view v_driver_summary as
select
    l.session_id,
    d.id            as driver_id,
    d.driver_name,
    coalesce(d.short_name, upper(left(d.driver_name, 3))) as short_name,
    d.color, d.max_total_min, d.max_stint_min,
    count(*)                                          as laps_done,
    round(min(l.lap_time) filter (where l.is_valid and not l.is_inlap and not l.is_outlap), 3) as best_lap,
    round(avg(l.lap_time) filter (where l.is_valid and not l.is_inlap and not l.is_outlap), 3) as avg_lap,
    round((sum(l.lap_time) / 60.0)::numeric, 1)       as drive_time_min,
    max(l.finished_at)                                as last_seen
from laps l
join drivers d on d.id = l.driver_id
group by l.session_id, d.id, d.driver_name, d.short_name, d.color, d.max_total_min, d.max_stint_min;

create or replace view v_field_pace as
with ranked as (
    select
        session_id, vehicle_id, driver_name, car_class, car_number, lap_num, lap_time,
        row_number() over (partition by session_id, vehicle_id order by lap_num desc) as rn
    from opponent_laps
    where lap_time is not null and lap_time > 0 and not in_pits
)
select
    session_id, vehicle_id,
    max(driver_name)                              as driver_name,
    max(car_class)                                as car_class,
    max(car_number)                               as car_number,
    count(*) filter (where rn <= 5)               as pace_samples,
    round(avg(lap_time) filter (where rn <= 5), 3) as avg5,
    round(min(lap_time), 3)                        as best_lap,
    round(max(lap_time) filter (where rn = 1), 3)  as last_lap,
    max(lap_num)                                   as laps_done
from ranked
group by session_id, vehicle_id;

create or replace view v_weather_trend as
select
    session_id,
    (floor(race_time_s / 300) * 300)::numeric        as bucket_s,
    round(avg(track_temp_c), 2)                      as track_temp_c,
    round(avg(ambient_temp_c), 2)                    as ambient_temp_c,
    round(avg(rain_pct), 2)                          as rain_pct,
    round(avg(wetness_avg_pct), 2)                   as wetness_avg_pct,
    round(max(wetness_max_pct), 2)                   as wetness_max_pct,
    round(avg(cloud_pct), 2)                         as cloud_pct,
    round(avg(wind_kmh), 2)                          as wind_kmh
from weather_log
group by session_id, floor(race_time_s / 300)
order by bucket_s;

alter view v_laps_full      set (security_invoker = true);
alter view v_fuel_strategy  set (security_invoker = true);
alter view v_driver_summary set (security_invoker = true);
alter view v_field_pace     set (security_invoker = true);
alter view v_weather_trend  set (security_invoker = true);