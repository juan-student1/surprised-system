#!/usr/bin/env bash
# Corre DENTRO del contenedor postgres:17 (lo llama 04_migrar_datos.sh). Variables: S, D, CLAVE_JP.
set -euo pipefail
echo "▶ Esquema en Cloud SQL"
psql -q -v ON_ERROR_STOP=1 "$D" -f /db/schema.sql -f /db/002_llamadas.sql 2>&1 | grep -v NOTICE || true

echo "▶ Usuario centinela_jp (creado por SQL: no es cloudsqlsuperuser, solo lee y escribe datos)"
psql -q -v ON_ERROR_STOP=1 -v clave="$CLAVE_JP" "$D" <<'SQL'
select set_config('centinela.clave_jp', :'clave', false) \g /dev/null
do $$ begin
  if exists (select 1 from pg_roles where rolname = 'centinela_jp') then
    execute format('alter role centinela_jp login password %L', current_setting('centinela.clave_jp'));
  else
    execute format('create role centinela_jp login password %L', current_setting('centinela.clave_jp'));
  end if;
end $$;
SQL
psql -q -v ON_ERROR_STOP=1 "$D" -f /db/003_cloudsql.sql

echo "▶ Vaciando destino y copiando datos desde Supabase"
psql -q -v ON_ERROR_STOP=1 "$D" -c "truncate numeros, reportes, nodos, eventos, llamadas restart identity cascade"
pg_dump "$S" --data-only --no-owner --no-privileges --schema=public \
   -t public.numeros -t public.reportes -t public.nodos -t public.eventos -t public.llamadas > /tmp/datos.sql
psql -q -v ON_ERROR_STOP=1 "$D" -f /tmp/datos.sql >/dev/null
rm -f /tmp/datos.sql

echo "▶ Comprobación (deben coincidir)"
for t in numeros reportes nodos eventos llamadas; do
  printf "  %-9s Supabase=%-6s CloudSQL=%s\n" "$t" \
    "$(psql -tAq "$S" -c "select count(*) from $t")" "$(psql -tAq "$D" -c "select count(*) from $t")"
done
