-- ============================================================
-- Migracion 005: numero de orden diario (001-999) por restaurante
-- Correr UNA vez en Supabase (SQL Editor) despues de la 004. Las
-- instalaciones nuevas no la necesitan: schema.sql ya incluye todo esto.
--
-- El numero lo asigna la BASE DE DATOS en un trigger, no la app: si dos
-- llamadas registran una orden al mismo tiempo, el INSERT ... ON CONFLICT
-- DO UPDATE sobre el contador bloquea esa fila y cada orden recibe un
-- numero distinto. Un contador en Python podria repetir numeros.
-- ============================================================

alter table ordenes add column if not exists numero_dia integer;
alter table ordenes add column if not exists fecha_operacion date;
create index if not exists idx_ordenes_numero_dia on ordenes(restaurante_id, fecha_operacion, numero_dia);

-- Ultimo numero usado por restaurante y dia
create table if not exists contadores_ordenes (
    restaurante_id uuid not null references restaurantes(id),
    fecha date not null,
    ultimo integer not null,
    primary key (restaurante_id, fecha)
);
alter table contadores_ordenes enable row level security;

create or replace function asignar_numero_orden()
returns trigger as $$
declare
    -- El "dia" es el de Mexico, no el de UTC: si no, el contador se
    -- reiniciaria a las 18:00 hora del centro. Misma zona que los reportes.
    dia date := (now() at time zone 'America/Mexico_City')::date;
    siguiente integer;
begin
    insert into contadores_ordenes (restaurante_id, fecha, ultimo)
    values (new.restaurante_id, dia, 1)
    on conflict (restaurante_id, fecha)
    do update set ultimo = contadores_ordenes.ultimo + 1
    returning ultimo into siguiente;

    new.fecha_operacion := dia;
    -- 001..999; si un restaurante pasa de 999 en un dia, vuelve a 001.
    new.numero_dia := ((siguiente - 1) % 999) + 1;
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_ordenes_numero_dia on ordenes;
create trigger trg_ordenes_numero_dia
    before insert on ordenes
    for each row
    execute function asignar_numero_orden();

-- ------------------------------------------------------------
-- Verificacion (opcional). Pega esto aparte en el SQL Editor; no deja
-- datos porque termina en ROLLBACK:
--
--   begin;
--   insert into ordenes (restaurante_id, items, total)
--   select id, '[]'::jsonb, 0 from restaurantes where slug = 'tacos-el-guero';
--   insert into ordenes (restaurante_id, items, total)
--   select id, '[]'::jsonb, 0 from restaurantes where slug = 'tacos-el-guero';
--   select numero_dia, fecha_operacion from ordenes
--   where restaurante_id = (select id from restaurantes where slug = 'tacos-el-guero')
--   order by created_at desc limit 2;      -- dos numeros consecutivos, fecha de hoy
--   rollback;
-- ------------------------------------------------------------
