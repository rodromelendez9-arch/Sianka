-- ============================================================
-- Migracion 002: soporte para N restaurantes
-- Correr UNA vez en Supabase (SQL Editor) sobre una base que ya tenia el
-- schema original. Las instalaciones nuevas no la necesitan: schema.sql ya
-- incluye todo esto.
-- ============================================================

-- Identificador legible de cada restaurante (p. ej. "tacos-el-guero") y las
-- variables que antes estaban fijas en el codigo.
alter table restaurantes add column if not exists slug text;
alter table restaurantes add column if not exists saludo text;
alter table restaurantes add column if not exists tiempo_recoleccion_min integer default 20;
alter table restaurantes add column if not exists instrucciones_extra text;
alter table restaurantes add column if not exists voz_tts text;

update restaurantes set slug = 'tacos-el-guero'
where slug is null and nombre = 'Tacos El Güero';

update restaurantes set slug = 'restaurante-' || left(id::text, 8)
where slug is null;

alter table restaurantes alter column slug set not null;
create unique index if not exists idx_restaurantes_slug on restaurantes(slug);

-- Cada numero de Twilio pertenece a un solo restaurante: es lo que decide
-- que restaurante contesta una llamada.
create unique index if not exists idx_restaurantes_twilio_number
    on restaurantes(twilio_number) where twilio_number is not null;

-- ------------------------------------------------------------
-- Usuarios del dashboard: cada uno pertenece a UN restaurante y solo ve
-- los datos de ese restaurante. Reemplaza a DASHBOARD_PASSWORD.
-- ------------------------------------------------------------
create table if not exists usuarios (
    id uuid primary key default gen_random_uuid(),
    restaurante_id uuid not null references restaurantes(id),
    email text not null,
    password_hash text not null,
    nombre text,
    activo boolean default true,
    created_at timestamptz default now()
);

create unique index if not exists idx_usuarios_email on usuarios(lower(email));
create index if not exists idx_usuarios_restaurante on usuarios(restaurante_id);

-- Los datos del backend se escriben con la service_role key; con RLS
-- activado y sin politicas, nadie con la anon key puede leer los hashes.
alter table usuarios enable row level security;
