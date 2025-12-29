from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import calendar
import os

app = Flask(__name__)
app.secret_key = "secret"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "data.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ---------------------------------------------------
# MODELS
# ---------------------------------------------------
class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    stock = db.Column(db.Integer, default=0)
    capital_per_unit = db.Column(db.Float, default=0)
    selling_price = db.Column(db.Float, default=0)
    cashier_bonus = db.Column(db.Float, default=0)        # pesos per unit (manager sets)

class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"), nullable=False)
    quantity = db.Column(db.Integer, default=0)
    total_price = db.Column(db.Float, default=0)
    cashier_bonus_earned = db.Column(db.Float, default=0)
    date = db.Column(db.DateTime, default=datetime.utcnow)

    item = db.relationship("Item")

# ---------------------------------------------------
# LOGIN
# ---------------------------------------------------
USERS = {
    "cashier": {"password": "Glitz", "role": "cashier"},
    "manager": {"password": "MarlaSchr", "role": "manager"},
}

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        user = USERS.get(username)

        if user and user["password"] == password:
            session["role"] = user["role"]
            session["user"] = username

            if user["role"] == "manager":
                return redirect(url_for("manager_panel"))
            return redirect(url_for("cashier_panel"))

        flash("Invalid credentials", "danger")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---------------------------------------------------
# CASHIER PANEL
# ---------------------------------------------------
@app.route("/cashier", methods=["GET", "POST"])
def cashier_panel():
    if session.get("role") != "cashier":
        return redirect(url_for("login"))

    items = Item.query.all()

    if request.method == "POST":
        item_id = int(request.form.get("item_id"))
        qty = int(request.form.get("quantity"))

        item = Item.query.get(item_id)

        if not item or qty <= 0 or qty > item.stock:
            flash("Invalid quantity or item", "danger")
            return redirect(url_for("cashier_panel"))

        item.stock -= qty
        total = qty * item.selling_price
        bonus = qty * item.cashier_bonus

        sale = Sale(
            item=item,
            quantity=qty,
            total_price=total,
            cashier_bonus_earned=bonus,
        )

        db.session.add(sale)
        db.session.commit()

        flash("Sale recorded", "success")
        return redirect(url_for("cashier_panel"))

    # cashier total bonus
    total_bonus = db.session.query(db.func.sum(Sale.cashier_bonus_earned)).scalar() or 0

    return render_template("cashier.html", items=items, total_bonus=total_bonus)

# ---------------------------------------------------
# MANAGER PANEL
# ---------------------------------------------------
@app.route("/manager", methods=["GET", "POST"])
def manager_panel():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    items = Item.query.all()
    sales = Sale.query.order_by(Sale.date.desc()).all()

    # Add new item OR update bonuses / stock
    if request.method == "POST" and request.form.get("form_type") == "add_item":
        name = request.form.get("name")
        stock = int(request.form.get("stock") or 0)
        capital = float(request.form.get("capital") or 0)
        price = float(request.form.get("price") or 0)
        bonus = float(request.form.get("bonus") or 0)

        item = Item(
            name=name,
            stock=stock,
            capital_per_unit=capital,
            selling_price=price,
            cashier_bonus=bonus,
        )
        db.session.add(item)
        db.session.commit()
        flash("Item added", "success")
        return redirect(url_for("manager_panel"))

    # monthly profit
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)
    _, last_day = calendar.monthrange(now.year, now.month)
    month_end = datetime(now.year, now.month, last_day, 23, 59, 59)

    monthly_sales = (
        db.session.query(db.func.sum(Sale.total_price))
        .filter(Sale.date >= month_start, Sale.date <= month_end)
        .scalar()
        or 0
    )

    monthly_capital = 0
    for s in Sale.query.filter(Sale.date >= month_start, Sale.date <= month_end).all():
        monthly_capital += s.quantity * s.item.capital_per_unit

    # fixed monthly expenses
    expenses = {
        "Electricity": 6000,
        "Water": 1000,
        "Rent": 25000,
        "BIR Tax": 900,
        "Munisipyo": 1000,
    }
    total_expenses = monthly_capital + sum(expenses.values())

    profit = monthly_sales - total_expenses

    return render_template(
        "manager.html",
        items=items,
        sales=sales,
        expenses=expenses,
        monthly_sales=monthly_sales,
        total_expenses=total_expenses,
        profit=profit,
    )

# ---------------------------------------------------
# DELETE SALE (manager only)
# ---------------------------------------------------
@app.route("/delete_sale", methods=["POST"])
def delete_sale():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    sale_id = request.form.get("sale_id")
    sale = Sale.query.get(sale_id)

    if not sale:
        flash("Sale not found", "danger")
        return redirect(url_for("manager_panel"))

    # return stock
    sale.item.stock += sale.quantity

    db.session.delete(sale)
    db.session.commit()

    flash("Sale removed and stock/cashier bonus adjusted", "info")
    return redirect(url_for("manager_panel"))

# ---------------------------------------------------
if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
