#!/bin/bash
# to clean all migrations files in the project.
find . -type f -name "0*.py" -exec rm -f {} \; -print
find . -type f -name "0*.pyc" -exec rm -f {} \; -print
echo "All migrations in apps are cleaned!"

# Parameters for PostgreSQL connection
PGUSER="postgres"
PGHOST="localhost"
PGPORT="5432"
# Reading the password from user
echo -n "Enter the PostgreSQL password."
echo -n ""

DATABASE_TO_DELETE="se_cms"
DATABASE_TO_CREATE="se_cms"
# Erase the database if it exist
sudo -i -u postgres dropdb --username="$PGUSER" --host="$PGHOST" --port="$PGPORT" "$DATABASE_TO_DELETE"
# Create the new data base
sudo -i -u postgres createdb --username="$PGUSER" --host="$PGHOST" --port="$PGPORT" "$DATABASE_TO_CREATE"
# Verify if the operation is succeed
if [ $? -ne 0 ]; then
    echo "Faild to reset the database!"
    exit 1  # Stop the script with eror code 1
fi

echo "The database '$DATABASE_TO_CREATE' was recreated!"

# make migrations & migrate
python manage.py makemigrations
python manage.py migrate

# Create a superuser in django
echo -n "Enter the username of the superuser: "
read DJANGO_USER
echo -n "Enter the email for superuser: "
read DJANGO_EMAIL

python manage.py createsuperuser --username="$DJANGO_USER" --email="$DJANGO_EMAIL"
python manage.py runscript data_load
