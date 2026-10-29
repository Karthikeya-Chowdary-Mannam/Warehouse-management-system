# Warehouse Desk

Local Flask and PostgreSQL coursework application for managing warehouse records. It has no login page and is intended to run on your own computer at `http://127.0.0.1:5000`.

## What it includes

- Dashboard counts for the warehouse operation.
- Create, search, filter, edit, and delete screens for managers, warehouses, employees, suppliers, customers, products, inventory, orders, deliveries, payments, returns, and stock transfers.
- PostgreSQL primary keys, foreign keys, `NOT NULL` constraints, and validation rules.
- Exactly 10 digits for phone fields. Email addresses, phone numbers within each entity table, and the sales-order ID on a delivery cannot be duplicated. Primary keys are unique by definition.
- Password fields are stored as hashes. The app does not use them for login.
- Triggers update order totals and inventory when purchase orders, delivered sales orders, returns, and stock transfers are recorded.

## Fresh local setup on Linux

Run commands from this project folder in the VS Code terminal.

### 1. Create a PostgreSQL login and a new empty database

Open a local PostgreSQL administrator session:

```bash
sudo -u postgres psql
```

At the `postgres=#` prompt, replace `CHOOSE_A_PASSWORD` with a password you choose (use letters and numbers to make the URL easy to enter), then run:

```sql
CREATE ROLE warehouse_app WITH LOGIN PASSWORD 'CHOOSE_A_PASSWORD';
CREATE DATABASE warehouse_db OWNER warehouse_app;
\q
```

If you already created the role or database, choose a different name or use the existing one. This creates an empty database; it does not delete or change your old database.

### 2. Set the connection details

Copy the example settings and open the new `.env` file:

```bash
cp .env.example .env
nano .env
```

Set `DATABASE_URL` to the password you chose in Step 1. Do not include the quote marks. Save in nano with **Ctrl+O**, Enter, then **Ctrl+X**. `.env` is ignored by Git so the password should not be uploaded to GitHub.

### 3. Install and initialize

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
psql -h localhost -U warehouse_app -d warehouse_db -f schema.sql
```

Enter the database password when `psql` asks. The SQL creates the tables and database rules in the new database.

### 4. Run the website locally

```bash
flask --app app run --debug
```

Open `http://127.0.0.1:5000` in your browser. Keep the terminal running while you use the site. Stop Flask with **Ctrl+C**.

## Data entry notes

- IDs are generated automatically by PostgreSQL and remain unique. PostgreSQL does not reuse an ID just because a record was deleted, so gaps in ID numbers are normal.
- Fields marked required cannot be submitted blank. Date, status, and quantity fields with database defaults are filled automatically when omitted.
- PostgreSQL enforces the rules as well as the form, so invalid or duplicate values cannot be inserted by bypassing the website.
- The local app binds to `127.0.0.1`; it is only available on this computer.

## If PostgreSQL says a role already exists

Use a different role name in the `CREATE ROLE` command and put that same name in `.env` and the `psql -U` option. If `sudo -u postgres psql` fails, use the pgAdmin Query Tool connected as a database administrator to run the two SQL statements (run `CREATE DATABASE` separately if the Query Tool rejects it in a transaction).
