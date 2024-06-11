Get-ChildItem -Recurse -Filter "0*.py" | Remove-Item -Force
Get-ChildItem -Recurse -Filter "0*.pyc" | Remove-Item -Force
Write-Host "All migrations in apps are cleaned!"


# Parameters for PostgreSQL connection
$PGUSER="postgres"
$PGHOST="localhost"
$PGPORT="5432"
$DATABASE="se_cms"

# Ștergerea bazei de date
Write-Host "Erase the old database"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -c "DROP DATABASE IF EXISTS $DATABASE;" -U $PGUSER -h $PGHOST -p $PGPORT

# Crearea bazei de date
Write-Host "Create the new database"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -c "CREATE DATABASE $DATABASE;" -U $PGUSER -h $PGHOST -p $PGPORT


# Import the data back into the new database
Write-Host "Import the data back into the new database"
& "C:\Program Files\PostgreSQL\16\bin\psql.exe" -U $PGUSER -h $PGHOST -p $PGPORT -d $DATABASE -f "backup.sql"

