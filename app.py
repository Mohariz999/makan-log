"""Makan Log: rate hawker dishes. Flask + SQLAlchemy, PostgreSQL in production, SQLite locally."""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

import click
from dotenv import load_dotenv
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFProtect
from sqlalchemy import func

load_dotenv()
db = SQLAlchemy()
migrate = Migrate()
csrf = CSRFProtect()

SORTS = {"rating": "Top rated", "price": "Cheapest", "newest": "Newest"}


class Stall(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    hawker_centre = db.Column(db.String(120), nullable=False)
    cuisine = db.Column(db.String(60), nullable=False)
    dishes = db.relationship("Dish", back_populates="stall", cascade="all, delete-orphan")
    __table_args__ = (db.UniqueConstraint("name", "hawker_centre", name="uq_stall_name_centre"),)


class Dish(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    stall_id = db.Column(db.Integer, db.ForeignKey("stall.id"), nullable=False, index=True)
    name = db.Column(db.String(120), nullable=False)
    price = db.Column(db.Numeric(6, 2), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.String(300))
    created_at = db.Column(db.DateTime(timezone=True), nullable=False,
                           default=lambda: datetime.now(timezone.utc))
    stall = db.relationship("Stall", back_populates="dishes")
    __table_args__ = (db.CheckConstraint("rating BETWEEN 1 AND 5", name="ck_dish_rating"),
                      db.CheckConstraint("price >= 0", name="ck_dish_price"))

    def to_dict(self):
        return {"id": self.id, "dish": self.name, "price": float(self.price), "rating": self.rating,
                "notes": self.notes, "stall": self.stall.name, "hawker_centre": self.stall.hawker_centre,
                "cuisine": self.stall.cuisine, "created_at": self.created_at.isoformat()}


def database_url():
    """DATABASE_URL from the environment, normalised for SQLAlchemy's psycopg 3 driver."""
    url = os.getenv("DATABASE_URL", "sqlite:///makan.db")
    # Hosted Postgres providers hand out postgres:// or postgresql:// URLs.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def filtered_dishes(args):
    """Dish query with the hawker centre / max price / sort filters shared by the page and the API."""
    query = Dish.query.join(Stall)
    if args.get("centre"):
        query = query.filter(Stall.hawker_centre == args["centre"])
    if args.get("max_price"):
        try:
            query = query.filter(Dish.price <= Decimal(args["max_price"]))
        except InvalidOperation:
            abort(400, "max_price must be a number.")
    sort = args.get("sort", "rating")
    order = {"price": (Dish.price.asc(), Dish.rating.desc()),
             "newest": (Dish.created_at.desc(), Dish.id.desc())}.get(sort, (Dish.rating.desc(), Dish.price.asc()))
    return query.order_by(*order)


def stall_leaderboard(limit=5):
    """Stalls ranked by average dish rating: a GROUP BY with aggregates."""
    average = func.avg(Dish.rating).label("average_rating")
    return (db.session.query(Stall, average, func.count(Dish.id).label("dish_count"))
            .join(Dish).group_by(Stall.id)
            .order_by(average.desc(), func.count(Dish.id).desc(), Stall.name)
            .limit(limit).all())


def parse_dish_form(form):
    """Validate the add-dish form; returns cleaned values or raises ValueError."""
    values = {key: (form.get(key) or "").strip() for key in
              ("stall", "hawker_centre", "cuisine", "dish", "price", "rating", "notes")}
    for key in ("stall", "hawker_centre", "cuisine", "dish"):
        if not values[key]:
            raise ValueError("Please fill in the stall, hawker centre, cuisine and dish.")
    try:
        values["price"] = Decimal(values["price"]).quantize(Decimal("0.01"))
    except InvalidOperation:
        raise ValueError("Price must be a number, like 4.50.")
    if not Decimal("0") <= values["price"] <= Decimal("100"):
        raise ValueError("Price must be between $0 and $100.")
    if values["rating"] not in {"1", "2", "3", "4", "5"}:
        raise ValueError("Rating must be 1 to 5.")
    values["rating"] = int(values["rating"])
    values["notes"] = values["notes"][:300] or None
    return values


def add_dish(values):
    stall = Stall.query.filter_by(name=values["stall"], hawker_centre=values["hawker_centre"]).first()
    if not stall:
        stall = Stall(name=values["stall"], hawker_centre=values["hawker_centre"], cuisine=values["cuisine"])
        db.session.add(stall)
    dish = Dish(stall=stall, name=values["dish"], price=values["price"], rating=values["rating"],
                notes=values["notes"])
    db.session.add(dish)
    db.session.commit()
    return dish


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=database_url(),
                      SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
                      SECRET_KEY=os.getenv("SECRET_KEY") or secrets.token_hex(32))
    if test_config:
        app.config.update(test_config)
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    app.json.compact = False  # indented JSON, readable when the API is opened in a browser

    @app.template_filter("sgd")
    def sgd(value):
        return f"${Decimal(str(value)):,.2f}"

    @app.get("/")
    def index():
        dishes = filtered_dishes(request.args).all()
        centres = [row[0] for row in db.session.query(Stall.hawker_centre).distinct().order_by(Stall.hawker_centre)]
        return render_template("index.html", dishes=dishes, leaderboard=stall_leaderboard(), centres=centres,
                               sorts=SORTS, filters=request.args,
                               api_filters={key: value for key, value in request.args.items() if value})

    @app.route("/dishes/new", methods=["GET", "POST"])
    def new_dish():
        if request.method == "POST":
            try:
                dish = add_dish(parse_dish_form(request.form))
                flash(f"Added {dish.name} from {dish.stall.name}.", "success")
                return redirect(url_for("index", sort="newest"))
            except ValueError as error:
                flash(str(error), "danger")
                return render_template("new_dish.html", form=request.form), 400
        return render_template("new_dish.html", form={})

    @app.get("/api/dishes")
    def api_dishes():
        return jsonify([dish.to_dict() for dish in filtered_dishes(request.args).limit(200)])

    @app.get("/api/stalls/top")
    def api_top_stalls():
        return jsonify([{"stall": stall.name, "hawker_centre": stall.hawker_centre,
                         "average_rating": round(float(average), 2), "dishes": count}
                        for stall, average, count in stall_leaderboard()])

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.cli.command("seed")
    @click.option("--count", default=12, show_default=True, help="How many random dishes to add.")
    def seed_command(count):
        """Add random starter dishes, only if the database is empty."""
        from seed import seed_random_dishes
        added = seed_random_dishes(count)
        click.echo(f"Seeded {added} dishes." if added else "Database already has dishes; nothing seeded.")

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
