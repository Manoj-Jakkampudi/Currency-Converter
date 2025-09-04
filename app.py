# app.py
from flask import Flask, render_template, request, redirect, url_for, session, flash, g
import sqlite3
import os
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
# Use an environment variable for SECRET_KEY in production, fallback to a dev key
app.secret_key = os.environ.get("SECRET_KEY", "your_super_secret_key_here") # IMPORTANT: Change this in production!


BASE_DIR = os.path.dirname(__file__)
DB_PATH = os.path.join(BASE_DIR, "users.db")

# ---------------- DB helpers ----------------
def get_db():
    """
    Establishes a database connection or returns the existing one.
    Uses Flask's `g` object to store the connection for the current request.
    """
    if "db" not in g:
        # timeout gives SQLite a short wait if DB briefly locked
        # check_same_thread=False is needed for SQLite in multi-threaded environments (like Flask's dev server)
        g.db = sqlite3.connect(DB_PATH, timeout=15, check_same_thread=False)
        g.db.row_factory = sqlite3.Row # Allows accessing columns by name
    return g.db

@app.teardown_appcontext
def close_db(exc):
    """Closes the database connection at the end of the request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """
    Initializes the database. Creates the users table if it doesn't exist
    and enables WAL mode for better concurrency.
    """
    conn = sqlite3.connect(DB_PATH)
    try:
        # Enable WAL (Write-Ahead Logging) to reduce locking issues
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL
            );
        """)
        conn.commit()
    finally:
        conn.close()

# Initialize DB at application startup
init_db()

# ---------------- Static currency data (offline) ----------------
# These rates are static and for demonstration. In a real app, you'd fetch them from an API.
CURRENCY_RATES = {
    "USD": 1.00,
    "EUR": 0.92,
    "GBP": 0.78,
    "INR": 83.00,
    "JPY": 146.00,
    "AUD": 1.52,
    "CAD": 1.36,
    "CNY": 7.25,
    "SGD": 1.34,
    "AED": 3.67,
    "CHF": 0.90, # Swiss Franc
    "NZD": 1.65, # New Zealand Dollar
    "ZAR": 18.50, # South African Rand
    "BRL": 5.20, # Brazilian Real
    "RUB": 90.00 # Russian Ruble
}
CURRENCY_CODES = sorted(list(CURRENCY_RATES.keys())) # Sorted for display

# ---------------- Routes ----------------
@app.route("/")
def root():
    """Redirects to the converter page if logged in, otherwise to login."""
    if "username" in session:
        return redirect(url_for("converter"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    """Handles user registration."""
    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Please fill both username and password.", "warning")
            return redirect(url_for("register"))

        db = get_db()
        # Check if username already exists
        row = db.execute("SELECT 1 FROM users WHERE username = ?", (username,)).fetchone()
        if row:
            flash("⚠️ Username already exists. Choose another.", "danger")
            return redirect(url_for("register"))

        # Hash the password before storing it
        hashed_password = generate_password_hash(password)
        try:
            db.execute("INSERT INTO users (username, password) VALUES (?, ?)", (username, hashed_password))
            db.commit()
        except sqlite3.IntegrityError:
            # This catch is for extremely rare race conditions where username is created between check and insert
            flash("⚠️ Username already exists. Choose another.", "danger")
            return redirect(url_for("register"))

        flash("✅ Successfully registered! Please login.", "success")
        # Redirect to login with a flag to show a specific message
        return redirect(url_for("login", registered=1))

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    """Handles user login."""
    # Check if the 'registered' query parameter is present
    registered_flag = request.args.get("registered") == "1"

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Please enter both username and password.", "warning")
            return redirect(url_for("login"))

        db = get_db()
        user = db.execute("SELECT id, username, password FROM users WHERE username = ?", (username,)).fetchone()

        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            flash(f"Welcome, {user['username']}!", "success")
            return redirect(url_for("converter"))
        else:
            flash("❌ Invalid username or password.", "danger")
            return redirect(url_for("login"))

    return render_template("login.html", registered=registered_flag)

@app.route("/converter", methods=["GET", "POST"])
def converter():
    """
    Handles the currency conversion logic.
    Requires user to be logged in.
    """
    if "username" not in session:
        flash("Please login first to access the converter.", "warning")
        return redirect(url_for("login"))

    result = None
    # Store form values to pre-fill selects if conversion fails
    selected_from_cur = request.form.get("from_currency", "USD")
    selected_to_cur = request.form.get("to_currency", "EUR")
    input_amount = request.form.get("amount", "")

    if request.method == "POST":
        try:
            amount = float(input_amount)
            from_cur = selected_from_cur
            to_cur = selected_to_cur

            if amount <= 0:
                flash("Amount must be a positive number.", "warning")
                return render_template("index.html",
                                       currencies=CURRENCY_CODES,
                                       result=None,
                                       username=session.get("username"),
                                       selected_from_cur=selected_from_cur,
                                       selected_to_cur=selected_to_cur,
                                       input_amount=input_amount)

            if from_cur not in CURRENCY_RATES or to_cur not in CURRENCY_RATES:
                flash("Invalid currency selected.", "danger")
                return render_template("index.html",
                                       currencies=CURRENCY_CODES,
                                       result=None,
                                       username=session.get("username"),
                                       selected_from_cur=selected_from_cur,
                                       selected_to_cur=selected_to_cur,
                                       input_amount=input_amount)

            # Convert to USD first
            usd_amount = amount / CURRENCY_RATES[from_cur]
            # Then convert from USD to target currency
            converted_amount = round(usd_amount * CURRENCY_RATES[to_cur], 2)

            result = f"{amount:.2f} {from_cur} = {converted_amount:.2f} {to_cur}"
            flash("Conversion successful!", "success")

        except ValueError:
            flash("Amount must be a valid number.", "danger")
        except Exception as e:
            flash(f"An unexpected error occurred: {e}", "danger")

    return render_template("index.html",
                           currencies=CURRENCY_CODES,
                           result=result,
                           username=session.get("username"),
                           selected_from_cur=selected_from_cur,
                           selected_to_cur=selected_to_cur,
                           input_amount=input_amount)

@app.route("/logout")
def logout():
    """Logs out the user by clearing the session."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("login"))

@app.route("/privacy")
def privacy():
    """Displays the Privacy Policy page."""
    return render_template("privacy.html")

@app.route("/terms")
def terms():
    """Displays the Terms of Service page."""
    return render_template("terms.html")

@app.route("/contact")
def contact():
    """Displays the Contact page."""
    return render_template("contact.html")

# Run the application
if __name__ == "__main__":
    # For production deployment, use environment variables
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
