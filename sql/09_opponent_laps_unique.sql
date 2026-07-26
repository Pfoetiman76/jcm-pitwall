-- 09_opponent_laps_unique.sql
-- Sichert den UNIQUE-Constraint auf opponent_laps(session_id, vehicle_id, lap_num).
-- Der Upsert (on_conflict) braucht ihn zwingend. Schema-rueckstaendige DBs (aus
-- fruehem Setup, "No migrations") haben ihn evtl. nicht -> der Upsert scheitert
-- dann mit HTTP 400 "no unique or exclusion constraint matching the ON CONFLICT".
-- Idempotent (drop if exists + add). Wenn das aktuelle Schema schon einen
-- passenden Constraint hat, ist der hier zusaetzliche redundant, aber harmlos -
-- PostgREST matcht on_conflict ueber die Spalten, nicht den Namen.

-- Erst evtl. vorhandene Duplikate entfernen, sonst laesst sich der
-- Constraint nicht anlegen. Behaelt jeweils die aelteste Zeile (kleinste id).
delete from opponent_laps a
 using opponent_laps b
 where a.id < b.id
   and a.session_id = b.session_id
   and a.vehicle_id = b.vehicle_id
   and a.lap_num    = b.lap_num;

alter table opponent_laps drop constraint if exists opponent_laps_uniq;
alter table opponent_laps add  constraint opponent_laps_uniq
      unique (session_id, vehicle_id, lap_num);

-- PostgREST-Schema-Cache neu laden, sonst greift der Constraint fuer die API
-- evtl. erst verzoegert (400 trotz "Success").
notify pgrst, 'reload schema';
