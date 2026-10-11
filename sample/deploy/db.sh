#!/usr/bin/env bash

# Wait for PostgreSQL database to start
until pg_isready -h "$BS_DATABASES__DEFAULT__HOST" -p "$BS_DATABASES__DEFAULT__PORT"; do
  echo "Waiting for postgres..."
  sleep 2
done
echo "Postgres is running, continuing"

# Set database password
export PGPASSWORD="$BS_DATABASES__DEFAULT__PASSWORD"

# Function to execute SQL commands
db_sql(){
    if echo "$1" | psql -h "$BS_DATABASES__DEFAULT__HOST" -p "$BS_DATABASES__DEFAULT__PORT" -U "$BS_DATABASES__DEFAULT__USER" -d postgres; then
      echo "Success: $1"
    else
      echo "Error: $1"
      exit 1
    fi
}

# Check if database exists
db_exists(){
  echo "SELECT 1 FROM pg_database WHERE datname='$1'" | psql -tA -h "$BS_DATABASES__DEFAULT__HOST" -p "$BS_DATABASES__DEFAULT__PORT" -U "$BS_DATABASES__DEFAULT__USER" -d postgres
}

# Create database if it doesn't exist
db_create() {
  if [[ "$(db_exists "$1")" == '1' ]]; then
    echo "Database already exists: $1"
  else
    db_sql "CREATE DATABASE \"$1\""
  fi
}

echo "Creating databases..."
db_create "$BS_DATABASES__DEFAULT__NAME"

echo "Configuring user $BS_DATABASES__DEFAULT__USER..."
db_sql "ALTER ROLE \"$BS_DATABASES__DEFAULT__USER\" SET client_encoding TO 'utf8'"
db_sql "ALTER ROLE \"$BS_DATABASES__DEFAULT__USER\" SET default_transaction_isolation TO 'read committed'"
db_sql "ALTER ROLE \"$BS_DATABASES__DEFAULT__USER\" SET timezone TO 'UTC'"

echo "Checking project"
if python manage.py constance list; then
 echo "Success: Project check"
else
 echo "Error: Project check"
 exit 1

fi

# `migrate` installs the missing and changed triggers of pgtrigger once the migrations are
# applied (bazis 2.16). Before a migration that removes or renames a column a trigger reads,
# uninstall that trigger by its URI, e.g. `python manage.py pgtrigger uninstall
# app_label.Model:name`. Never `pgtrigger uninstall` or `pgtrigger install` without a URI: it
# also removes the triggers of pgtrigger of the other projects that share the database.
echo "Running migrations"
if python manage.py migrate; then
  echo "Success: migrations"
else
  echo "Error: migrations"
  exit 1
fi
