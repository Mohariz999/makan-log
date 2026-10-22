import random
from decimal import Decimal

import pytest

from app import Dish, Stall, add_dish, create_app, database_url, db, parse_dish_form, stall_leaderboard
from seed import seed_random_dishes


@pytest.fixture()
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://", "WTF_CSRF_ENABLED": False})
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()


def dish(stall="Ah Seng", centre="Maxwell Food Centre", name="Chicken rice", price="4.50", rating="4"):
    return {"stall": stall, "hawker_centre": centre, "cuisine": "Chinese", "dish": name,
            "price": price, "rating": rating}


def test_app_initialises_with_health_check(client):
    assert client.get("/health").json == {"status": "ok"}


def test_index_returns_200(client):
    assert client.get("/").status_code == 200


def test_index_api_link_keeps_current_filters(client):
    html = client.get("/?centre=Maxwell+Food+Centre&max_price=&sort=price").get_data(as_text=True)
    assert "/api/dishes?centre=Maxwell+Food+Centre&amp;sort=price" in html


def test_adding_a_dish_saves_it_and_reuses_the_stall(app, client):
    response = client.post("/dishes/new", data=dish())
    assert response.status_code == 302
    client.post("/dishes/new", data=dish(name="Roasted chicken rice"))
    assert Stall.query.count() == 1
    assert Dish.query.count() == 2
    assert b"Roasted chicken rice" in client.get("/").data


@pytest.mark.parametrize("bad, message", [
    ({"price": "abc"}, b"Price must be a number"),
    ({"price": "150"}, b"between $0 and $100"),
    ({"rating": "9"}, b"Rating must be 1 to 5"),
    ({"dish": ""}, b"Please fill in"),
])
def test_invalid_dish_is_rejected(client, bad, message):
    response = client.post("/dishes/new", data={**dish(), **bad})
    assert response.status_code == 400 and message in response.data
    assert Dish.query.count() == 0


def test_parse_dish_form_cleans_values():
    values = parse_dish_form({**dish(price="4.5"), "notes": "  "})
    assert values["price"] == Decimal("4.50") and values["rating"] == 4 and values["notes"] is None


def test_api_filters_by_centre_and_price_and_sorts(client):
    for values in (dish(name="A", price="3", rating="3"), dish(name="B", price="8", rating="5"),
                   dish(stall="Other", centre="Tiong Bahru Market", name="C", price="2", rating="4")):
        client.post("/dishes/new", data=values)
    assert [d["dish"] for d in client.get("/api/dishes").json] == ["B", "C", "A"]  # top rated first
    assert [d["dish"] for d in client.get("/api/dishes?sort=price").json] == ["C", "A", "B"]
    assert [d["dish"] for d in client.get("/api/dishes?centre=Maxwell Food Centre&max_price=5").json] == ["A"]
    assert client.get("/api/dishes?max_price=lots").status_code == 400


def test_leaderboard_averages_ratings_per_stall(app):
    add_dish(parse_dish_form(dish(stall="Good", rating="5")))
    add_dish(parse_dish_form(dish(stall="Good", name="Other dish", rating="3")))
    add_dish(parse_dish_form(dish(stall="Great", rating="5")))
    board = [(stall.name, float(average), count) for stall, average, count in stall_leaderboard()]
    assert board == [("Great", 5.0, 1), ("Good", 4.0, 2)]


def test_seed_adds_random_dishes_once(app):
    assert seed_random_dishes(12, rng=random.Random(1)) == 12
    assert Dish.query.count() == 12
    assert all(1 <= d.rating <= 5 and d.price > 0 for d in Dish.query)
    assert seed_random_dishes(12) == 0
    assert Dish.query.count() == 12


def test_database_url_normalises_postgres_scheme(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@host/db?sslmode=require")
    assert database_url() == "postgresql+psycopg://u:p@host/db?sslmode=require"
    monkeypatch.delenv("DATABASE_URL")
    assert database_url() == "sqlite:///makan.db"


def test_forms_require_csrf_token_outside_tests():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite://"})
    with app.app_context():
        db.create_all()
        assert app.test_client().post("/dishes/new", data=dish()).status_code == 400
        assert Dish.query.count() == 0


def test_api_errors_are_json(client):
    response = client.get("/api/dishes?max_price=lots")
    assert response.status_code == 400 and response.json["message"] == "max_price must be a number."
    assert client.get("/api/nope").json["error"] == "Not Found"
    assert client.get("/nope").mimetype == "text/html"


def test_add_form_suggests_existing_centres(client):
    client.post("/dishes/new", data=dish(centre="Tiong Bahru Market"))
    assert b'<option value="Tiong Bahru Market">' in client.get("/dishes/new").data
