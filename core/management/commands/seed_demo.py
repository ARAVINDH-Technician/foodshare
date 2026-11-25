import random
from datetime import timedelta, timezone as dtz

from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import Donation, FoodNeed, User

IST = dtz(timedelta(hours=5, minutes=30))
AREAS = ["T Nagar", "Adyar", "Velachery", "Anna Nagar", "Tambaram", "Porur", "Guindy", "Mylapore"]

DONOR_NAMES = {
    "Hotel / restaurant": ["Spice Garden Hotel", "Marina Residency", "Saravana Bhavan Unit", "Hotel Annapoorna",
                           "Green Leaf Restaurant"],
    "Marriage hall": ["Sri Lakshmi Kalyana Mandapam", "Royal Palace Hall", "Vasantham Mahal", "Gokulam Convention",
                      "Sri Murugan Hall"],
    "College event": ["Loyola Event Cell", "Anna Univ Fest Team", "SRM Cultural Club", "Stella Maris Union",
                      "VIT Chennai Fest"],
    "Other event": ["Chennai Cultural Fest", "Book Fair Committee", "Temple Annadhanam Trust", "Music Season Caterers",
                    "Corporate Meet Services"],
}
PREFIX = {"Hotel / restaurant": "hotel", "Marriage hall": "hall", "College event": "college", "Other event": "event"}
NGO_NAMES = ["Annam Foundation", "Hope Kitchen", "Share a Meal Chennai", "Akshaya Trust", "Feed Chennai",
             "Sevai Volunteers", "Roti Bank Chennai", "Smile Meals", "Anbu Illam", "Nalam Foundation"]

HOURS = {  # IST posting hours by donor type
    "Hotel / restaurant": [14, 15, 16, 21, 22, 23],
    "Marriage hall": [12, 13, 14, 22, 23],
    "College event": [13, 14, 15, 16, 17],
    "Other event": [11, 15, 18, 19, 20],
}
PORTIONS = {"Hotel / restaurant": (20, 80), "Marriage hall": (100, 300),
            "College event": (40, 150), "Other event": (20, 100)}
FOODS = ["Veg meals", "Biryani", "Rice and sambar", "Chapati and curry", "Idli and chutney", "Mixed rice"]


class Command(BaseCommand):
    help = "Create 90 days of demo data: 20 donors, 10 NGOs, donations and needs"

    def handle(self, *args, **opts):
        random.seed(42)
        donors, ngos = [], []
        for dtype, names in DONOR_NAMES.items():
            for i, org in enumerate(names, 1):
                u, _ = User.objects.get_or_create(username=f"demo_{PREFIX[dtype]}{i}",
                                                  defaults={"role": "donor", "organisation": org, "verified": True})
                u.set_password("demo1234"); u.save()
                donors.append((u, dtype, round(random.uniform(0.40, 0.95), 2)))  # each donor has own reliability
        for i, org in enumerate(NGO_NAMES, 1):
            u, _ = User.objects.get_or_create(username=f"demo_ngo{i}",
                                              defaults={"role": "ngo", "organisation": org, "verified": True})
            u.set_password("demo1234"); u.save()
            ngos.append(u)

        # safe re-run: removes only demo_ data, your own accounts stay untouched
        Donation.objects.filter(donor__username__startswith="demo_").delete()
        FoodNeed.objects.filter(ngo__username__startswith="demo_").delete()

        now = timezone.now()
        today = now.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)
        count = 0
        for back in range(90, 0, -1):
            day = today - timedelta(days=back)
            weekend = day.weekday() >= 5
            for donor, dtype, rel in donors:
                if dtype == "Marriage hall":
                    p = 0.60 if weekend else 0.12
                elif dtype == "College event":
                    p = 0.08 if weekend else 0.30
                elif dtype == "Hotel / restaurant":
                    p = 0.35
                else:
                    p = 0.20
                p = min(0.95, p * (0.8 + 0.4 * (90 - back) / 90))  # slow growth over time
                if random.random() > p:
                    continue
                created = day.replace(hour=random.choice(HOURS[dtype]), minute=random.randint(0, 59))
                lo, hi = PORTIONS[dtype]
                d = Donation.objects.create(
                    donor=donor, donor_type=dtype, food=random.choice(FOODS),
                    portions=random.randint(lo, hi), area=random.choice(AREAS),
                    address="Demo address, Chennai", safe_declared=True,
                    deadline=created + timedelta(hours=random.randint(4, 7)))
                roll = random.random()
                fields = {"created": created}
                if roll < rel:  # collected
                    req = created + timedelta(minutes=random.randint(10, 60))
                    res = req + timedelta(minutes=random.randint(5, 90))
                    col = res + timedelta(minutes=random.randint(15, 60))
                    fields.update(status="collected", ngo=random.choice(ngos),
                                  requested_at=req, responded_at=res, collected_at=col)
                elif roll < rel + (1 - rel) * 0.25:
                    fields.update(status="cancelled")
                elif roll < rel + (1 - rel) * 0.5:  # NGO asked, donor never answered
                    fields.update(status="pending", ngo=random.choice(ngos),
                                  requested_at=created + timedelta(minutes=random.randint(10, 60)))
                # else stays "available" and the deadline passed, so it counts as expired
                Donation.objects.filter(pk=d.pk).update(**fields)  # created is auto_now_add
                count += 1

        # live food right now (for surplus vs demand)
        for i in range(12):
            donor, dtype, _ = random.choice(donors)
            lo, hi = PORTIONS[dtype]
            d = Donation.objects.create(
                donor=donor, donor_type=dtype, food=random.choice(FOODS), portions=random.randint(lo, hi),
                area=AREAS[i % len(AREAS)], address="Demo address, Chennai", safe_declared=True,
                deadline=now + timedelta(hours=random.randint(3, 6)))
            Donation.objects.filter(pk=d.pk).update(created=now - timedelta(minutes=random.randint(5, 90)))
            count += 1

        # NGO food needs: some areas want more than is available
        for area in AREAS:
            FoodNeed.objects.create(ngo=random.choice(ngos), area=area, meals=random.randint(40, 300), active=True)
        FoodNeed.objects.create(ngo=ngos[0], area=AREAS[0], meals=100, active=False)

        self.stdout.write(self.style.SUCCESS(
            f"Created {count} donations, {len(donors)} donors, {len(ngos)} NGOs, {len(AREAS)} active needs."))
        self.stdout.write("Demo logins: demo_hotel1 or demo_ngo1, password demo1234")
