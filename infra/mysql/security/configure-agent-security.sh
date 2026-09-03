#!/bin/bash
set -e

query_password="${AGENT_MYSQL_PASSWORD:?AGENT_MYSQL_PASSWORD is required}"
audit_password="${AGENT_AUDIT_MYSQL_PASSWORD:?AGENT_AUDIT_MYSQL_PASSWORD is required}"
escaped_query_password="$(printf '%s' "$query_password" | sed -e 's/\\/\\\\/g' -e "s/'/''/g")"
escaped_audit_password="$(printf '%s' "$audit_password" | sed -e 's/\\/\\\\/g' -e "s/'/''/g")"

export MYSQL_PWD="${MYSQL_ROOT_PASSWORD:?MYSQL_ROOT_PASSWORD is required}"

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

FLUSH PRIVILEGES;
EOSQL

echo "Agent database permissions configured."
