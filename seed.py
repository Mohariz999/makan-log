"""Random starter data. Stall names are made up; hawker centres are real places."""
import random
from decimal import Decimal

from app import Dish, Stall, db

CENTRES = ["Maxwell Food Centre", "Tiong Bahru Market", "Old Airport Road", "Chinatown Complex",
           "Amoy Street Food Centre", "Newton Food Centre", "Bedok 85", "Adam Road Food Centre"]

# (stall name, cuisine, [(dish, low price, high price), ...])
STALLS = [
    ("Ah Seng Chicken Rice", "Chinese", [("Steamed chicken rice", 3.5, 5), ("Roasted chicken rice", 3.5, 5)]),
    ("Uncle Lim Char Kway Teow", "Chinese", [("Char kway teow", 4, 6)]),
    ("Mak Cik Nasi Lemak", "Malay", [("Nasi lemak with chicken wing", 3.5, 5.5), ("Nasi lemak with otah", 3, 4.5)]),
    ("Raju's Prata Corner", "Indian", [("Egg prata", 1.5, 2.5), ("Murtabak", 6, 9)]),
    ("Golden Wok Hokkien Mee", "Chinese", [("Fried Hokkien mee", 5, 8)]),
    ("Satay Bros", "Malay", [("Chicken satay (10 sticks)", 7, 10), ("Mutton satay (10 sticks)", 8, 11)]),
    ("Laksa Lane", "Peranakan", [("Curry laksa", 4.5, 6.5)]),
    ("Fishball Kaki", "Chinese", [("Dry fishball noodles", 3.5, 5)]),
    ("Briyani House", "Indian", [("Chicken briyani", 6, 8), ("Mutton briyani", 7, 9)]),
    ("Carrot Cake King", "Chinese", [("Black carrot cake", 3, 5), ("White carrot cake", 3, 5)]),
    ("Kopi & Toast", "Drinks", [("Kaya toast set", 3, 4.5), ("Teh tarik", 1.4, 2)]),
    ("Chendol Station", "Dessert", [("Chendol", 2, 3.5)]),
]

NOTES = [None, None, "Worth the queue", "Generous portion", "A bit salty", "Get there before noon",
         "Chilli is the star", "Cheap and good", "Wok hei on point", None]


def seed_random_dishes(count=12, rng=None):
    """Insert `count` random dishes if there are none yet. Returns how many were added."""
    if Dish.query.first():
        return 0
    rng = rng or random.Random()
    # A stall's dishes are all at one hawker centre, so pick the centre once per stall.
    stalls = {}
    choices = [(stall, cuisine, dish) for stall, cuisine, dishes in STALLS for dish in dishes]
    for stall_name, cuisine, (dish_name, low, high) in rng.sample(choices, min(count, len(choices))):
        if stall_name not in stalls:
            stalls[stall_name] = Stall(name=stall_name, hawker_centre=rng.choice(CENTRES), cuisine=cuisine)
            db.session.add(stalls[stall_name])
        price = Decimal(str(round(rng.uniform(low, high) * 2) / 2)).quantize(Decimal("0.01"))  # nearest 50c
        db.session.add(Dish(stall=stalls[stall_name], name=dish_name, price=price,
                            rating=rng.choices([2, 3, 4, 5], weights=[1, 3, 5, 3])[0], notes=rng.choice(NOTES)))
    db.session.commit()
    return min(count, len(choices))
