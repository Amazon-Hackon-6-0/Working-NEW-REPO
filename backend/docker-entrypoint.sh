#!/bin/sh
set -eu

mkdir -p /app/app/data

if [ ! -f /app/app/data/office_directory.example.json ] && [ -f /app/seed-data/office_directory.example.json ]; then
  cp /app/seed-data/office_directory.example.json /app/app/data/office_directory.example.json
fi

if [ ! -f /app/app/data/office_directory.json ] && [ -f /app/seed-data/office_directory.json ]; then
  cp /app/seed-data/office_directory.json /app/app/data/office_directory.json
fi

exec "$@"
