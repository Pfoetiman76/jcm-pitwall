-- ============================================================
-- JCM Pitwall - Nachtrag: gemessener Boxenverlust
--
-- Der Client misst den Boxenverlust aus In-/Out-Laps, konnte ihn aber
-- nirgends ablegen. Diese Spalte hat gefehlt.
-- Im SQL-Editor ausfuehren, dauert eine Sekunde.
-- ============================================================

alter table field_state
  add column if not exists pit_loss_s numeric(7,2);

comment on column field_state.pit_loss_s is
  'Median des aus In-/Out-Laps geschaetzten Boxenverlusts in Sekunden';

-- Nachtrag 2: Werte, die LMU direkt liefert und die wir bisher geschaetzt haben.
-- track_length_m  ersetzt die Schaetzung der Streckenlaenge im Dashboard
-- session_remaining_s ist die echte Restzeit aus dem Spiel statt Wanduhr-Rechnerei
alter table field_state
  add column if not exists track_length_m      numeric(10,2),
  add column if not exists session_remaining_s numeric(12,2);
