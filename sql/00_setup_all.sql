-- ============================================================
-- JCM Pitwall - KOMPLETTES SETUP IN EINEM DURCHLAUF
--
-- Diese Datei ersetzt 01 bis 04. Einmal in den Supabase SQL-Editor
-- einfuegen, "Run", fertig. Sie ist idempotent - mehrfaches Ausfuehren
-- schadet nicht.
--
-- WICHTIG, Aenderung gegenueber der ersten Fassung:
-- der anon-Key darf hier nur noch LESEN. Geschrieben wird ausschliesslich
-- mit dem service_role-Key, der auf den 6 Fahrer-PCs liegt und nie in den
-- Browser kommt. Grund: das Dashboard ist eine statische Seite im Netz,
-- ihr Key ist damit oeffentlich. Lesbar ist unkritisch, schreibbar waere
-- eine Einladung.
-- ============================================================


-- ############ aus 01_schema.sql ############
-- ============================================================
-- JCM Pitwall - Schema Phase 1 (Supabase / PostgreSQL)
-- Rundenbasierte Aggregation, ausgelegt auf < 1 MB pro 24h-Rennen
-- Ausfuehren im Supabase SQL Editor, Reihenfolge 01 -> 02 -> 03
-- ============================================================

create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
-- drivers: die 6 Teammitglieder
-- ------------------------------------------------------------
create table if not exists drivers (
    id              uuid primary key default gen_random_uuid(),
    driver_name     text not null unique,
    short_name      text,                       -- 3 Zeichen fuer die Timing-Tower
    steam_id        text,
    color           text default '#ff6a13',     -- Farbe im Stint-Ring
    max_stint_min   int  default 65,            -- Fahrzeitlimit pro Stint
    max_total_min   int  default 840,           -- Fahrzeitlimit ueber 24h (Reglement)
    created_at      timestamptz not null default now()
);

-- ------------------------------------------------------------
-- sessions: eine Zeile pro Rennen/Training
-- ------------------------------------------------------------
create table if not exists sessions (
    id              uuid primary key default gen_random_uuid(),
    sim             text not null default 'LMU',         -- LMU | rF2
    track_name      text not null,
    car_name        text,
    car_class       text,
    session_type    text default 'RACE',                 -- PRACTICE | QUALI | RACE
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

-- ------------------------------------------------------------
-- laps: eine Zeile pro abgeschlossener Runde
-- ------------------------------------------------------------
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
    under_fcy       boolean not null default false,   -- Full Course Yellow / SC
    position        int,
    gap_to_leader   numeric(9,3),
    race_time_s     numeric(12,3),                    -- Rennzeit bei Start/Ziel
    finished_at     timestamptz not null default now(),
    unique (session_id, lap_num)
);

create index if not exists laps_session_idx on laps (session_id, lap_num desc);

-- ------------------------------------------------------------
-- stint_telemetry: aggregierte Fahrzeugwerte pro Runde
-- 1 Zeile je Runde, ~350 Zeilen pro 24h -> vernachlaessigbar
-- ------------------------------------------------------------
create table if not exists stint_telemetry (
    lap_id              bigint primary key references laps(id) on delete cascade,
    session_id          uuid not null references sessions(id) on delete cascade,

    fuel_used_l         numeric(7,3),
    fuel_remaining_l    numeric(7,3),
    virtual_energy_pct  numeric(6,3),      -- Hypercar / LMDh

    wear_fl             numeric(6,4),      -- 1.0 = neu, 0.0 = runter (LMU mWear)
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
    brake_thermal_load  numeric(12,2),     -- Integral(max(T-T_opt,0)) dt in Grad C*s
    brake_friction_work numeric(12,2),     -- Integral(Bremsdruck * v) dt, relativ

    max_speed_kmh       numeric(6,2),
    avg_speed_kmh       numeric(6,2),
    track_temp_c        numeric(5,2),
    ambient_temp_c      numeric(5,2),
    rain_pct            numeric(5,2),
    track_wetness_pct   numeric(5,2),

    damage_index        numeric(5,2),      -- abgeleitet, kein Sim-Wert
    created_at          timestamptz not null default now()
);

create index if not exists stint_tel_session_idx on stint_telemetry (session_id);

-- ------------------------------------------------------------
-- stints: Fahrerwechsel-Protokoll (Lenkzeit-Ueberwachung)
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- events: Boxenstopp, FCY, Schaden, Reifenwechsel, Notizen
-- ------------------------------------------------------------
create table if not exists events (
    id              bigserial primary key,
    session_id      uuid not null references sessions(id) on delete cascade,
    lap_num         int,
    kind            text not null,     -- PIT | FCY | DAMAGE | TYRES | NOTE | DRIVER_CHANGE
    payload         jsonb default '{}'::jsonb,
    created_at      timestamptz not null default now()
);

create index if not exists events_session_idx on events (session_id, created_at desc);

-- ############ aus 02_views.sql ############
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

-- ############ aus 04_field.sql ############
-- ============================================================
-- JCM Pitwall - Erweiterung: Feld, Gegner-Runden, Wetter
-- Nach 01/02/03 ausfuehren. Rein additiv, aendert nichts Bestehendes.
--
-- Speicher-Ueberlegung (Free Tier, 500 MB):
--   field_state    1 Zeile pro Session, wird alle 5 s ueberschrieben -> konstant
--   opponent_laps  ~30 Autos x ~350 Runden = ~10.000 Zeilen pro 24h -> ~2 MB
--   weather_log    1 Zeile pro Minute = 1440 Zeilen pro 24h -> ~0,2 MB
-- Zusammen bleibt ein 24h-Rennen unter 3 MB.
-- ============================================================

-- ------------------------------------------------------------
-- field_state: Momentaufnahme des kompletten Feldes.
-- EINE Zeile pro Session, alle paar Sekunden per Upsert ersetzt.
-- Das ist der Trick gegen die Zeilenexplosion: Live-Abstaende
-- brauchen keine Historie, nur den aktuellen Stand.
-- ------------------------------------------------------------
create table if not exists field_state (
    session_id      uuid primary key references sessions(id) on delete cascade,
    updated_at      timestamptz not null default now(),
    race_time_s     numeric(12,3),
    leader_laps     int,
    pit_loss_s      numeric(7,2),
    vehicles        jsonb not null default '[]'::jsonb,
    weather         jsonb not null default '{}'::jsonb
);

-- ------------------------------------------------------------
-- opponent_laps: abgeschlossene Runden aller anderen Fahrzeuge.
-- Basis fuer Bestzeiten, Schnitt der letzten 5 Runden und Stintlaengen
-- der Konkurrenz.
-- ------------------------------------------------------------
create table if not exists opponent_laps (
    id              bigserial primary key,
    session_id      uuid not null references sessions(id) on delete cascade,
    vehicle_id      int not null,          -- mID aus der Shared Memory
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

-- ------------------------------------------------------------
-- weather_log: eine Zeile pro Minute fuer den Verlauf ueber 24h
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------
-- View: Schnitt der letzten 5 Runden je Fahrzeug (Feld + eigenes Auto)
-- Genau die Kennzahl, die im Timing-Tower gebraucht wird: nicht die
-- Bestzeit, sondern was das Auto GERADE faehrt.
-- ------------------------------------------------------------
create or replace view v_field_pace as
with ranked as (
    select
        session_id, vehicle_id, driver_name, car_class, car_number,
        lap_num, lap_time,
        row_number() over (partition by session_id, vehicle_id order by lap_num desc) as rn
    from opponent_laps
    where lap_time is not null and lap_time > 0 and not in_pits
)
select
    session_id,
    vehicle_id,
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

-- ------------------------------------------------------------
-- View: Wetter, auf 5-Minuten-Raster verdichtet.
-- Ein 24h-Verlauf braucht keine 1440 Punkte im Diagramm.
-- ------------------------------------------------------------
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

-- ------------------------------------------------------------


-- ############ Zugriffsrechte (ersetzt 03_rls.sql) ############
--
-- anon: nur lesen.  service_role: umgeht RLS ohnehin und darf alles.

do $$
declare t text;
begin
  foreach t in array array['drivers','sessions','laps','stint_telemetry','stints',
                           'events','field_state','opponent_laps','weather_log']
  loop
    execute format('alter table %I enable row level security', t);

    -- alte Schreibrechte aus der ersten Fassung entfernen, falls vorhanden
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

-- Kontrolle: sollte fuer jede Tabelle genau eine Policy "…_read" zeigen
select tablename, policyname, cmd, roles
from pg_policies
where schemaname = 'public'
order by tablename;
