import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "supersecret"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "data.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ---------------- MODELS ---------------- #

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))
    role = db.Column(db.String(20))   # "manager" or "cashier"


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    price = db.Column(db.Float)
    stock = db.Column(db.Integer)


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    cashier = db.Column(db.String(50))
    item_name = db.Column(db.String(100))
    quantity = db.Column(db.Integer)
    total = db.Column(db.Float)
    cashier_bonus = db.Column(db.Float)
    date = db.Column(db.DateTime, default=datetime.utcnow)
    deleted = db.Column(db.Boolean, default=False)   # NEW (undo sales safely)


# ----------------- HELPERS ----------------- #

MONTHLY_EXPENSE = (
    6000 +     # Electricity
    1000 +     # Water
    25000 +    # Rent
    900 +      # BIR
    1000       # Munisipyo
)

BONUS_RATE = 0.05   # 5% bonus per sale


def get_month_key(dt):
    return dt.strftime("%Y-%m")


# ----------------- AUTH ----------------- #

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        user = User.query.filter_by(username=u, password=p).first()

        if not user:
            flash("Invalid credentials")
            return redirect(url_for("login"))

        session["user"] = user.username
        session["role"] = user.role

        if user.role == "manager":
            return redirect(url_for("manager_panel"))
        return redirect(url_for("cashier_panel"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ----------------- CASHIER ----------------- #

@app.route("/cashier", methods=["GET", "POST"])
def cashier_panel():
    if "role" not in session or session["role"] != "cashier":
        return redirect(url_for("login"))

    user = session["user"]
    items = Item.query.all()

    if request.method == "POST":
        item_id = int(request.form["item"])
        qty = int(request.form["quantity"])

        item = Item.query.get(item_id)

        if item.stock < qty:
            flash("Not enough stock!")
            return redirect(url_for("cashier_panel"))

        total = item.price * qty
        bonus = total * BONUS_RATE

        sale = Sale(
            cashier=user,
            item_name=item.name,
            quantity=qty,
            total=total,
            cashier_bonus=bonus,
        )

        item.stock -= qty
        db.session.add(sale)
        db.session.commit()

        flash("Sale recorded!")

    sales = Sale.query.filter_by(cashier=user, deleted=False).all()
    total_bonus = sum(s.cashier_bonus for s in sales)

    return render_template(
        "cashier.html",
        items=items,
        sales=sales,
        total_bonus=total_bonus,
    )


# ----------------- MANAGER ----------------- #

@app.route("/manager")
def manager_panel():
    if "role" not in session or session["role"] != "manager":
        return redirect(url_for("login"))

    items = Item.query.all()
    sales = Sale.query.filter_by(deleted=False).all()

    monthly_sales = {}
    for s in sales:
        key = get_month_key(s.date)
        monthly_sales.setdefault(key, 0)
        monthly_sales[key] += s.total

    # calculate indicators
    indicators = []
    for month, total in monthly_sales.items():
        profit = total - MONTHLY_EXPENSE
        indicators.append({
            "month": month,
            "total": total,
            "profit": profit,
            "status": "green" if profit >= 0 else "red"
        })

    return render_template(
        "manager.html",
        items=items,
        sales=sales,
        indicators=indicators,
        expense=MONTHLY_EXPENSE,
    )


# ----------- MANAGER: ADD ITEM ----------- #

@app.route("/add_item", methods=["POST"])
def add_item():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    name = request.form["name"]
    price = float(request.form["price"])
    stock = int(request.form["stock"])

    db.session.add(Item(name=name, price=price, stock=stock))
    db.session.commit()

    return redirect(url_for("manager_panel"))


# ----------- MANAGER: DELETE SALE (UNDO) ----------- #

@app.route("/delete_sale/<int:sale_id>")
def delete_sale(sale_id):
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    sale = Sale.query.get_or_404(sale_id)

    if sale.deleted:
        return redirect(url_for("manager_panel"))

    # restore stock
    item = Item.query.filter_by(name=sale.item_name).first()
    if item:
        item.stock += sale.quantity

    # mark sale deleted (bonus automatically excluded everywhere)
    sale.deleted = True
    db.session.commit()

    flash("Sale removed and cashier bonus adjusted.")
    return redirect(url_for("manager_panel"))


# ----------- INIT DATABASE (RUN ONCE ON RENDER) ----------- #

@app.route("/initdb")
def initdb():
    db.create_all()

    # Create default accounts if missing
    if not User.query.filter_by(username="manager").first():
        db.session.add(User(username="manager", password="1234", role="manager"))
    if not User.query.filter_by(username="cashier").first():
        db.session.add(User(username="cashier", password="1234", role="cashier"))

    db.session.commit()
    return "Database initialized"


# -------------- RUN LOCAL ---------------- #

if __name__ == "__main__":
    with app.app_context():
        db.create_all()
    app.run(debug=True)
