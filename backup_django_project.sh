#!/bin/bash

# Parameters for PostgreSQL connection
PGUSER="postgres"
PGHOST="localhost"
PGPORT="5432"

DATABASE_TO_DELETE="se_cms"
DATABASE_TO_CREATE="se_cms"
# Backup the existing database
echo "Backup the existing database"
pg_dump --username="$PGUSER" --host="$PGHOST" --port="$PGPORT" --dbname="$DATABASE_TO_DELETE" --password > backup.sql

# ...
