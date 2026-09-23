-- ============================================================
-- Voice Agent MVP — Schema Supabase (PostgreSQL)
-- Restaurantes mexicanos: llamadas por voz -> ordenes en vivo
-- ============================================================

-- Extension necesaria para gen_random_uuid()
create extension if not exists "pgcrypto";

-- ------------------------------------------------------------
-- Tabla: restaurantes
-- ------------------------------------------------------------
create table if not exists restaurantes (
    id uuid primary key default gen_random_uuid(),
    -- Identificador legible y unico (p. ej. "tacos-el-guero"): es como se
    -- refiere uno al restaurante en admin.py y en los logs.
    slug text not null unique,
    nombre text not null,
    ciudad text,
    horario text,
    -- Numero de Twilio al que marcan los clientes; decide que restaurante
    -- contesta cada llamada.
    twilio_number text unique,
    -- Variables del agente de voz (si son null se usan los defaults del codigo)
    saludo text,
    tiempo_recoleccion_min integer default 20,
    instrucciones_extra text,
    voz_tts text,
    activo boolean default true,
    created_at timestamptz default now()
);

-- ------------------------------------------------------------
-- Tabla: usuarios (acceso al dashboard, uno o varios por restaurante)
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
alter table usuarios enable row level security;

-- ------------------------------------------------------------
-- Tabla: menus
-- ------------------------------------------------------------
create table if not exists menus (
    id uuid primary key default gen_random_uuid(),
    restaurante_id uuid references restaurantes(id),
    platillo text not null,
    precio decimal(10,2) not null,
    ingredientes text,
    activo boolean default true,
    disponible boolean default true
);

-- Si tu tabla `menus` ya existia antes de agregar `disponible` (CREATE TABLE
-- IF NOT EXISTS no la agrega retroactivamente), corre esto una vez:
-- alter table menus add column if not exists disponible boolean default true;

-- ------------------------------------------------------------
-- Tabla: llamadas
-- ------------------------------------------------------------
create table if not exists llamadas (
    id uuid primary key default gen_random_uuid(),
    restaurante_id uuid references restaurantes(id),
    telefono_cliente text,
    duracion_segundos integer,
    transcripcion text,
    resultado text check (resultado in ('orden', 'sin_orden')),
    created_at timestamptz default now()
);

-- ------------------------------------------------------------
-- Tabla: ordenes
-- ------------------------------------------------------------
create table if not exists ordenes (
    id uuid primary key default gen_random_uuid(),
    restaurante_id uuid references restaurantes(id),
    llamada_id uuid references llamadas(id),
    items jsonb not null,
    total decimal(10,2),
    tiempo_recoleccion text,
    status text default 'nueva'
        check (status in ('nueva', 'confirmada', 'preparando', 'lista', 'entregada')),
    created_at timestamptz default now(),
    updated_at timestamptz default now()
);

-- Indices utiles para el dashboard en tiempo real
create index if not exists idx_ordenes_restaurante on ordenes(restaurante_id);
create index if not exists idx_ordenes_status on ordenes(status);
create index if not exists idx_llamadas_restaurante on llamadas(restaurante_id);
create index if not exists idx_menus_restaurante on menus(restaurante_id);

-- ------------------------------------------------------------
-- Trigger: mantener updated_at al dia en ordenes
-- ------------------------------------------------------------
create or replace function set_updated_at()
returns trigger as $$
begin
    new.updated_at = now();
    return new;
end;
$$ language plpgsql;

drop trigger if exists trg_ordenes_updated_at on ordenes;
create trigger trg_ordenes_updated_at
    before update on ordenes
    for each row
    execute function set_updated_at();

-- ============================================================
-- Datos de prueba: Tacos El Güero, Mérida Yucatán
-- ============================================================

-- Para dar de alta mas restaurantes (y los usuarios del dashboard) usa
-- `python admin.py` en vez de SQL a mano.
insert into restaurantes (slug, nombre, ciudad, horario, twilio_number, activo)
values (
    'tacos-el-guero',
    'Tacos El Güero',
    'Mérida, Yucatán',
    'Lunes a domingo de 13:00 a 23:00',
    '+525550001234',
    true
);

-- Menú del restaurante (usa el id recien insertado)
insert into menus (restaurante_id, platillo, precio, ingredientes, activo)
select id, 'Cochinita pibil', 25.00, 'Cochinita, cebolla morada, chile habanero, tortilla de maíz', true
from restaurantes where nombre = 'Tacos El Güero';

insert into menus (restaurante_id, platillo, precio, ingredientes, activo)
select id, 'Bistec', 28.00, 'Bistec, cebolla, cilantro, tortilla de maíz', true
from restaurantes where nombre = 'Tacos El Güero';

insert into menus (restaurante_id, platillo, precio, ingredientes, activo)
select id, 'Pollo', 25.00, 'Pollo asado, lechuga, tomate, tortilla de maíz', true
from restaurantes where nombre = 'Tacos El Güero';

insert into menus (restaurante_id, platillo, precio, ingredientes, activo)
select id, 'Agua de jamaica', 20.00, 'Agua fresca de jamaica', true
from restaurantes where nombre = 'Tacos El Güero';

insert into menus (restaurante_id, platillo, precio, ingredientes, activo)
select id, 'Agua de horchata', 20.00, 'Agua fresca de horchata', true
from restaurantes where nombre = 'Tacos El Güero';

insert into menus (restaurante_id, platillo, precio, ingredientes, activo)
select id, 'Refresco', 18.00, 'Refresco de lata', true
from restaurantes where nombre = 'Tacos El Güero';
