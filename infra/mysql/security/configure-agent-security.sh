#!/bin/bash
set -e

query_password="${AGENT_MYSQL_PASSWORD:?AGENT_MYSQL_PASSWORD is required}"
audit_password="${AGENT_AUDIT_MYSQL_PASSWORD:?AGENT_AUDIT_MYSQL_PASSWORD is required}"
import_password="${IMPORT_MYSQL_PASSWORD:?IMPORT_MYSQL_PASSWORD is required}"
escaped_query_password="$(printf '%s' "$query_password" | sed -e 's/\\/\\\\/g' -e "s/'/''/g")"
escaped_audit_password="$(printf '%s' "$audit_password" | sed -e 's/\\/\\\\/g' -e "s/'/''/g")"
escaped_import_password="$(printf '%s' "$import_password" | sed -e 's/\\/\\\\/g' -e "s/'/''/g")"

export MYSQL_PWD="${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"

# Java/Flyway creates the versioned tables and views. Do not depend on Java's
# healthcheck here: that healthcheck also probes the import account, which this
# script is responsible for creating.
for attempt in $(seq 1 60); do
  ready="$(mysql --protocol=tcp -h mysql -u root -Nse \
    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema='house_price' AND table_name IN ('house_dataset','v_agent_house_listing','agent_query_audit')" 2>/dev/null || true)"
  if [ "$ready" = "3" ]; then
    break
  fi
  if [ "$attempt" = "60" ]; then
    echo "Timed out waiting for Flyway-managed Agent/import tables" >&2
    exit 1
  fi
  sleep 2
done

mysql --protocol=tcp -h mysql -u root <<EOSQL
DROP USER IF EXISTS 'house_agent'@'%';

CREATE USER IF NOT EXISTS 'house_agent_ro'@'%' IDENTIFIED BY '${escaped_query_password}';
ALTER USER 'house_agent_ro'@'%' IDENTIFIED BY '${escaped_query_password}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'house_agent_ro'@'%';
GRANT SELECT ON house_price.v_agent_house_listing TO 'house_agent_ro'@'%';
GRANT SELECT ON house_price.v_agent_district_summary TO 'house_agent_ro'@'%';
GRANT SELECT ON house_price.v_agent_monthly_price_trend TO 'house_agent_ro'@'%';

CREATE USER IF NOT EXISTS 'house_agent_audit'@'%' IDENTIFIED BY '${escaped_audit_password}';
ALTER USER 'house_agent_audit'@'%' IDENTIFIED BY '${escaped_audit_password}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'house_agent_audit'@'%';
GRANT INSERT ON house_price.agent_query_audit TO 'house_agent_audit'@'%';

CREATE USER IF NOT EXISTS 'house_import_writer'@'%' IDENTIFIED BY '${escaped_import_password}';
ALTER USER 'house_import_writer'@'%' IDENTIFIED BY '${escaped_import_password}';
REVOKE ALL PRIVILEGES, GRANT OPTION FROM 'house_import_writer'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON house_price.house_info TO 'house_import_writer'@'%';
GRANT SELECT, INSERT, UPDATE, DELETE ON house_price.rental_listing TO 'house_import_writer'@'%';
GRANT SELECT, INSERT, UPDATE ON house_price.house_dataset TO 'house_import_writer'@'%';
GRANT SELECT, UPDATE ON house_price.house_dataset_state TO 'house_import_writer'@'%';

FLUSH PRIVILEGES;
EOSQL

echo "Agent and import database permissions configured."
