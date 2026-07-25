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
