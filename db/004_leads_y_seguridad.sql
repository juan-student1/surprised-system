-- =====================================================================
--  CENTINELA · Migración 004: leads de ventas (JM) y métricas de seguridad (JP)
--  Correr UNA vez como centinela_app (dueño de las tablas), después de 003.
--  Cloud SQL → centinela-db → Cloud SQL Studio → base "centinela", usuario centinela_app → pegar y Run.
--  Se puede correr varias veces (if not exists).
-- =====================================================================

-- Formulario "Para empresas" de la web. Datos personales (Ley 1581 de 2012):
-- solo con autorización explícita, nunca se muestran al público y se borran a pedido.
create table if not exists leads (
    id            bigserial primary key,
    nombre        text not null,
    empresa       text,
    correo        text not null,
    telefono      text,
    segmento      text not null,        -- persona | call_center | cooperativa | banco | operador | otro
    plan          text not null,        -- gratis | pro | empresa
    mensaje       text,
    acepta_datos  boolean not null,     -- autorización de tratamiento de datos (habeas data)
    origen_hash   text,                 -- hash de la IP (anti-spam), nunca la IP
    nodo          text,
    estado        text not null default 'nuevo',   -- nuevo | contactado | descartado
    creado        timestamptz not null default now()
);
create index if not exists idx_leads_creado on leads(creado desc);

-- Peticiones bloqueadas por hora (401/403/429) que cada nodo agrega en memoria
-- y vuelca en cada latido. Sin IPs: solo hora, nodo, código y grupo de ruta.
create table if not exists seguridad_hora (
    hora    timestamptz not null,
    nodo    text not null,
    codigo  int  not null,
    ruta    text not null,
    total   int  not null default 0,
    primary key (hora, nodo, codigo, ruta)
);

-- Privilegio mínimo para el nodo JP (igual que 003)
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'centinela_jp') then
    grant select, insert, update, delete on leads, seguridad_hora to centinela_jp;
    grant usage, select on sequence leads_id_seq to centinela_jp;
  end if;
end $$;
