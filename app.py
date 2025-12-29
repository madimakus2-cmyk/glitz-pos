from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
import calendar

app = Flask(__name__)
app.secret_key = "secret123"

app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///store.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)


# ------------------- MODELS -------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50))
    password = db.Column(db.String(50))
    role = db.Column(db.String(20))


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80))
    stock = db.Column(db.Integer)
    capital_per_unit = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    cashier_bonus = db.Column(db.Float)   # pesos per unit bonus


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    quantity = db.Column(db.Integer)
    selling_price = db.Column(db.Float)
    cashier_bonus = db.Column(db.Float)
    cashier_name = db.Column(db.String(50))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    item = db.relationship("Item")


# ------------------- APP STARTUP -------------------

with app.app_context():
    db.create_all()

    # Create default users only if not exists
    if not User.query.first():
        db.session.add(User(username="manager", password="1234", role="manager"))
        db.session.add(User(username="cashier", password="1234", role="cashier"))
        db.session.commit()


# ------------------- HELPERS -------------------

def current_month_range():
    now = datetime.now()
    first = datetime(now.year, now.month, 1)
    last_day = calendar.monthrange(now.year, now.month)[1]
    last = datetime(now.year, now.month, last_day, 23, 59, 59)
    return first, last


def get_month_sales():
    start, end = current_month_range()
    return Sale.query.filter(Sale.timestamp >= start, Sale.timestamp <= end)


# fixed monthly expenses
MONTHLY_EXPENSES = {
    "Electricity": 6000,
    "Water": 1000,
    "Rent": 25000,
    "BIR tax": 900,
    "Municipality": 1000,
}


# ------------------- AUTH -------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        user = User.query.filter_by(username=username, password=password, role=role).first()

        if not user:
            flash("Invalid credentials", "danger")
            return redirect(url_for("login"))

        session["user"] = user.username
        session["role"] = user.role

        if role == "manager":
            return redirect(url_for("manager_panel"))
        return redirect(url_for("cashier_panel"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------- MANAGER PANEL -------------------

@app.route("/manager")
def manager_panel():
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    items = Item.query.all()
    sales = get_month_sales().all()

    # income & profit
    total_sales_amount = sum(s.selling_price * s.quantity for s in sales)
    total_cost = sum(s.item.capital_per_unit * s.quantity for s in sales)
    expenses_total = sum(MONTHLY_EXPENSES.values())

    total_profit = total_sales_amount - total_cost - expenses_total

    return render_template(
        "manager.html",
        items=items,
        sales=sales,
        expenses=MONTHLY_EXPENSES,
        expenses_total=expenses_total,
        total_sales_amount=total_sales_amount,
        total_profit=total_profit,
    )


@app.route("/manager/add_item", methods=["POST"])
def add_item():
    item = Item(
        name=request.form["name"],
        stock=int(request.form["stock"]),
        capital_per_unit=float(request.form["capital"]),
        selling_price=float(request.form["price"]),
        cashier_bonus=float(request.form["bonus"])
    )
    db.session.add(item)
    db.session.commit()
    return redirect(url_for("manager_panel"))


@app.route("/manager/delete_sale/<int:sale_id>")
def delete_sale(sale_id):
    if session.get("role") != "manager":
        return redirect(url_for("login"))

    sale = Sale.query.get_or_404(sale_id)

    # restore stock
    sale.item.stock += sale.quantity

    db.session.delete(sale)
    db.session.commit()

    flash("Sale removed and bonus undone.", "warning")
    return redirect(url_for("manager_panel"))


# ------------------- CASHIER PANEL -------------------

@app.route("/cashier")
def cashier_panel():
    if session.get("role") != "cashier":
        return redirect(url_for("login"))

    items = Item.query.all()

    sales = get_month_sales().filter_by(cashier_name=session["user"]).all()

    total_bonus = sum(s.cashier_bonus * s.quantity for s in sales)

    return render_template(
        "cashier.html",
        items=items,
        sales=sales,
        total_bonus=total_bonus,
    )


@app.route("/cashier/sell", methods=["POST"])
def cashier_sell():
    if session.get("role") != "cashier":
        return redirect(url_for("login"))

    item = Item.query.get(int(request.form["item_id"]))
    qty = int(request.form["quantity"])

    if qty > item.stock:
        flash("Not enough stock.", "danger")
        return redirect(url_for("cashier_panel"))

    item.stock -= qty

    sale = Sale(
        item_id=item.id,
        quantity=qty,
        selling_price=item.selling_price,
        cashier_bonus=item.cashier_bonus,
        cashier_name=session["user"],
    )

    db.session.add(sale)
    db.session.commit()

    flash("Sale recorded.", "success")
    return redirect(url_for("cashier_panel"))


if __name__ == "__main__":
    app.run(debug=True)
