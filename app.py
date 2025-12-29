import sqlite3
from flask import Flask, render_template, request, redirect, session, g

app = Flask(__name__)
app.secret_key = "super-secret-key"


# -----------------------
# DB UTILITIES
# -----------------------
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect("pos.db")
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    db = get_db()

    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password TEXT,
            role TEXT
        );

        CREATE TABLE IF NOT EXISTS inventory (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            price REAL,
            stock INTEGER
        );

        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashier TEXT,
            item TEXT,
            quantity INTEGER,
            total REAL,
            deleted INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS bonuses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cashier TEXT,
            sale_id INTEGER,
            amount REAL,
            active INTEGER DEFAULT 1
        );
        """
    )

    # seed manager if missing
    cur = db.execute("SELECT 1 FROM users WHERE username=?", ("manager",))
    if not cur.fetchone():
        db.execute(
            "INSERT INTO users(username,password,role) VALUES (?,?,?)",
            ("manager", "admin123", "manager"),
        )

    db.commit()


with app.app_context():
    init_db()


# -----------------------
# AUTH
# -----------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        db = get_db()
        user = db.execute(
            "SELECT * FROM users WHERE username=? AND password=?",
            (username, password),
        ).fetchone()

        if user:
            session["user"] = username
            session["role"] = user["role"]

            if user["role"] == "manager":
                return redirect("/manager")
            return redirect("/cashier")

        return "Invalid credentials"

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# -----------------------
# CASHIER
# -----------------------
@app.route("/cashier", methods=["GET", "POST"])
def cashier():
    if "role" not in session or session["role"] != "cashier":
        return redirect("/login")

    db = get_db()
    inventory = db.execute("SELECT * FROM inventory").fetchall()

    if request.method == "POST":
        item_id = request.form["item_id"]
        qty = int(request.form["quantity"])

        item = db.execute("SELECT * FROM inventory WHERE id=?", (item_id,)).fetchone()
        if not item or item["stock"] < qty:
            return "Not enough stock"

        total = item["price"] * qty

        # record sale
        db.execute(
            "INSERT INTO sales(cashier,item,quantity,total) VALUES (?,?,?,?)",
            (session["user"], item["name"], qty, total),
        )
        sale_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        # cashier bonus (example: 5% of sale)
        bonus_amount = round(total * 0.05, 2)
        db.execute(
            "INSERT INTO bonuses(cashier,sale_id,amount) VALUES (?,?,?)",
            (session["user"], sale_id, bonus_amount),
        )

        # update stock
        db.execute(
            "UPDATE inventory SET stock = stock - ? WHERE id=?",
            (qty, item_id),
        )

        db.commit()

        return redirect("/cashier")

    return render_template("cashier.html", inventory=inventory)


# -----------------------
# MANAGER PANEL
# -----------------------
@app.route("/manager")
def manager_panel():
    if "role" not in session or session["role"] != "manager":
        return redirect("/login")

    db = get_db()

    sales = db.execute(
        "SELECT * FROM sales ORDER BY id DESC"
    ).fetchall()

    inventory = db.execute("SELECT * FROM inventory").fetchall()

    total_sales = db.execute(
        "SELECT COALESCE(SUM(total),0) FROM sales WHERE deleted=0"
    ).fetchone()[0]

    # total bonuses currently active
    total_bonuses = db.execute(
        "SELECT COALESCE(SUM(amount),0) FROM bonuses WHERE active=1"
    ).fetchone()[0]

    total_profit = round(total_sales - total_bonuses, 2)

    # 👇 prevents your previous crash
    expenses = {}

    return render_template(
        "manager.html",
        sales=sales,
        inventory=inventory,
        total_sales=total_sales,
        total_profit=total_profit,
        expenses=expenses,
    )


# -----------------------
# DELETE (UNDO) A SALE
# -----------------------
@app.route("/delete_sale/<int:sale_id>", methods=["POST"])
def delete_sale(sale_id):
    if "role" not in session or session["role"] != "manager":
        return redirect("/login")

    db = get_db()

    sale = db.execute("SELECT * FROM sales WHERE id=?", (sale_id,)).fetchone()
    if not sale or sale["deleted"] == 1:
        return redirect("/manager")

    # mark sale deleted
    db.execute("UPDATE sales SET deleted=1 WHERE id=?", (sale_id,))

    # restore inventory
    db.execute(
        "UPDATE inventory SET stock = stock + ? WHERE name=?",
        (sale["quantity"], sale["item"]),
    )

    # cancel cashier bonus
    db.execute(
        "UPDATE bonuses SET active=0 WHERE sale_id=?",
        (sale_id,),
    )

    db.commit()

    return redirect("/manager")


if __name__ == "__main__":
    app.run(debug=True)
