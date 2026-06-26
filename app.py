from flask import Flask, render_template, request, redirect, url_for, session, send_file
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import sqlite3
import os
import io
import base64
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'sales_secret_key_2024'

# ─── Database Setup ───────────────────────────────────────────────
def init_db():
    conn = sqlite3.connect('database/sales.db')
    c = conn.cursor()

    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        category TEXT NOT NULL,
        unit_price REAL NOT NULL,
        cost_price REAL NOT NULL,
        stock INTEGER DEFAULT 0
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS customers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        region TEXT NOT NULL,
        email TEXT
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT NOT NULL,
        product_id INTEGER,
        customer_id INTEGER,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        FOREIGN KEY(product_id) REFERENCES products(id),
        FOREIGN KEY(customer_id) REFERENCES customers(id)
    )''')

    # Default admin user
    try:
        c.execute("INSERT INTO users (username, password) VALUES (?, ?)", ('admin', 'admin123'))
    except:
        pass

    conn.commit()
    conn.close()

# ─── Helper: Load CSV into DB ─────────────────────────────────────
def load_csv_data():
    csv_path = 'dataset/sales.csv'
    if not os.path.exists(csv_path):
        return

    conn = sqlite3.connect('database/sales.db')
    c = conn.cursor()

    count = c.execute("SELECT COUNT(*) FROM sales").fetchone()[0]
    if count > 0:
        conn.close()
        return

    df = pd.read_csv(csv_path)

    for _, row in df.iterrows():
        # Insert product if not exists
        c.execute("INSERT OR IGNORE INTO products (name, category, unit_price, cost_price, stock) VALUES (?,?,?,?,?)",
                  (row['product_name'], row['category'], row['unit_price'], row['cost_price'], 100))
        product = c.execute("SELECT id FROM products WHERE name=?", (row['product_name'],)).fetchone()

        # Insert customer if not exists
        c.execute("INSERT OR IGNORE INTO customers (name, region) VALUES (?,?)",
                  (row['customer_name'], row['region']))
        customer = c.execute("SELECT id FROM customers WHERE name=?", (row['customer_name'],)).fetchone()

        # Insert sale
        c.execute("INSERT INTO sales (date, product_id, customer_id, quantity, unit_price) VALUES (?,?,?,?,?)",
                  (row['date'], product[0], customer[0], row['quantity'], row['unit_price']))

    conn.commit()
    conn.close()

# ─── Helper: Chart to Base64 ─────────────────────────────────────
def fig_to_base64(fig):
    buf = io.BytesIO()
    fig.savefig(buf, format='png', bbox_inches='tight', facecolor='#1e1e2e')
    buf.seek(0)
    img_base64 = base64.b64encode(buf.read()).decode('utf-8')
    plt.close(fig)
    return img_base64

# ─── Routes ──────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user' in session:
        return redirect(url_for('dashboard'))
    return render_template('index.html')

@app.route('/login', methods=['POST'])
def login():
    username = request.form['username']
    password = request.form['password']
    conn = sqlite3.connect('database/sales.db')
    user = conn.execute("SELECT * FROM users WHERE username=? AND password=?",
                        (username, password)).fetchone()
    conn.close()
    if user:
        session['user'] = username
        return redirect(url_for('dashboard'))
    return render_template('index.html', error='Invalid credentials!')

@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('index'))

# ─── Dashboard ───────────────────────────────────────────────────
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('index'))

    conn = sqlite3.connect('database/sales.db')

    # KPI Cards
    total_sales = conn.execute(
        "SELECT SUM(s.quantity * s.unit_price) FROM sales s").fetchone()[0] or 0

    total_profit = conn.execute(
        "SELECT SUM(s.quantity * (s.unit_price - p.cost_price)) FROM sales s JOIN products p ON s.product_id=p.id").fetchone()[0] or 0

    total_orders = conn.execute("SELECT COUNT(*) FROM sales").fetchone()[0]

    best_product = conn.execute(
        "SELECT p.name, SUM(s.quantity) as qty FROM sales s JOIN products p ON s.product_id=p.id GROUP BY p.name ORDER BY qty DESC LIMIT 1").fetchone()

    # Monthly Revenue Data
    monthly = conn.execute(
        "SELECT strftime('%Y-%m', date) as month, SUM(quantity * unit_price) as revenue FROM sales GROUP BY month ORDER BY month").fetchall()

    # Category Sales
    category = conn.execute(
        "SELECT p.category, SUM(s.quantity * s.unit_price) as revenue FROM sales s JOIN products p ON s.product_id=p.id GROUP BY p.category").fetchall()

    # Region Sales
    region = conn.execute(
        "SELECT c.region, SUM(s.quantity * s.unit_price) as revenue FROM sales s JOIN customers c ON s.customer_id=c.id GROUP BY c.region").fetchall()

    conn.close()

    # ── Chart 1: Monthly Revenue Line Chart ──
    months = [r[0] for r in monthly]
    revenues = [r[1] for r in monthly]
    fig1, ax1 = plt.subplots(figsize=(9, 3.5))
    fig1.patch.set_facecolor('#1e1e2e')
    ax1.set_facecolor('#1e1e2e')
    ax1.plot(months, revenues, color='#7c3aed', linewidth=2.5, marker='o', markersize=5)
    ax1.fill_between(months, revenues, alpha=0.15, color='#7c3aed')
    ax1.set_title('Monthly Revenue Trend', color='white', fontsize=13, pad=10)
    ax1.tick_params(colors='#aaa', labelsize=8)
    ax1.spines[:].set_color('#333')
    plt.xticks(rotation=45)
    chart1 = fig_to_base64(fig1)

    # ── Chart 2: Category Pie Chart ──
    cat_labels = [r[0] for r in category]
    cat_values = [r[1] for r in category]
    colors = ['#7c3aed', '#06b6d4', '#10b981', '#f59e0b', '#ef4444']
    fig2, ax2 = plt.subplots(figsize=(5, 4))
    fig2.patch.set_facecolor('#1e1e2e')
    ax2.set_facecolor('#1e1e2e')
    wedges, texts, autotexts = ax2.pie(cat_values, labels=cat_labels, autopct='%1.1f%%',
                                        colors=colors[:len(cat_labels)], startangle=90)
    for text in texts + autotexts:
        text.set_color('white')
        text.set_fontsize(9)
    ax2.set_title('Sales by Category', color='white', fontsize=12)
    chart2 = fig_to_base64(fig2)

    # ── Chart 3: Region Bar Chart ──
    reg_labels = [r[0] for r in region]
    reg_values = [r[1] for r in region]
    fig3, ax3 = plt.subplots(figsize=(5, 4))
    fig3.patch.set_facecolor('#1e1e2e')
    ax3.set_facecolor('#1e1e2e')
    bars = ax3.bar(reg_labels, reg_values, color=['#7c3aed', '#06b6d4', '#10b981', '#f59e0b', '#ef4444'])
    ax3.set_title('Revenue by Region', color='white', fontsize=12)
    ax3.tick_params(colors='#aaa')
    ax3.spines[:].set_color('#333')
    for bar, val in zip(bars, reg_values):
        ax3.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 500,
                 f'₹{val/1000:.0f}K', ha='center', color='white', fontsize=8)
    chart3 = fig_to_base64(fig3)

    return render_template('dashboard.html',
        total_sales=f"₹{total_sales:,.0f}",
        total_profit=f"₹{total_profit:,.0f}",
        total_orders=total_orders,
        best_product=best_product[0] if best_product else 'N/A',
        chart1=chart1, chart2=chart2, chart3=chart3,
        user=session['user']
    )

# ─── Products ────────────────────────────────────────────────────
@app.route('/products')
def products():
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect('database/sales.db')
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return render_template('products.html', products=products, user=session['user'])

@app.route('/add_product', methods=['POST'])
def add_product():
    if 'user' not in session:
        return redirect(url_for('index'))
    name = request.form['name']
    category = request.form['category']
    unit_price = float(request.form['unit_price'])
    cost_price = float(request.form['cost_price'])
    stock = int(request.form['stock'])
    conn = sqlite3.connect('database/sales.db')
    conn.execute("INSERT INTO products (name, category, unit_price, cost_price, stock) VALUES (?,?,?,?,?)",
                 (name, category, unit_price, cost_price, stock))
    conn.commit()
    conn.close()
    return redirect(url_for('products'))

# ─── Sales ───────────────────────────────────────────────────────
@app.route('/sales')
def sales():
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect('database/sales.db')
    sales = conn.execute('''
        SELECT s.id, s.date, p.name, c.name, s.quantity, s.unit_price,
               (s.quantity * s.unit_price) as total
        FROM sales s
        JOIN products p ON s.product_id = p.id
        JOIN customers c ON s.customer_id = c.id
        ORDER BY s.date DESC
    ''').fetchall()
    products = conn.execute("SELECT * FROM products").fetchall()
    customers = conn.execute("SELECT * FROM customers").fetchall()
    conn.close()
    return render_template('sales.html', sales=sales, products=products,
                           customers=customers, user=session['user'])

@app.route('/add_sale', methods=['POST'])
def add_sale():
    if 'user' not in session:
        return redirect(url_for('index'))
    date = request.form['date']
    product_id = request.form['product_id']
    customer_id = request.form['customer_id']
    quantity = int(request.form['quantity'])
    conn = sqlite3.connect('database/sales.db')
    unit_price = conn.execute("SELECT unit_price FROM products WHERE id=?", (product_id,)).fetchone()[0]
    conn.execute("INSERT INTO sales (date, product_id, customer_id, quantity, unit_price) VALUES (?,?,?,?,?)",
                 (date, product_id, customer_id, quantity, unit_price))
    conn.commit()
    conn.close()
    return redirect(url_for('sales'))

# ─── CSV Export ──────────────────────────────────────────────────
@app.route('/export_csv')
def export_csv():
    if 'user' not in session:
        return redirect(url_for('index'))
    conn = sqlite3.connect('database/sales.db')
    df = pd.read_sql_query('''
        SELECT s.id, s.date, p.name as product, c.name as customer,
               c.region, s.quantity, s.unit_price,
               (s.quantity * s.unit_price) as total_revenue,
               (s.quantity * (s.unit_price - p.cost_price)) as profit
        FROM sales s
        JOIN products p ON s.product_id = p.id
        JOIN customers c ON s.customer_id = c.id
        ORDER BY s.date
    ''', conn)
    conn.close()
    path = 'dataset/export.csv'
    df.to_csv(path, index=False)
    return send_file(path, as_attachment=True, download_name='sales_report.csv')

# ─── Run ─────────────────────────────────────────────────────────
if __name__ == '__main__':
    os.makedirs('database', exist_ok=True)
    init_db()
    load_csv_data()
    app.run(debug=True)