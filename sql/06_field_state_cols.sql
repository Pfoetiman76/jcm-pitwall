-- ============================================================
-- Nachtrag fuer bestehende Datenbanken.
-- Der Client schickt an field_state drei Spalten, die im
-- urspruenglichen Schema fehlten. Ohne sie: HTTP 400 beim
-- field_state-Upsert -> Zeiten- und Strecken-Schirm bleiben leer,
-- Wetter-Vorhersage fehlt. (Eigene Runden/Telemetrie sind NICHT
-- betroffen, die laufen ueber eigene Tabellen.)
-- In Supabase: SQL Editor -> einfuegen -> Run.
-- ============================================================

alter table field_state add column if not exists track_length_m      numeric(10,3);
alter table field_state add column if not exists session_remaining_s numeric(12,3);
alter table field_state add column if not exists weather_forecast     jsonb;

-- PostgREST seinen Schema-Cache neu laden lassen (sonst greift es
-- ein paar Sekunden lang noch auf den alten Stand zu):
notify pgrst, 'reload schema';
