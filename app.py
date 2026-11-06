import os, re, sqlite3, uuid
from functools import wraps
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, "database.db")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
os.makedirs(UPLOAD_DIR, exist_ok=True)

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key-before-deployment")
app.config["MAX_CONTENT_LENGTH"] = 5 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = UPLOAD_DIR

SHOP_NAME = "MMS Textiles"
PHONE = "9952367070"
WHATSAPP = "919952367070"
ADDRESS = "Tenkasi Main Road, Opposite Union Office, Alangulam, Tamil Nadu"
MAP_URL = "https://maps.app.goo.gl/ugC1J7CQnJat5quJ7"
INSTAGRAM_URL = "https://www.instagram.com/m.m.s_textiles?vrfl=bjNmNXV4YnViNHA5"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS categories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category_id INTEGER,
            price REAL NOT NULL DEFAULT 0,
            description TEXT DEFAULT '',
            image TEXT DEFAULT '',
            featured INTEGER DEFAULT 0,
            new_arrival INTEGER DEFAULT 0,
            available INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(category_id) REFERENCES categories(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS offers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            active INTEGER DEFAULT 1
        );
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            address TEXT DEFAULT '',
            items TEXT NOT NULL,
            status TEXT DEFAULT 'Enquiry Received',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        );
        """)
        count = db.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
        if count == 0:
            names = ["Sarees", "Silk Sarees", "Cotton Sarees", "Men's Shirts", "Men's Pants",
                     "Innerwear", "Chudidhar", "Salwar", "Women's Dress Materials",
                     "Towels", "Trousers", "Shorts", "Tracks", "Kids' Wear"]
            db.executemany("INSERT INTO categories(name) VALUES(?)", [(n,) for n in names])
        if db.execute("SELECT COUNT(*) FROM admins").fetchone()[0] == 0:
            username = os.environ.get("ADMIN_USERNAME", "admin")
            password = os.environ.get("ADMIN_PASSWORD", "ChangeMe123!")
            db.execute("INSERT INTO admins(username,password_hash) VALUES(?,?)",
                       (username, generate_password_hash(password)))
        if db.execute("SELECT COUNT(*) FROM offers").fetchone()[0] == 0:
            db.execute("INSERT INTO offers(title,description,active) VALUES(?,?,1)",
                       ("Discover Our Collections", "Beautiful choices for every occasion and every generation."))
init_db()

CATEGORY_IMG_DIR = os.path.join(BASE_DIR, "static", "images", "categories")

def category_image(name):
    """Photo for a category: static/images/categories/<slug>.jpg|jpeg|png|webp,
    falling back to the built-in illustration <slug>.svg, then default.svg."""
    slug = re.sub(r"[^a-z0-9]+", "-", (name or "").lower().replace("'", "")).strip("-")
    for ext in ("jpg", "jpeg", "png", "webp", "svg"):
        if os.path.isfile(os.path.join(CATEGORY_IMG_DIR, f"{slug}.{ext}")):
            return url_for("static", filename=f"images/categories/{slug}.{ext}")
    return url_for("static", filename="images/categories/default.svg")

@app.context_processor
def inject_globals():
    return dict(shop_name=SHOP_NAME, phone=PHONE, whatsapp=WHATSAPP, address=ADDRESS,
                map_url=MAP_URL, instagram_url=INSTAGRAM_URL, category_image=category_image)

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("admin_id"):
            return redirect(url_for("admin_login", next=request.path))
        return fn(*args, **kwargs)
    return wrapper

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def save_image(file):
    if not file or not file.filename:
        return None
    if not allowed_file(file.filename):
        raise ValueError("Please upload a JPG, PNG or WEBP image.")
    ext = secure_filename(file.filename).rsplit(".", 1)[1].lower()
    filename = f"{uuid.uuid4().hex}.{ext}"
    file.save(os.path.join(UPLOAD_DIR, filename))
    return filename

@app.route("/")
def home():
    with get_db() as db:
        categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
        featured = db.execute("""SELECT p.*, c.name AS category_name FROM products p
            LEFT JOIN categories c ON c.id=p.category_id WHERE p.available=1 AND p.featured=1
            ORDER BY p.created_at DESC LIMIT 8""").fetchall()
        latest = db.execute("""SELECT p.*, c.name AS category_name FROM products p
            LEFT JOIN categories c ON c.id=p.category_id WHERE p.available=1
            ORDER BY p.created_at DESC LIMIT 8""").fetchall()
        offers = db.execute("SELECT * FROM offers WHERE active=1 ORDER BY id DESC").fetchall()
    return render_template("index.html", categories=categories, featured=featured, latest=latest, offers=offers)

@app.route("/about")
def about():
    return render_template("about.html")

@app.route("/products")
def products():
    q = request.args.get("q", "").strip()
    category_id = request.args.get("category", "").strip()
    sort = request.args.get("sort", "newest")
    sql = """SELECT p.*, c.name AS category_name FROM products p
             LEFT JOIN categories c ON c.id=p.category_id WHERE p.available=1"""
    params = []
    if q:
        sql += " AND (p.name LIKE ? OR p.description LIKE ? OR c.name LIKE ?)"
        params += [f"%{q}%"] * 3
    if category_id.isdigit():
        sql += " AND p.category_id=?"
        params.append(int(category_id))
    sql += " ORDER BY p.price ASC" if sort == "low" else (" ORDER BY p.price DESC" if sort == "high" else " ORDER BY p.created_at DESC")
    with get_db() as db:
        items = db.execute(sql, params).fetchall()
        categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template("products.html", products=items, categories=categories, q=q, selected_category=category_id, sort=sort)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    with get_db() as db:
        product = db.execute("""SELECT p.*, c.name AS category_name FROM products p
            LEFT JOIN categories c ON c.id=p.category_id WHERE p.id=? AND p.available=1""",
            (product_id,)).fetchone()
        if not product:
            abort(404)
        related = db.execute("""SELECT * FROM products WHERE available=1 AND category_id=?
            AND id<>? ORDER BY created_at DESC LIMIT 4""", (product["category_id"], product_id)).fetchall()
    return render_template("product_detail.html", product=product, related=related)

@app.route("/contact")
def contact():
    return render_template("contact.html")

@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        with get_db() as db:
            admin = db.execute("SELECT * FROM admins WHERE username=?", (username,)).fetchone()
        if admin and check_password_hash(admin["password_hash"], password):
            session.clear()
            session["admin_id"] = admin["id"]
            session["admin_username"] = admin["username"]
            return redirect(url_for("admin_dashboard"))
        flash("Incorrect username or password.", "error")
    return render_template("admin/login.html")

@app.route("/admin/logout")
def admin_logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/admin")
@admin_required
def admin_dashboard():
    with get_db() as db:
        stats = {
            "products": db.execute("SELECT COUNT(*) FROM products").fetchone()[0],
            "categories": db.execute("SELECT COUNT(*) FROM categories").fetchone()[0],
            "orders": db.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
            "offers": db.execute("SELECT COUNT(*) FROM offers WHERE active=1").fetchone()[0]
        }
        recent_orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC LIMIT 6").fetchall()
    return render_template("admin/dashboard.html", stats=stats, orders=recent_orders)

@app.route("/admin/products")
@admin_required
def admin_products():
    with get_db() as db:
        items = db.execute("""SELECT p.*, c.name AS category_name FROM products p
            LEFT JOIN categories c ON c.id=p.category_id ORDER BY p.created_at DESC""").fetchall()
    return render_template("admin/products.html", products=items)

@app.route("/admin/products/add", methods=["GET", "POST"])
@admin_required
def add_product():
    with get_db() as db:
        categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if request.method == "POST":
        try:
            image = save_image(request.files.get("image")) or ""
            with get_db() as db:
                db.execute("""INSERT INTO products(name,category_id,price,description,image,featured,new_arrival,available)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (request.form["name"].strip(), request.form.get("category_id") or None,
                     float(request.form.get("price") or 0), request.form.get("description", "").strip(),
                     image, int(request.form.get("featured") == "on"),
                     int(request.form.get("new_arrival") == "on"), int(request.form.get("available") == "on")))
            flash("Product added successfully.", "success")
            return redirect(url_for("admin_products"))
        except (ValueError, KeyError) as e:
            flash(str(e) or "Please check the product details.", "error")
    return render_template("admin/product_form.html", categories=categories, product=None)

@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def edit_product(product_id):
    with get_db() as db:
        product = db.execute("SELECT * FROM products WHERE id=?", (product_id,)).fetchone()
        categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    if not product:
        abort(404)
    if request.method == "POST":
        try:
            new_image = save_image(request.files.get("image"))
            image = new_image or product["image"]
            with get_db() as db:
                db.execute("""UPDATE products SET name=?,category_id=?,price=?,description=?,image=?,
                    featured=?,new_arrival=?,available=? WHERE id=?""",
                    (request.form["name"].strip(), request.form.get("category_id") or None,
                     float(request.form.get("price") or 0), request.form.get("description", "").strip(),
                     image, int(request.form.get("featured") == "on"),
                     int(request.form.get("new_arrival") == "on"), int(request.form.get("available") == "on"),
                     product_id))
            flash("Product updated successfully.", "success")
            return redirect(url_for("admin_products"))
        except (ValueError, KeyError) as e:
            flash(str(e) or "Please check the product details.", "error")
    return render_template("admin/product_form.html", categories=categories, product=product)

@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def delete_product(product_id):
    with get_db() as db:
        product = db.execute("SELECT image FROM products WHERE id=?", (product_id,)).fetchone()
        db.execute("DELETE FROM products WHERE id=?", (product_id,))
    if product and product["image"]:
        path = os.path.join(UPLOAD_DIR, product["image"])
        if os.path.isfile(path):
            os.remove(path)
    flash("Product deleted.", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    with get_db() as db:
        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if name:
                try:
                    db.execute("INSERT INTO categories(name) VALUES(?)", (name,))
                    flash("Category added.", "success")
                except sqlite3.IntegrityError:
                    flash("That category already exists.", "error")
            return redirect(url_for("admin_categories"))
        categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template("admin/categories.html", categories=categories)

@app.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
@admin_required
def delete_category(category_id):
    with get_db() as db:
        db.execute("DELETE FROM categories WHERE id=?", (category_id,))
    flash("Category deleted. Products in this category are now uncategorized.", "success")
    return redirect(url_for("admin_categories"))

@app.route("/admin/orders", methods=["GET", "POST"])
@admin_required
def admin_orders():
    statuses = ["Enquiry Received", "Order Confirmed", "Processing", "Dispatched", "Delivered", "Cancelled"]
    with get_db() as db:
        if request.method == "POST":
            db.execute("""INSERT INTO orders(customer_name,phone,address,items,status)
                VALUES(?,?,?,?,?)""",
                (request.form["customer_name"].strip(), request.form["phone"].strip(),
                 request.form.get("address", "").strip(), request.form["items"].strip(),
                 request.form.get("status", statuses[0])))
            flash("Order/enquiry record added.", "success")
            return redirect(url_for("admin_orders"))
        orders = db.execute("SELECT * FROM orders ORDER BY created_at DESC").fetchall()
    return render_template("admin/orders.html", orders=orders, statuses=statuses)

@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def update_order_status(order_id):
    status = request.form.get("status", "Enquiry Received")
    allowed = ["Enquiry Received", "Order Confirmed", "Processing", "Dispatched", "Delivered", "Cancelled"]
    if status not in allowed:
        abort(400)
    with get_db() as db:
        db.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
    flash("Order status updated.", "success")
    return redirect(url_for("admin_orders"))

@app.route("/admin/offers", methods=["GET", "POST"])
@admin_required
def admin_offers():
    with get_db() as db:
        if request.method == "POST":
            db.execute("INSERT INTO offers(title,description,active) VALUES(?,?,1)",
                       (request.form["title"].strip(), request.form.get("description", "").strip()))
            flash("Offer added.", "success")
            return redirect(url_for("admin_offers"))
        offers = db.execute("SELECT * FROM offers ORDER BY id DESC").fetchall()
    return render_template("admin/offers.html", offers=offers)

@app.route("/admin/offers/<int:offer_id>/toggle", methods=["POST"])
@admin_required
def toggle_offer(offer_id):
    with get_db() as db:
        db.execute("UPDATE offers SET active=1-active WHERE id=?", (offer_id,))
    return redirect(url_for("admin_offers"))

@app.route("/admin/offers/<int:offer_id>/delete", methods=["POST"])
@admin_required
def delete_offer(offer_id):
    with get_db() as db:
        db.execute("DELETE FROM offers WHERE id=?", (offer_id,))
    return redirect(url_for("admin_offers"))

@app.errorhandler(404)
def not_found(error):
    return render_template("404.html"), 404

if __name__ == "__main__":
    app.run(debug=True)
