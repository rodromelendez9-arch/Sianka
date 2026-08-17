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
    nombre text not null,
    ciudad text,
    horario text,
    twilio_number text,
    activo boolean default true,
    created_at timestamptz default now()
);

-- ------------------------------------------------------------
-- Tabla: menus
-- ------------------------------------------------------------
create table if not exists menus (
    id uuid primary key default gen_random_uuid(),
    restaurante_id uuid references restaurantes(id),
    platillo text not null,
    precio decimal(10,2) not null,
    ingredientes text,
    activo boolean default true
);

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

insert into restaurantes (nombre, ciudad, horario, twilio_number, activo)
values (
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
