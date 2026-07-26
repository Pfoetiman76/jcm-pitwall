-- ============================================================
-- JCM Pitwall - 02 Feld / Gegner / Wetter
-- Nach 01 ausfuehren.
-- ============================================================

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
