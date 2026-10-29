"""Flask interface for the Warehouse Management System PostgreSQL schema."""

import base64
import json
import os
from datetime import date, datetime
from decimal import Decimal

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import (
    MetaData,
    Table,
    and_,
    create_engine,
    func,
    or_,
    select,
)
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from werkzeug.security import generate_password_hash

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    # DATABASE_URL can still be supplied directly in the shell.
    pass


app = Flask(__name__)
app.secret_key = os.environ.get(
    "FLASK_SECRET_KEY",
    "local-development-key-change-me",
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg:///warehouse_db",
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
metadata = MetaData()

TABLES = [
    "manager",
    "warehouse",
    "employee",
    "users",
    "supplier",
    "customer",
    "product_category",
    "product",
    "inventory",
    "purchase_order",
    "purchase_order_item",
    "sales_order",
    "sales_order_item",
    "delivery",
    "payment",
    "return",
    "stock_transfer",
]

GROUPS = {
    "People & Places": [
        "manager",
        "warehouse",
        "employee",
        "users",
        "supplier",
        "customer",
    ],
    "Catalog & Stock": [
        "product_category",
        "product",
        "inventory",
    ],
    "Purchasing": [
        "purchase_order",
        "purchase_order_item",
    ],
    "Sales & Fulfilment": [
        "sales_order",
        "sales_order_item",
        "delivery",
        "payment",
        "return",
    ],
    "Warehouse Operations": [
        "stock_transfer",
    ],
}

LABELS = {
    "users": "User Accounts",
    "product_category": "Product Categories",
    "purchase_order": "Purchase Orders",
    "purchase_order_item": "Purchase Order Items",
    "sales_order": "Sales Orders",
    "sales_order_item": "Sales Order Items",
    "stock_transfer": "Stock Transfers",
}

STATUS_OPTIONS = {
    "purchase_order": [
        "Draft",
        "Placed",
        "Partially Received",
        "Received",
        "Cancelled",
    ],
    "sales_order": [
        "Pending",
        "Processing",
        "Shipped",
        "Delivered",
        "Cancelled",
        "Returned",
    ],
    "delivery": [
        "Preparing",
        "Dispatched",
        "In Transit",
        "Delivered",
        "Failed",
        "Returned",
    ],
    "payment": [
        "Pending",
        "Paid",
        "Failed",
        "Refunded",
        "Partially Refunded",
    ],
}

PAYMENT_METHOD_OPTIONS = [
    "Cash",
    "Card",
    "Bank Transfer",
    "UPI",
    "Cheque",
    "Other",
]


def label(name):
    return LABELS.get(name, name.replace("_", " ").title())


def table_for(name):
    if name not in TABLES:
        abort(404)

    try:
        return Table(name, metadata, autoload_with=engine)
    except SQLAlchemyError:
        abort(
            503,
            "Database schema is unavailable. Run schema.sql and configure DATABASE_URL.",
        )


def pk_columns(table):
    return list(table.primary_key.columns)


def encode_key(row, table):
    values = [str(row[column.name]) for column in pk_columns(table)]
    encoded = json.dumps(values).encode()
    return base64.urlsafe_b64encode(encoded).decode().rstrip("=")


def decode_key(key, table):
    try:
        padded_key = key + "=" * (-len(key) % 4)
        values = json.loads(base64.urlsafe_b64decode(padded_key))
        columns = pk_columns(table)

        if len(values) != len(columns):
            raise ValueError()

        conditions = []

        for column, value in zip(columns, values):
            type_name = column.type.__class__.__name__.lower()

            if "int" in type_name:
                value = int(value)
            elif any(
                item in type_name
                for item in ("numeric", "float", "decimal")
            ):
                value = Decimal(value)

            conditions.append(column == value)

        return and_(*conditions)

    except Exception:
        abort(404)


def ref_options(column):
    foreign_key = next(iter(column.foreign_keys), None)

    if not foreign_key:
        return None

    target = foreign_key.column.table
    primary_key = list(target.primary_key.columns)[0]

    display_column = next(
        (
            target.c[name]
            for name in (
                "name",
                "product_name",
                "category_name",
                "username",
            )
            if name in target.c
        ),
        primary_key,
    )

    with engine.connect() as connection:
        rows = connection.execute(
            select(primary_key, display_column).order_by(display_column)
        ).all()

    return [
        (str(row[0]), f"{row[0]} — {row[1]}")
        for row in rows
    ]


def form_fields(table, row=None):
    fields = []
    primary_keys = set(pk_columns(table))

    for column in table.columns:
        if column in primary_keys and column.autoincrement is True:
            continue

        if column.computed is not None or column.identity is not None:
            continue

        options = ref_options(column)
        type_name = column.type.__class__.__name__.lower()

        if column.name == "payment_method" and table.name == "payment":
            options = [
                (method, method)
                for method in PAYMENT_METHOD_OPTIONS
            ]
            kind = "select"
        elif column.name == "status" and table.name in STATUS_OPTIONS:
            options = [
                (status, status)
                for status in STATUS_OPTIONS[table.name]
            ]
            kind = "select"
        elif options is not None:
            kind = "select"
        elif "date" in type_name and "time" not in type_name:
            kind = "date"
        elif "time" in type_name:
            kind = "datetime-local"
        elif "bool" in type_name:
            kind = "checkbox"
        elif column.name == "phone":
            kind = "tel"
        elif column.name == "password_hash":
            kind = "password"
        elif column.name == "email":
            kind = "email"
        elif "text" in type_name:
            kind = "textarea"
        elif any(
            item in type_name
            for item in ("int", "numeric", "float", "decimal")
        ):
            kind = "number"
        else:
            kind = "text"

        if row is not None:
            value = row[column.name]
        elif (
            column.default is not None
            and not callable(column.default.arg)
        ):
            value = column.default.arg
        else:
            value = ""

        if isinstance(value, (date, datetime)):
            value = value.isoformat()
        elif isinstance(value, Decimal):
            value = str(value)

        if column.name == "password_hash":
            value = ""

        has_default = (
            column.default is not None
            or column.server_default is not None
        )

        fields.append(
            {
                "name": column.name,
                "label": (
                    "Password"
                    if column.name == "password_hash"
                    else column.name.replace("_", " ").title()
                ),
                "kind": kind,
                "value": "" if value is None else value,
                "required": (
                    not has_default
                    and kind != "checkbox"
                    and not (column.name == "password_hash" and row is not None)
                ),
                "placeholder": (
                    "Leave blank to keep the current password"
                    if column.name == "password_hash" and row is not None
                    else ""
                ),
                "options": options,
                "step": (
                    "any"
                    if any(
                        item in type_name
                        for item in ("numeric", "float", "decimal")
                    )
                    else "1"
                ),
            }
        )

    return fields


def parse_form(table, existing_row=None):
    data = {}
    primary_keys = set(pk_columns(table))

    for column in table.columns:
        if (
            (column in primary_keys and column.autoincrement is True)
            or column.computed is not None
            or column.identity is not None
        ):
            continue

        type_name = column.type.__class__.__name__.lower()

        # An unchecked checkbox is omitted from the request; save it as False.
        if "bool" in type_name:
            raw = request.form.get(column.name)
            data[column.name] = (
                raw is not None
                and raw.lower() in ("1", "true", "on", "yes")
            )
            continue

        raw = request.form.get(column.name, "").strip()

        # Passwords are stored as hashes. On edit, a blank password means
        # keep the existing hash rather than erase it.
        if column.name == "password_hash":
            if raw == "" and existing_row is not None:
                continue
            if raw == "":
                raise ValueError("Password is required.")
            data[column.name] = generate_password_hash(raw)
            continue

        if raw == "":
            # Let a database default fill the value. Otherwise reject blanks.
            if (
                column.default is not None
                or column.server_default is not None
            ):
                continue

            raise ValueError(
                f"{column.name.replace('_', ' ').title()} is required."
            )

        if column.name == "phone":
            if (
                len(raw) != 10
                or not raw.isascii()
                or not raw.isdigit()
            ):
                raise ValueError(
                    "Phone number must contain exactly 10 digits."
                )

        if "int" in type_name:
            data[column.name] = int(raw)
        elif any(
            item in type_name
            for item in ("numeric", "float", "decimal")
        ):
            data[column.name] = Decimal(raw)
        elif "date" in type_name and "time" not in type_name:
            data[column.name] = date.fromisoformat(raw)
        elif "time" in type_name:
            data[column.name] = datetime.fromisoformat(raw)
        else:
            data[column.name] = raw

    return data


def database_error_message(error):
    original = getattr(error, "orig", None)
    code = (
        getattr(original, "sqlstate", None)
        or getattr(original, "pgcode", None)
    )

    if code == "23505":
        return (
            "That email, phone number, primary key, or delivery order "
            "is already in use."
        )

    if code == "23502":
        return "A required field cannot be empty."

    if code == "23514":
        return "One of the values does not meet a database rule."

    if code == "23503":
        return "Choose an existing related record."

    return "The database rejected this record. Check the entered values."


@app.context_processor
def inject_navigation():
    current_table = (
        request.view_args.get("table")
        if request.view_args
        else None
    )

    return {
        "groups": GROUPS,
        "table_label": label,
        "current_table": current_table,
        "now_label": datetime.now().strftime("%d %b %Y"),
    }


@app.get("/")
def index():
    stats = {}

    try:
        with engine.connect() as connection:
            for name in (
                "warehouse",
                "employee",
                "supplier",
                "customer",
                "product",
                "sales_order",
                "purchase_order",
            ):
                stats[name] = connection.execute(
                    select(func.count()).select_from(table_for(name))
                ).scalar_one()

    except SQLAlchemyError:
        flash(
            "Could not connect to PostgreSQL. "
            "Set DATABASE_URL and run schema.sql.",
            "error",
        )

    return render_template("dashboard.html", stats=stats)


@app.get("/data/<table>")
def list_data(table):
    current_table = table_for(table)
    query = request.args.get("q", "").strip()
    classify = request.args.get("class", "")
    statement = select(current_table)

    text_columns = [
        column
        for column in current_table.columns
        if column.type.__class__.__name__.lower()
        in ("text", "varchar", "string")
    ]

    if query and text_columns:
        statement = statement.where(
            or_(
                *[
                    column.ilike(f"%{query}%")
                    for column in text_columns
                ]
            )
        )

    class_column = next(
        (
            column
            for column in current_table.columns
            if column.name
            in (
                "status",
                "category_id",
                "warehouse_id",
                "stock_class",
            )
        ),
        None,
    )

    classes = []

    if class_column is not None:
        with engine.connect() as connection:
            classes = [
                str(row[0])
                for row in connection.execute(
                    select(class_column)
                    .distinct()
                    .where(class_column.is_not(None))
                    .order_by(class_column)
                ).all()
            ]

        if classify:
            statement = statement.where(class_column == classify)

    statement = statement.order_by(*pk_columns(current_table)).limit(500)

    try:
        with engine.connect() as connection:
            rows = [
                dict(row._mapping)
                for row in connection.execute(statement)
            ]

    except SQLAlchemyError:
        rows = []
        flash(f"Could not load {label(table)}.", "error")

    # The schema stores password hashes; never show those values in tables.
    for row in rows:
        if "password_hash" in row:
            row["password_hash"] = "Stored securely"

    columns = list(current_table.columns)

    return render_template(
        "table.html",
        table=table,
        title=label(table),
        rows=rows,
        columns=columns,
        display_columns=columns[:7],
        q=query,
        classify=classify,
        classes=classes,
        key_for=lambda row: encode_key(row, current_table),
        total=len(rows),
        truncated=len(rows) == 500,
    )


@app.route("/data/<table>/new", methods=["GET", "POST"])
def create_data(table):
    current_table = table_for(table)
    fields = form_fields(current_table)

    if request.method == "POST":
        try:
            values = parse_form(current_table)

            with engine.begin() as connection:
                connection.execute(
                    current_table.insert().values(**values)
                )

            flash(f"{label(table)} record created.", "success")
            return redirect(url_for("list_data", table=table))

        except IntegrityError as error:
            flash(database_error_message(error), "error")
            fields = form_fields(current_table)

            for field in fields:
                if field["kind"] != "password":
                    field["value"] = request.form.get(field["name"], "")

        except (ValueError, TypeError, SQLAlchemyError) as error:
            flash(str(error), "error")
            fields = form_fields(current_table)

            for field in fields:
                if field["kind"] != "password":
                    field["value"] = request.form.get(field["name"], "")

    return render_template(
        "form.html",
        table=table,
        title=f"Add {label(table)}",
        fields=fields,
        action="Create record",
    )


@app.route("/data/<table>/<key>/edit", methods=["GET", "POST"])
def edit_data(table, key):
    current_table = table_for(table)
    where = decode_key(key, current_table)

    with engine.connect() as connection:
        row = connection.execute(
            select(current_table).where(where)
        ).mappings().first()

    if row is None:
        abort(404)

    fields = form_fields(current_table, row)

    if request.method == "POST":
        try:
            values = parse_form(current_table, existing_row=row)

            with engine.begin() as connection:
                connection.execute(
                    current_table.update()
                    .where(where)
                    .values(**values)
                )

            flash(f"{label(table)} record updated.", "success")
            return redirect(url_for("list_data", table=table))

        except IntegrityError as error:
            flash(database_error_message(error), "error")
            fields = form_fields(current_table, row)

            for field in fields:
                if field["kind"] != "password":
                    field["value"] = request.form.get(field["name"], "")

        except (ValueError, TypeError, SQLAlchemyError) as error:
            flash(str(error), "error")
            fields = form_fields(current_table, row)

            for field in fields:
                if field["kind"] != "password":
                    field["value"] = request.form.get(field["name"], "")

    return render_template(
        "form.html",
        table=table,
        title=f"Edit {label(table)}",
        fields=fields,
        action="Save changes",
    )


@app.post("/data/<table>/<key>/delete")
def delete_data(table, key):
    current_table = table_for(table)

    try:
        with engine.begin() as connection:
            result = connection.execute(
                current_table.delete().where(
                    decode_key(key, current_table)
                )
            )

        flash(
            "Record deleted."
            if result.rowcount
            else "Record was not found.",
            "success",
        )

    except IntegrityError:
        flash(
            "This record is still referenced by other data. "
            "Remove or reassign those records first.",
            "error",
        )

    except SQLAlchemyError:
        flash("Could not delete the record.", "error")

    return redirect(url_for("list_data", table=table))


@app.errorhandler(503)
def unavailable(error):
    return (
        render_template(
            "error.html",
            code=503,
            message=str(error.description),
        ),
        503,
    )


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
