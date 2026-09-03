#!/bin/sh
set -eu

mkdir -p /app/data
chown -R spring:spring /app/data

exec runuser -u spring -- "$@"
