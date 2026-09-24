#!/usr/bin/env python3
import datetime
import logging
import random
import uuid

import time_uuid
from cassandra.query import BatchStatement

# Set logger
log = logging.getLogger()

CREATE_KEYSPACE = """
        CREATE KEYSPACE IF NOT EXISTS {}
        WITH replication = {{ 'class': 'SimpleStrategy', 'replication_factor': {} }}
"""

# Q1: orders_by_customers
CREATE_ORDERS_BY_CUSTOMERS_TABLE = """
    CREATE TABLE IF NOT EXISTS orders_by_customers (
        email TEXT,
        order_date TIMEUUID,
        name TEXT STATIC,
        order_number TEXT,
        total_amount DECIMAL,
        status TEXT,
        PRIMARY KEY ((email), order_date)
    ) WITH CLUSTERING ORDER BY (order_date DESC)
"""

# Q2: products_by_order
# PK: order_number (todos los productos de una orden viven en la misma partición)
# CK: price DESC para cumplir el ordenamiento; product_name evita sobreescrituras
#     cuando dos productos de la misma orden cuestan lo mismo.
CREATE_PRODUCTS_BY_ORDER_TABLE = """
    CREATE TABLE IF NOT EXISTS products_by_order (
        order_number TEXT,
        price DECIMAL,
        product_name TEXT,
        category TEXT,
        quantity INT,
        PRIMARY KEY ((order_number), price, product_name)
    ) WITH CLUSTERING ORDER BY (price DESC, product_name ASC)
"""

# Q3.1 & Q3.2: shipments_by_o_sd
# PK: order_number
# CK: shipment_date DESC (orden + rango de fechas); tracking_number desempata.
CREATE_SHIPMENTS_BY_O_SD_TABLE = """
    CREATE TABLE IF NOT EXISTS shipments_by_o_sd (
        order_number TEXT,
        shipment_date TIMEUUID,
        tracking_number TEXT,
        status TEXT,
        type TEXT,
        total_amount DECIMAL,
        customer_name TEXT,
        PRIMARY KEY ((order_number), shipment_date, tracking_number)
    ) WITH CLUSTERING ORDER BY (shipment_date DESC, tracking_number ASC)
"""

# Q3.3: shipments_by_o_ssd
# PK compuesta: (order_number, status) -> el filtro por status es igualdad sobre la partición
# CK: shipment_date DESC permite el rango opcional de fechas.
CREATE_SHIPMENTS_BY_O_SSD_TABLE = """
    CREATE TABLE IF NOT EXISTS shipments_by_o_ssd (
        order_number TEXT,
        status TEXT,
        shipment_date TIMEUUID,
        tracking_number TEXT,
        type TEXT,
        total_amount DECIMAL,
        customer_name TEXT,
        PRIMARY KEY ((order_number, status), shipment_date, tracking_number)
    ) WITH CLUSTERING ORDER BY (shipment_date DESC, tracking_number ASC)
"""

# Q3.4: shipments_by_o_tsd
# PK compuesta: (order_number, type)
CREATE_SHIPMENTS_BY_O_TSD_TABLE = """
    CREATE TABLE IF NOT EXISTS shipments_by_o_tsd (
        order_number TEXT,
        type TEXT,
        shipment_date TIMEUUID,
        tracking_number TEXT,
        status TEXT,
        total_amount DECIMAL,
        customer_name TEXT,
        PRIMARY KEY ((order_number, type), shipment_date, tracking_number)
    ) WITH CLUSTERING ORDER BY (shipment_date DESC, tracking_number ASC)
"""

# Q3.5: shipments_by_o_tssd
# PK compuesta: (order_number, type, status)
CREATE_SHIPMENTS_BY_O_TSSD_TABLE = """
    CREATE TABLE IF NOT EXISTS shipments_by_o_tssd (
        order_number TEXT,
        type TEXT,
        status TEXT,
        shipment_date TIMEUUID,
        tracking_number TEXT,
        total_amount DECIMAL,
        customer_name TEXT,
        PRIMARY KEY ((order_number, type, status), shipment_date, tracking_number)
    ) WITH CLUSTERING ORDER BY (shipment_date DESC, tracking_number ASC)
"""


# Query statements 
# Q1
SELECT_ORDERS_BY_CUSTOMER = """
    SELECT email, toDate(order_date) as order_date_readable, name, order_number, total_amount, status
    FROM orders_by_customers
    WHERE email = ?
"""

# Q2
SELECT_PRODUCTS_BY_ORDER = """
    SELECT order_number, price, product_name, category, quantity
    FROM products_by_order
    WHERE order_number = ?
"""

# Q3.1: All shipments (no date filter)
SELECT_SHIPMENTS_BY_ORDER = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_sd
    WHERE order_number = ?
"""

# Q3.2: Same as Q3.1 (with date range)
SELECT_SHIPMENTS_BY_ORDER_DATE_RANGE = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_sd
    WHERE order_number = ?
      AND shipment_date >= minTimeUuid(?) AND shipment_date <= maxTimeUuid(?)
"""

# Q3.3: Shipments by status with date range
SELECT_SHIPMENTS_BY_ORDER_STATUS = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_ssd
    WHERE order_number = ? AND status = ?
      AND shipment_date >= minTimeUuid(?) AND shipment_date <= maxTimeUuid(?)
"""

# Q3.4: Shipments by type with date range
SELECT_SHIPMENTS_BY_ORDER_TYPE = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_tsd
    WHERE order_number = ? AND type = ?
      AND shipment_date >= minTimeUuid(?) AND shipment_date <= maxTimeUuid(?)
"""

# Q3.5: Shipments by type and status with date range
SELECT_SHIPMENTS_BY_ORDER_TYPE_STATUS = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_tssd
    WHERE order_number = ? AND type = ? AND status = ?
      AND shipment_date >= minTimeUuid(?) AND shipment_date <= maxTimeUuid(?)
"""

# Variantes sin rango de fecha (el filtro de fecha es opcional en Q3.3 - Q3.5)
SELECT_SHIPMENTS_BY_ORDER_STATUS_NO_DATE = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_ssd
    WHERE order_number = ? AND status = ?
"""

SELECT_SHIPMENTS_BY_ORDER_TYPE_NO_DATE = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_tsd
    WHERE order_number = ? AND type = ?
"""

SELECT_SHIPMENTS_BY_ORDER_TYPE_STATUS_NO_DATE = """
    SELECT order_number, toDate(shipment_date) as shipment_date_readable, tracking_number, status, type, total_amount, customer_name
    FROM shipments_by_o_tssd
    WHERE order_number = ? AND type = ? AND status = ?
"""

# Inserts de envíos: mismo orden de columnas para las 4 tablas,
# así la misma tupla de datos sirve para todas.
INSERT_SHIPMENT = """
    INSERT INTO {} (order_number, shipment_date, tracking_number, status, type, total_amount, customer_name)
    VALUES (?, ?, ?, ?, ?, ?, ?)
"""
SHIPMENT_TABLES = ['shipments_by_o_sd', 'shipments_by_o_ssd', 'shipments_by_o_tsd', 'shipments_by_o_tssd']


# Sample data
CUSTOMERS = [
    ('juan.perez@email.com', 'Juan Pérez', '+52-33-1234-5678', 'Av. Patria 1234, Zapopan, Jalisco'),
    ('maria.gonzalez@email.com', 'María González', '+52-33-2345-6789', 'Calle Independencia 567, Guadalajara, Jalisco'),
    ('carlos.rodriguez@email.com', 'Carlos Rodríguez', '+52-33-3456-7890', 'Av. Américas 890, Guadalajara, Jalisco'),
    ('ana.martinez@email.com', 'Ana Martínez', '+52-33-4567-8901', 'Calle Libertad 123, Tlaquepaque, Jalisco'),
    ('luis.lopez@email.com', 'Luis López', '+52-33-5678-9012', 'Av. López Mateos 456, Zapopan, Jalisco'),
    ('sofia.hernandez@email.com', 'Sofía Hernández', '+52-33-6789-0123', 'Calle Reforma 789, Guadalajara, Jalisco')
]

PRODUCTS = [
    ('Laptop Dell XPS 13', 'Electrónicos', 25000.00),
    ('iPhone 14 Pro', 'Electrónicos', 28000.00),
    ('Samsung Galaxy S23', 'Electrónicos', 22000.00),
    ('Nike Air Max 270', 'Calzado', 3500.00),
    ('Adidas Ultraboost 22', 'Calzado', 4200.00),
    ('Levi\'s 501 Jeans', 'Ropa', 1800.00),
    ('Camisa Hugo Boss', 'Ropa', 2500.00),
    ('Mochila North Face', 'Accesorios', 1200.00),
    ('Reloj Apple Watch Series 8', 'Electrónicos', 8500.00),
    ('Audífonos Sony WH-1000XM4', 'Electrónicos', 6500.00),
    ('Cafetera Nespresso', 'Hogar', 3200.00),
    ('Aspiradora Dyson V11', 'Hogar', 12000.00),
    ('Licuadora Vitamix', 'Hogar', 8000.00),
    ('Perfume Chanel No. 5', 'Belleza', 4500.00),
    ('Crema La Mer', 'Belleza', 6000.00)
]

ORDER_STATUSES = ['Pending', 'Processing', 'Shipped', 'Delivered', 'Cancelled']
SHIPMENT_STATUSES = ['Pending', 'Shipped', 'In Transit', 'Out for Delivery', 'Delivered', 'Delayed', 'Returned']
SHIPMENT_TYPES = ['Standard', 'Express', 'Same-day']

# Get date range from user input or use default (last 30 days)
# Default to last 30 days if not provided
# Si optional=True y ambas fechas se dejan vacías, regresa (None, None) = sin filtro de fecha
def get_date_range(optional=False):
    """Pide fecha inicial y final (YYYY-MM-DD).
    Devuelve datetimes: inicio a las 00:00:00 y fin a las 23:59:59.999 para que el rango sea inclusivo."""
    today = datetime.date.today()
    default_start = today - datetime.timedelta(days=30)

    hint = "blank = no date filter" if optional else f"blank = {default_start} to {today}"
    print(f"\nDate range (YYYY-MM-DD), {hint}")
    start_str = input('Start date: ').strip()
    end_str = input('End date: ').strip()

    if optional and not start_str and not end_str:
        return None, None

    try:
        start = datetime.date.fromisoformat(start_str) if start_str else default_start
        end = datetime.date.fromisoformat(end_str) if end_str else today
    except ValueError:
        print("Invalid date format, using last 30 days.")
        start, end = default_start, today

    if start > end:
        start, end = end, start

    start_dt = datetime.datetime.combine(start, datetime.time.min)
    end_dt = datetime.datetime.combine(end, datetime.time(23, 59, 59, 999000))
    return start_dt, end_dt

def execute_batch(session, stmt, data):
    batch_size = 10
    for i in range(0, len(data), batch_size):
        batch = BatchStatement()
        for item in data[i : i+batch_size]:
            batch.add(stmt, item)
        session.execute(batch)

def bulk_insert(session):
    # Prepare statements
    orders_stmt = session.prepare("INSERT INTO orders_by_customers (email, order_date, name, order_number, total_amount, status) VALUES (?, ?, ?, ?, ?, ?)")
    products_stmt = session.prepare("INSERT INTO products_by_order (order_number, price, product_name, category, quantity) VALUES (?, ?, ?, ?, ?)")
    shipment_stmts = [session.prepare(INSERT_SHIPMENT.format(table)) for table in SHIPMENT_TABLES]
    
    orders_num = 100
    products_per_order = 3
    shipments_per_order = 10
    
    orders_data = []
    products_data = []
    shipments_data = []
    
    # Generate orders
    for i in range(orders_num):
        customer = random.choice(CUSTOMERS)
        order_number = f"ORD-{uuid.uuid4().hex[:8].upper()}"
        order_date = random_date(datetime.datetime(2024, 1, 1), datetime.datetime(2025, 12, 31))
        total_amount = 0
        
        # Generate products for this order
        selected_products = random.sample(PRODUCTS, products_per_order)
        for product_name, category, price in selected_products:
            quantity = random.randint(1, 3)
            total_amount += price * quantity
            products_data.append((order_number, price, product_name, category, quantity))
        
        status = random.choice(ORDER_STATUSES)
        orders_data.append((customer[0], order_date, customer[1], order_number, total_amount, status))
        
        # Generate shipments for this order
        for j in range(shipments_per_order):
            tracking_number = f"TRK-{uuid.uuid4().hex[:10].upper()}"
            shipment_date = random_date(datetime.datetime(2024, 1, 1), datetime.datetime(2025, 12, 31))
            ship_status = random.choice(SHIPMENT_STATUSES)
            ship_type = random.choice(SHIPMENT_TYPES)
            ship_amount = total_amount / shipments_per_order
            
            # Add to all shipment tables
            shipments_data.append((order_number, shipment_date, tracking_number, ship_status, ship_type, ship_amount, customer[1]))
    
    # Execute batch inserts
    execute_batch(session, orders_stmt, orders_data)
    execute_batch(session, products_stmt, products_data)
    
    # Insert into all shipment tables (same data, same order)
    for stmt in shipment_stmts:
        execute_batch(session, stmt, shipments_data)

def random_date(start_date, end_date):
    """Generate a random date between start_date and end_date"""
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_number_of_days = random.randrange(days_between_dates)
    rand_date = start_date + datetime.timedelta(days=random_number_of_days)
    return time_uuid.TimeUUID.with_timestamp(time_uuid.mkutime(rand_date))

def create_keyspace(session, keyspace, replication_factor):
    log.info(f"Creating keyspace: {keyspace} with replication factor {replication_factor}")
    session.execute(CREATE_KEYSPACE.format(keyspace, replication_factor))

def create_schema(session):
    log.info("Creating logistics schema")
    session.execute(CREATE_ORDERS_BY_CUSTOMERS_TABLE)
    session.execute(CREATE_PRODUCTS_BY_ORDER_TABLE)
    session.execute(CREATE_SHIPMENTS_BY_O_SD_TABLE)
    session.execute(CREATE_SHIPMENTS_BY_O_SSD_TABLE)
    session.execute(CREATE_SHIPMENTS_BY_O_TSD_TABLE)
    session.execute(CREATE_SHIPMENTS_BY_O_TSSD_TABLE)

# Q1: Get orders by customer
def get_orders_by_customer(session, email):
    log.info(f"Retrieving orders for customer: {email}")
    stmt = session.prepare(SELECT_ORDERS_BY_CUSTOMER)
    rows = session.execute(stmt, [email])
    
    print(f"\n=== Orders for customer: {email} ===")
    for row in rows:
        print(f"Order: {row.order_number}")
        print(f"  - Date: {row.order_date_readable}")
        print(f"  - Customer: {row.name}")
        print(f"  - Total: ${row.total_amount:,.2f}")
        print(f"  - Status: {row.status}")
        print()

# Q2: Get products by order
def get_products_by_order(session, order_number):
    log.info(f"Retrieving products for order: {order_number}")
    stmt = session.prepare(SELECT_PRODUCTS_BY_ORDER)
    rows = list(session.execute(stmt, [order_number]))

    print(f"\n=== Products for order: {order_number} ===")
    if not rows:
        print("No products found for this order.")
        return

    total = 0
    for row in rows:
        subtotal = float(row.price) * row.quantity
        total += subtotal
        print(f"Product: {row.product_name}")
        print(f"  - Category: {row.category}")
        print(f"  - Price: ${row.price:,.2f}")
        print(f"  - Quantity: {row.quantity}")
        print(f"  - Subtotal: ${subtotal:,.2f}")
        print()
    print(f"Order total: ${total:,.2f}")

def print_shipments(rows, title):
    rows = list(rows)
    print(f"\n=== {title} ===")
    if not rows:
        print("No shipments found.")
        return
    for row in rows:
        print(f"Tracking: {row.tracking_number}")
        print(f"  - Date: {row.shipment_date_readable}")
        print(f"  - Customer: {row.customer_name}")
        print(f"  - Status: {row.status}")
        print(f"  - Type: {row.type}")
        print(f"  - Amount: ${row.total_amount:,.2f}")
        print()
    print(f"Total shipments: {len(rows)}")

# Q3.1: Get all shipments by order (no date filter)
def get_shipments_by_order(session, order_number):
    log.info(f"Retrieving all shipments for order: {order_number}")
    stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER)
    rows = session.execute(stmt, [order_number])
    print_shipments(rows, f"Shipments for order: {order_number}")

# Q3.2: Same as Q3.1 (with explicit date range)
def get_shipments_by_order_date_range(session, order_number, start_date, end_date):
    log.info(f"Retrieving shipments for order {order_number} between {start_date} and {end_date}")
    stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER_DATE_RANGE)
    rows = session.execute(stmt, [order_number, start_date, end_date])
    print_shipments(rows, f"Shipments for order {order_number} ({start_date.date()} to {end_date.date()})")

def range_label(start_date, end_date):
    if start_date is None:
        return "all dates"
    return f"{start_date.date()} to {end_date.date()}"

# Q3.3: Get shipments by order and status with date range (fecha opcional)
def get_shipments_by_order_status(session, order_number, status, start_date=None, end_date=None):
    log.info(f"Retrieving shipments for order {order_number} with status {status}")
    if start_date is not None:
        stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER_STATUS)
        rows = session.execute(stmt, [order_number, status, start_date, end_date])
    else:
        stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER_STATUS_NO_DATE)
        rows = session.execute(stmt, [order_number, status])
    print_shipments(rows, f"Shipments for order {order_number} | status={status} ({range_label(start_date, end_date)})")

# Q3.4: Get shipments by order and type with date range (fecha opcional)
def get_shipments_by_order_type(session, order_number, ship_type, start_date=None, end_date=None):
    log.info(f"Retrieving shipments for order {order_number} with type {ship_type}")
    if start_date is not None:
        stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER_TYPE)
        rows = session.execute(stmt, [order_number, ship_type, start_date, end_date])
    else:
        stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER_TYPE_NO_DATE)
        rows = session.execute(stmt, [order_number, ship_type])
    print_shipments(rows, f"Shipments for order {order_number} | type={ship_type} ({range_label(start_date, end_date)})")

# Q3.5: Get shipments by order, type and status with date range (fecha opcional)
def get_shipments_by_order_type_status(session, order_number, ship_type, status, start_date=None, end_date=None):
    log.info(f"Retrieving shipments for order {order_number} with type {ship_type} and status {status}")
    if start_date is not None:
        stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER_TYPE_STATUS)
        rows = session.execute(stmt, [order_number, ship_type, status, start_date, end_date])
    else:
        stmt = session.prepare(SELECT_SHIPMENTS_BY_ORDER_TYPE_STATUS_NO_DATE)
        rows = session.execute(stmt, [order_number, ship_type, status])
    print_shipments(rows, f"Shipments for order {order_number} | type={ship_type}, status={status} ({range_label(start_date, end_date)})")