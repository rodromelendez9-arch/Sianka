-- ============================================================
-- Migracion 003: nombre del cliente, datos legales y proteccion de datos
-- Correr UNA vez en Supabase (SQL Editor) despues de la 002. Las
-- instalaciones nuevas no la necesitan: schema.sql ya incluye todo esto.
--
-- Despues de correrla, cifra las filas que ya existian con:
--   python admin.py cifrar-existentes
-- ============================================================

-- Nombre con el que el cliente pide su orden (se guarda CIFRADO por la app).
alter table ordenes add column if not exists nombre_cliente text;
alter table llamadas add column if not exists nombre_cliente text;

-- Huella (HMAC) del telefono: permite encontrar las llamadas de un numero
-- para atender derechos ARCO sin guardar el numero en claro.
alter table llamadas add column if not exists telefono_hash text;
create index if not exists idx_llamadas_telefono_hash on llamadas(restaurante_id, telefono_hash);

-- Datos del restaurante como "responsable" en su aviso de privacidad.
alter table restaurantes add column if not exists razon_social text;
alter table restaurantes add column if not exists domicilio text;
alter table restaurantes add column if not exists email_privacidad text;

-- Row Level Security en TODAS las tablas, sin politicas: el backend usa la
-- service_role key (que salta RLS), y cualquiera con la anon key -- que es
-- publica por diseno en Supabase -- no puede leer ni escribir nada.
alter table restaurantes enable row level security;
alter table menus enable row level security;
alter table llamadas enable row level security;
alter table ordenes enable row level security;
alter table usuarios enable row level security;
