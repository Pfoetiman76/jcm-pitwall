-- ============================================================
-- JCM Pitwall - KOMPLETTES SETUP IN EINER DATEI
--
-- Diese Datei ersetzt ALLE frueheren SQL-Dateien (01 bis 12).
-- Einmal in den Supabase SQL-Editor einfuegen, "Run", fertig.
-- Vollstaendig idempotent: mehrfaches Ausfuehren schadet nicht, und
-- sie bringt sowohl eine FRISCHE als auch eine schon bestehende
-- Datenbank auf den aktuellen Stand (fehlende Spalten werden ergaenzt).
--
-- Zugriff: der anon-Key darf nur LESEN. Geschrieben wird ausschliesslich
-- mit dem service_role-Key auf den Fahrer-PCs, nie im Browser.
-- ============================================================

create extension if not exists "pgcrypto";

-- ============================================================
-- 1) TABELLEN  (frische DB: voller aktueller Spaltensatz)
-- ============================================================

create table if not exists drivers (
    id              uuid primary key default gen_random_uuid(),
    driver_name     text not null unique,
    short_name      text,
    steam_id        text,
    color           text default '#ff6a13',
    max_stint_min   int  default 65,
    max_total_min   int  default 840,
    created_at      timestamptz not null default now()
);

create table if not exists sessions (
    id              uuid primary key default gen_random_uuid(),
    sim             text not null default 'LMU',
    track_name      text not null,
    car_name        text,
    car_class       text,
    session_type    text default 'RACE',
    planned_hours   numeric(5,2) default 24,
    fuel_capacity_l numeric(6,2),
    track_temp_c    numeric(5,2),
    ambient_temp_c  numeric(5,2),
    started_at      timestamptz not null default now(),
    ended_at        timestamptz,
    is_active       boolean not null default true,
    created_at      timestamptz not null default now()
);
create index if not exists sessions_active_idx on sessions (is_active, started_at desc);

create table if not exists laps (
    id              bigserial primary key,
    session_id      uuid not null references sessions(id) on delete cascade,
    driver_id       uuid references drivers(id),
    lap_num         int  not null,
    lap_time        numeric(9,3),
    s1              numeric(9,3),
    s2              numeric(9,3),
    s3              numeric(9,3),
    is_valid        boolean not null default true,
    is_inlap        boolean not null default false,
    is_outlap       boolean not null default false,
    under_fcy       boolean not null default false,
    position        int,
    gap_to_leader   numeric(9,3),
    race_time_s     numeric(12,3),
    finished_at     timestamptz not null default now(),
    unique (session_id, lap_num)
);
create index if not exists laps_session_idx on laps (session_id, lap_num desc);

create table if not exists stint_telemetry (
    lap_id              bigint primary key references laps(id) on delete cascade,
    session_id          uuid not null references sessions(id) on delete cascade,
    fuel_used_l         numeric(7,3),
    fuel_remaining_l    numeric(7,3),
    virtual_energy_pct  numeric(6,3),
    wear_fl             numeric(6,4),
    wear_fr             numeric(6,4),
    wear_rl             numeric(6,4),
    wear_rr             numeric(6,4),
    tyre_temp_fl        numeric(6,2),
    tyre_temp_fr        numeric(6,2),
    tyre_temp_rl        numeric(6,2),
    tyre_temp_rr        numeric(6,2),
    tyre_press_fl       numeric(6,2),
    tyre_press_fr       numeric(6,2),
    tyre_press_rl       numeric(6,2),
    tyre_press_rr       numeric(6,2),
    max_brake_temp_c    numeric(7,2),
    brake_thermal_load  numeric(12,2),
    brake_friction_work numeric(12,2),
    max_speed_kmh       numeric(6,2),
    avg_speed_kmh       numeric(6,2),
    track_temp_c        numeric(5,2),
    ambient_temp_c      numeric(5,2),
    rain_pct            numeric(5,2),
    track_wetness_pct   numeric(5,2),
    damage_index        numeric(5,2),
    brake_pad_fl        numeric(6,2),
    brake_pad_fr        numeric(6,2),
    brake_pad_rl        numeric(6,2),
    brake_pad_rr        numeric(6,2),
    aero_damage_pct     numeric(6,2),
    suspension_fl       numeric(6,2),
    suspension_fr       numeric(6,2),
    suspension_rl       numeric(6,2),
    suspension_rr       numeric(6,2),
    suspension_max_pct  numeric(6,2),
    created_at          timestamptz not null default now()
);
create index if not exists stint_tel_session_idx on stint_telemetry (session_id);

create table if not exists stints (
    id              bigserial primary key,
    session_id      uuid not null references sessions(id) on delete cascade,
    driver_id       uuid references drivers(id),
    stint_num       int,
    started_at      timestamptz not null default now(),
    ended_at        timestamptz,
    start_lap       int,
    end_lap         int,
    planned_end_at  timestamptz,
    note            text
);
create index if not exists stints_session_idx on stints (session_id, started_at);

create table if not exists events (
    id              bigserial primary key,
    session_id      uuid not null references sessions(id) on delete cascade,
    lap_num         int,
    kind            text not null,
    payload         jsonb default '{}'::jsonb,
    created_at      timestamptz not null default now()
);
create index if not exists events_session_idx on events (session_id, created_at desc);

create table if not exists field_state (
    session_id          uuid primary key references sessions(id) on delete cascade,
    updated_at          timestamptz not null default now(),
    race_time_s         numeric(12,3),
    leader_laps         int,
    pit_loss_s          numeric(7,2),
    track_length_m      numeric(10,2),
    session_remaining_s numeric(12,2),
    weather_forecast    jsonb,
    vehicles            jsonb not null default '[]'::jsonb,
    weather             jsonb not null default '{}'::jsonb
);

create table if not exists opponent_laps (
    id              bigserial primary key,
    session_id      uuid not null references sessions(id) on delete cascade,
    vehicle_id      int not null,
    driver_name     text,
    car_number      text,
    car_class       text,
    lap_num         int not null,
    lap_time        numeric(9,3),
    position        int,
    class_position  int,
    gap_to_leader   numeric(10,3),
    in_pits         boolean default false,
    race_time_s     numeric(12,3),
    created_at      timestamptz not null default now(),
    unique (session_id, vehicle_id, lap_num)
);
create index if not exists opp_laps_session_idx on opponent_laps (session_id, vehicle_id, lap_num desc);
create index if not exists opp_laps_class_idx   on opponent_laps (session_id, car_class);

create table if not exists weather_log (
    id              bigserial primary key,
    session_id      uuid not null references sessions(id) on delete cascade,
    race_time_s     numeric(12,3),
    track_temp_c    numeric(5,2),
    ambient_temp_c  numeric(5,2),
    rain_pct        numeric(5,2),
    wetness_avg_pct numeric(5,2),
    wetness_min_pct numeric(5,2),
    wetness_max_pct numeric(5,2),
    cloud_pct       numeric(5,2),
    wind_kmh        numeric(6,2),
    dark_cloud      numeric(5,2),
    created_at      timestamptz not null default now()
);
create index if not exists weather_session_idx on weather_log (session_id, created_at);

-- ============================================================
-- 2) SPALTEN-NACHZUG  (bestehende DB aus aelterer Fassung)
--    create table if not exists aendert existierende Tabellen NICHT,
--    darum hier alle historisch nachgereichten Spalten sichern.
-- ============================================================

alter table field_state add column if not exists pit_loss_s          numeric(7,2);
alter table field_state add column if not exists track_length_m      numeric(10,2);
alter table field_state add column if not exists session_remaining_s numeric(12,2);
alter table field_state add column if not exists weather_forecast    jsonb;

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
alter table stint_telemetry add column if not exists brake_pad_fl        numeric(6,2);
alter table stint_telemetry add column if not exists brake_pad_fr        numeric(6,2);
alter table stint_telemetry add column if not exists brake_pad_rl        numeric(6,2);
alter table stint_telemetry add column if not exists brake_pad_rr        numeric(6,2);
alter table stint_telemetry add column if not exists aero_damage_pct     numeric(6,2);
alter table stint_telemetry add column if not exists suspension_fl       numeric(6,2);
alter table stint_telemetry add column if not exists suspension_fr       numeric(6,2);
alter table stint_telemetry add column if not exists suspension_rl       numeric(6,2);
alter table stint_telemetry add column if not exists suspension_rr       numeric(6,2);
alter table stint_telemetry add column if not exists suspension_max_pct  numeric(6,2);

-- Unique-Constraint fuer den opponent_laps-Upsert (bestehende DB ohne ihn).
do $$
begin
  alter table opponent_laps add constraint opponent_laps_uniq
        unique (session_id, vehicle_id, lap_num);
exception when duplicate_table then null; when duplicate_object then null;
end $$;

-- ============================================================
-- 3) VIEWS  (immer aktuell per create or replace)
-- ============================================================

create or replace view v_laps_full as
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

-- Views mit den Rechten des Aufrufers ausfuehren (Security Advisor: kein
-- "Security Definer View" mehr; anon-RLS greift korrekt).
alter view v_laps_full      set (security_invoker = true);
alter view v_fuel_strategy  set (security_invoker = true);
alter view v_driver_summary set (security_invoker = true);
alter view v_field_pace     set (security_invoker = true);
alter view v_weather_trend  set (security_invoker = true);

-- ============================================================
-- 4) ZUGRIFFSRECHTE  (anon: nur lesen; service_role umgeht RLS)
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

drop policy if exists sessions_update on sessions;
drop policy if exists stints_update on stints;
drop policy if exists field_state_update on field_state;

-- ============================================================
-- 5) REALTIME  (field_state per WebSocket ans Dashboard pushen)
-- ============================================================

do $$
begin
  alter publication supabase_realtime add table public.field_state;
exception
  when duplicate_object then null;   -- schon in der Publication
  when undefined_object then
    raise notice 'Publication supabase_realtime fehlt - Realtime im Supabase-Projekt aktivieren.';
end $$;

notify pgrst, 'reload schema';
