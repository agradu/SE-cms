#!/bin/bash
# to clean all migrations files in the project.
# find . -type f -name "0*.py" -exec rm -f {} \; -print
# find . -type f -name "0*.pyc" -exec rm -f {} \; -print
# echo "All migrations in apps are cleaned!"
echo ""

# Parameters for PostgreSQL connection
PGUSER="postgres"
PGHOST="localhost"
PGPORT="5432"

DATABASE_TO_DELETE="se_cms"
DATABASE_TO_CREATE="se_cms"

# Erase the database if it exists
echo "Erase the old database database"
sudo -i -u postgres dropdb --username="$PGUSER" --host="$PGHOST" --port="$PGPORT" "$DATABASE_TO_DELETE"
# Create the new database
echo "Create the new database"
sudo -i -u postgres createdb --username="$PGUSER" --host="$PGHOST" --port="$PGPORT" "$DATABASE_TO_CREATE"
# Verify if the operation is successful
if [ $? -ne 0 ]; then
    echo "Failed to reset the database!"
    exit 1  # Stop the script with error code 1
fi

# Import the data back into the new database
echo "Import the data back into the new database"
psql --username="$PGUSER" --host="$PGHOST" --port="$PGPORT" --dbname="$DATABASE_TO_CREATE" --password < backup.sql

echo "The database '$DATABASE_TO_CREATE' was recreated with the data from backup!"

# ...

# Cleanup: remove the backup file
rm backup.sql

# ...
