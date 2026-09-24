-- ============================================================
-- Migracion 004: entregas a domicilio y aviso de privacidad opcional
-- Correr UNA vez en Supabase (SQL Editor) despues de la 003. Las
-- instalaciones nuevas no la necesitan: schema.sql ya incluye todo esto.
-- ============================================================

-- Configuracion de entregas por restaurante (se edita en /configuracion)
alter table restaurantes add column if not exists ofrece_entregas boolean default false;
alter table restaurantes add column if not exists costo_envio decimal(10,2) default 0;
alter table restaurantes add column if not exists pedido_minimo_envio decimal(10,2) default 0;
alter table restaurantes add column if not exists tiempo_entrega_min integer default 45;
alter table restaurantes add column if not exists zona_entrega text;

-- Aviso de privacidad: si se dice en el saludo (desactivado por defecto) y
-- la URL del aviso en el sitio propio del restaurante, si tiene.
alter table restaurantes add column if not exists aviso_en_llamada boolean default false;
alter table restaurantes add column if not exists url_aviso_privacidad text;

-- Datos de entrega de cada orden. direccion_entrega, referencias_entrega y
-- telefono_contacto se guardan CIFRADOS por la app.
alter table ordenes add column if not exists tipo_entrega text default 'recoger';
alter table ordenes add column if not exists direccion_entrega text;
alter table ordenes add column if not exists referencias_entrega text;
alter table ordenes add column if not exists telefono_contacto text;
alter table ordenes add column if not exists metodo_pago text;
alter table ordenes add column if not exists paga_con decimal(10,2);
alter table ordenes add column if not exists costo_envio decimal(10,2) default 0;

alter table ordenes drop constraint if exists ordenes_tipo_entrega_check;
alter table ordenes add constraint ordenes_tipo_entrega_check
    check (tipo_entrega in ('recoger', 'domicilio'));
alter table ordenes drop constraint if exists ordenes_metodo_pago_check;
alter table ordenes add constraint ordenes_metodo_pago_check
    check (metodo_pago is null or metodo_pago in ('efectivo', 'tarjeta'));
