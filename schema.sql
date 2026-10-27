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
    -- Datos del restaurante como "responsable" en su aviso de privacidad
    -- (se publican en /privacidad/<slug>)
    razon_social text,
    domicilio text,
    email_privacidad text,
    -- Aviso de privacidad: decirlo en el saludo (opcional) y URL en el
    -- sitio propio del restaurante, si tiene
    aviso_en_llamada boolean default false,
    url_aviso_privacidad text,
    -- Entregas a domicilio
    ofrece_entregas boolean default false,
    costo_envio decimal(10,2) default 0,
    pedido_minimo_envio decimal(10,2) default 0,
    tiempo_entrega_min integer default 45,
    zona_entrega text,
    -- Numero del encargado al que el agente pasa la llamada (null = no se transfiere)
    telefono_transferencia text,
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
    -- telefono_cliente, nombre_cliente y transcripcion se guardan CIFRADOS
    -- por la app (services/cifrado_service.py). telefono_hash es una huella
    -- HMAC del numero para encontrar sus llamadas (derechos ARCO).
    telefono_cliente text,
    telefono_hash text,
    nombre_cliente text,
    duracion_segundos integer,
    transcripcion text,
    resultado text check (resultado in ('orden', 'sin_orden', 'transferida')),
    -- Uso (minutos, tokens, caracteres de voz) y costo estimado en USD.
    -- Interno de Sianka: el panel del restaurante no lo muestra.
    uso jsonb,
    costo_estimado_usd numeric(10,4),
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
    nombre_cliente text,  -- cifrado por la app
    tipo_entrega text default 'recoger' check (tipo_entrega in ('recoger', 'domicilio')),
    -- Solo a domicilio. direccion, referencias y telefono: cifrados por la app
    direccion_entrega text,
    referencias_entrega text,
    telefono_contacto text,
    metodo_pago text check (metodo_pago is null or metodo_pago in ('efectivo', 'tarjeta')),
    paga_con decimal(10,2),
    costo_envio decimal(10,2) default 0,  -- ya incluido en total
    -- Numero para el mostrador (001-999), se reinicia cada dia. Lo asigna
    -- el trigger trg_ordenes_numero_dia, no la app.
    numero_dia integer,
    fecha_operacion date,
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
create index if not exists idx_llamadas_telefono_hash on llamadas(restaurante_id, telefono_hash);

-- Row Level Security en todas las tablas, sin politicas: el backend usa la
-- service_role key (que salta RLS) y la anon key -- publica por diseno en
-- Supabase -- no puede leer ni escribir nada.
alter table restaurantes enable row level security;
alter table menus enable row level security;
alter table llamadas enable row level security;
alter table ordenes enable row level security;

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

create index if not exists idx_ordenes_numero_dia on ordenes(restaurante_id, fecha_operacion, numero_dia);

-- ------------------------------------------------------------
-- Numero de orden diario (001-999) por restaurante. Lo asigna la base en
-- un trigger para que dos llamadas simultaneas nunca repitan numero.
-- ------------------------------------------------------------
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
