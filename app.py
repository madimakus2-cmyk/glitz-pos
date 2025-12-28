from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import os

app = Flask(__name__)
app.secret_key = "secret123"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///glitz.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ------------------ MODELS ------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    role = db.Column(db.String(20))   # cashier, manager


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    price = db.Column(db.Float)
    stock = db.Column(db.Integer, default=0)


class Expense(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    amount = db.Column(db.Float)
    month = db.Column(db.String(10))   # yyyy-mm


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_name = db.Column(db.String(120))
    quantity = db.Column(db.Integer)
    price = db.Column(db.Float)
    cashier = db.Column(db.String(120))
    date = db.Column(db.DateTime, default=datetime.utcnow)

    # ---- NEW FIELDS (undo sale) ----
    is_deleted = db.Column(db.Boolean, default=False)
    deleted_by = db.Column(db.String(120))
    deleted_at = db.Column(db.DateTime)


with app.app_context():
    db.create_all()

# ------------------ AUTH ------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        user = User.query.filter_by(username=username, password=password, role=role).first()

        if user:
            session["username"] = username
            session["role"] = role

            if role == "manager":
                return redirect(url_for("manager_panel"))
            else:
                return redirect(url_for("cashier_panel"))

        flash("Invalid credentials", "danger")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------ CASHIER ------------------

@app.route("/cashier")
def cashier_panel():
    if session.get("role") != "cashier":
        return redirect(url_for("login"))

    items = Item.query.all()
    return render_template("cashier.html", items=items)


@app.route("/cashier/sell", methods=["POST"])
def cashier_sell():
    if session.get("role") != "cashier":
        return redirect(url_for("login"))

    item_id = request.form["item_id"]
    quantity = int(request.form["quantity"])

    item = Item.query.get(item_id)

    if not item or item.stock < quantity:
        flash("Not enough stock!", "danger")
        return redirect(url_for("cashier_panel"))

    item.stock -= quantity

    sale = Sale(
        item_name=item.name,
        quantity=quantity,
        price=item.price,
        cashier=session["username"]
    )

    db.session.add(sale)
    db.session.commit()

    flash("Sale recorded", "success")
    return redirect(url_for("cashier_panel"))


# ------------------ MANAGER ------------------

@app.route("/manager")
def manager_panel():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    items = Item.query.all()
    sales = Sale.query.order_by(Sale.date.desc()).all()
    expenses = Expense.query.all()

    return render_template(
        "manager.html",
        items=items,
        sales=sales,
        expenses=expenses,
    )


@app.route("/manager/add-item", methods=["POST"])
def manager_add_item():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    name = request.form["name"]
    price = float(request.form["price"])
    stock = int(request.form["stock"])

    item = Item(name=name, price=price, stock=stock)
    db.session.add(item)
    db.session.commit()

    flash("Item added", "success")
    return redirect(url_for("manager_panel"))


@app.route("/manager/add-expense", methods=["POST"])
def manager_add_expense():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    name = request.form["name"]
    amount = float(request.form["amount"])

    month = f"{datetime.utcnow().year}-{datetime.utcnow().month:02d}"

    expense = Expense(name=name, amount=amount, month=month)
    db.session.add(expense)
    db.session.commit()

    flash("Expense saved", "success")
    return redirect(url_for("manager_panel"))


# ------------------ UNDO SALE (MANAGER ONLY) ------------------

@app.route("/manager/delete-sale/<int:sale_id>", methods=["POST"])
def delete_sale(sale_id):
    if session.get("role") != "manager":
        return "Unauthorized", 403

    sale = Sale.query.get_or_404(sale_id)

    sale.is_deleted = True
    sale.deleted_by = session["username"]
    sale.deleted_at = datetime.utcnow()

    db.session.commit()

    flash("Sale removed — cashier bonus updated.", "warning")
    return redirect(url_for("manager_panel"))


# ------------------ BONUS HELPER ------------------

def calculate_bonus(cashier):
    valid_sales = Sale.query.filter_by(cashier=cashier, is_deleted=False).all()
    total = sum(s.price * s.quantity for s in valid_sales)
    return total * 0.05   # change if needed


# ------------------ RUN ------------------

if __name__ == "__main__":
    app.run(debug=True)
