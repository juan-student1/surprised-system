-- =====================================================================
--  CENTINELA · Migración 003: ajustes para Cloud SQL (Google Cloud)
--  La corre nube/04_migrar_datos.sh como centinela_app (dueño de las tablas),
--  DESPUÉS de schema.sql y 002_llamadas.sql. Se puede correr varias veces.
-- =====================================================================

-- En Supabase el RLS bloqueaba su API REST pública (clave anon). En Cloud SQL esa API
-- no existe: el acceso lo controlan IAM (roles/cloudsql.client + conector obligatorio)
-- y los usuarios de la base. Con RLS activo y sin políticas, centinela_jp no vería nada.
alter table numeros  disable row level security;
alter table reportes disable row level security;
alter table nodos    disable row level security;
alter table eventos  disable row level security;
alter table llamadas disable row level security;

-- Nadie fuera del dueño puede crear objetos en el esquema
revoke create on schema public from public;

-- Privilegio mínimo para el nodo JP: leer y escribir datos, nunca cambiar el esquema
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'centinela_jp') then
    grant usage on schema public to centinela_jp;
    grant select, insert, update, delete on all tables in schema public to centinela_jp;
    grant usage, select on all sequences in schema public to centinela_jp;
  end if;
end $$;
