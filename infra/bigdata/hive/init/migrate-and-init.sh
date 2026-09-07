#!/bin/bash
set -euo pipefail

jdbc_url='jdbc:hive2://hiveserver2:10000/default'
tables="$(beeline -u "$jdbc_url" -n hive --silent=true --showHeader=false --outputformat=tsv2 -e 'USE mydb; SHOW TABLES;' 2>/dev/null || true)"

for table in house_info_raw house_info_detail house_info_analysis house_data_quality_summary; do
  legacy="${table}_legacy_pre_dataset"
  if printf '%s\n' "$tables" | grep -qx "$table"; then
    schema="$(beeline -u "$jdbc_url" -n hive --silent=true --showHeader=false --outputformat=tsv2 \
      -e "USE mydb; DESCRIBE ${table};" 2>/dev/null || true)"
    if ! printf '%s\n' "$schema" | awk '{print $1}' | grep -qx 'dataset_id'; then
      if printf '%s\n' "$tables" | grep -qx "$legacy"; then
        echo "Cannot migrate ${table}: ${legacy} already exists" >&2
        exit 1
      fi
      beeline -u "$jdbc_url" -n hive -e "USE mydb; ALTER TABLE ${table} RENAME TO ${legacy};"
    fi
  fi
done

exec beeline -u "$jdbc_url" -n hive -f /hive-init/01_init_hive.sql
