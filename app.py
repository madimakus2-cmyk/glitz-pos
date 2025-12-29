import os
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
app.secret_key = "secret-key"

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///" + os.path.join(BASE_DIR, "database.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ------------------ MODELS ------------------

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True)
    password = db.Column(db.String(80))
    role = db.Column(db.String(20))   # manager or cashier
    bonus_total = db.Column(db.Float, default=0.0)


class Item(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120))
    stock = db.Column(db.Integer)
    capital_per_unit = db.Column(db.Float)
    selling_price = db.Column(db.Float)
    cashier_bonus = db.Column(db.Float)   # bonus per unit sold to cashier


class Sale(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(db.Integer, db.ForeignKey("item.id"))
    qty = db.Column(db.Integer)
    total_price = db.Column(db.Float)
    profit = db.Column(db.Float)
    bonus_given = db.Column(db.Float)
    cashier_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)

    item = db.relationship("Item")
    cashier = db.relationship("User")


# ------------------ LOGIN ------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        user = User.query.filter_by(username=username, password=password).first()

        if not user:
            flash("Invalid credentials", "error")
            return redirect(url_for("login"))

        session["user_id"] = user.id
        session["role"] = user.role

        if user.role == "manager":
            return redirect(url_for("manager_panel"))
        return redirect(url_for("cashier_panel"))

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ------------------ CASHIER PANEL ------------------

@app.route("/cashier", methods=["GET", "POST"])
def cashier_panel():
    if "role" not in session or session["role"] != "cashier":
        return redirect(url_for("login"))

    items = Item.query.all()

    if request.method == "POST":
        item_id = int(request.form["item"])
        qty = int(request.form["qty"])

        item = Item.query.get(item_id)

        if qty > item.stock:
            flash("Not enough stock", "error")
            return redirect(url_for("cashier_panel"))

        cashier = User.query.get(session["user_id"])

        total_price = item.selling_price * qty
        profit = (item.selling_price - item.capital_per_unit) * qty
        bonus = item.cashier_bonus * qty

        # record sale
        sale = Sale(
            item_id=item.id,
            qty=qty,
            total_price=total_price,
            profit=profit,
            bonus_given=bonus,
            cashier_id=cashier.id
        )

        item.stock -= qty
        cashier.bonus_total += bonus

        db.session.add(sale)
        db.session.commit()

        flash("Sale recorded", "success")

    return render_template("cashier.html", items=items)


# ------------------ MANAGER PANEL ------------------

@app.route("/manager")
def manager_panel():
    if "role" not in session or session["role"] != "manager":
        return redirect(url_for("login"))

    items = Item.query.all()
    sales = Sale.query.order_by(Sale.timestamp.desc()).all()
    users = User.query.all()

    total_profit = sum(s.profit for s in sales)

    return render_template(
        "manager.html",
        items=items,
        sales=sales,
        users=users,
        total_profit=total_profit,
    )


# ----------- DELETE SALE (MANAGER ONLY) ------------

@app.route("/delete_sale/<int:sale_id>", methods=["POST"])
def delete_sale(sale_id):
    if "role" not in session or session["role"] != "manager":
        return redirect(url_for("login"))

    sale = Sale.query.get_or_404(sale_id)

    # restore stock
    sale.item.stock += sale.qty

    # remove cashier bonus that was given for this sale
    if sale.cashier:
        sale.cashier.bonus_total -= sale.bonus_given
        if sale.cashier.bonus_total < 0:
            sale.cashier.bonus_total = 0

    db.session.delete(sale)
    db.session.commit()

    flash("Sale deleted and bonuses corrected.", "success")
    return redirect(url_for("manager_panel"))


# ------------------ DB AUTO CREATE ------------------

with app.app_context():
    db.create_all()

    # default users
    if not User.query.filter_by(username="manager").first():
        db.session.add(User(username="manager", password="manager", role="manager"))

    if not User.query.filter_by(username="cashier").first():
        db.session.add(User(username="cashier", password="cashier", role="cashier"))

    db.session.commit()


# ------------------ RUN ------------------

if __name__ == "__main__":
    app.run(debug=True)
