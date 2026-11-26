-- =====================================================================
--  CENTINELA · Migración 005: uso de la IA híbrida (Ollama / Vertex AI Gemini)
--  Correr como centinela_app:  bash nube/10_migracion.sh db/005_ia_uso.sql
--  Cada nodo agrega en memoria y vuelca en cada latido. Sin textos de usuarios: solo conteos.
-- =====================================================================
create table if not exists ia_uso_hora (
    hora            timestamptz not null,
    nodo            text not null,
    proveedor       text not null,     -- ollama | vertex
    tipo            text not null,     -- chat | clasificar | profundo_campanas | profundo_semanal
    resultado       text not null,     -- ok | error | cache | sin_cupo | apagado
    llamadas        int  not null default 0,
    tokens_entrada  bigint not null default 0,
    tokens_salida   bigint not null default 0,
    primary key (hora, nodo, proveedor, tipo, resultado)
);

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'centinela_jp') then
    grant select, insert, update, delete on ia_uso_hora to centinela_jp;
  end if;
end $$;
