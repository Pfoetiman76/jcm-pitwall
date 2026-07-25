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
-- RLS fuer die neuen Tabellen (gleiche Linie wie 03_rls.sql)
-- ------------------------------------------------------------
alter table field_state   enable row level security;
alter table opponent_laps enable row level security;
alter table weather_log   enable row level security;

do $$
declare t text;
begin
  foreach t in array array['field_state','opponent_laps','weather_log']
  loop
    execute format('drop policy if exists %I on %I', t || '_read', t);
    execute format('create policy %I on %I for select using (true)', t || '_read', t);
    execute format('drop policy if exists %I on %I', t || '_insert', t);
    execute format('create policy %I on %I for insert with check (true)', t || '_insert', t);
  end loop;
end $$;

-- field_state wird ueberschrieben, braucht also Update
drop policy if exists field_state_update on field_state;
create policy field_state_update on field_state for update using (true) with check (true);
