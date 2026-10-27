-- ============================================================
-- 006: pasar la llamada a una persona y uso por llamada
-- Ejecutar en Supabase -> SQL Editor (una sola vez).
-- ============================================================

-- Numero del encargado al que el agente pasa la llamada cuando el cliente
-- pide hablar con alguien, tiene una queja o algo que no puede resolver.
-- Null = el restaurante no acepta transferencias.
alter table restaurantes add column if not exists telefono_transferencia text;

-- Uso de cada llamada (minutos, tokens, caracteres de voz) y su costo
-- estimado en USD. Es informacion interna de Sianka: el panel del
-- restaurante no la muestra.
alter table llamadas add column if not exists uso jsonb;
alter table llamadas add column if not exists costo_estimado_usd numeric(10,4);

-- Nuevo resultado posible: la llamada se paso a una persona.
alter table llamadas drop constraint if exists llamadas_resultado_check;
alter table llamadas add constraint llamadas_resultado_check
    check (resultado in ('orden', 'sin_orden', 'transferida'));
