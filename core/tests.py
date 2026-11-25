from datetime import timedelta
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from .models import Donation, User


class FlowTests(TestCase):
    def setUp(self):
        self.donor = User.objects.create_user("d", password="x", role="donor", organisation="Hotel A")
        self.ngo = User.objects.create_user("n", password="x", role="ngo", organisation="Trust", verified=True)
        self.don = Donation.objects.create(donor=self.donor, donor_type="Marriage hall", food="Rice", portions=50, area="Fairlands",
                                           address="x", deadline=timezone.now() + timedelta(hours=2), safe_declared=True)

    def refresh(self):
        self.don.refresh_from_db()

    def test_unverified_ngo_cannot_claim(self):
        self.ngo.verified = False; self.ngo.save()
        self.client.force_login(self.ngo)
        self.client.post(reverse("claim", args=[self.don.pk]))
        self.refresh(); self.assertEqual(self.don.status, "available")

    def test_claim_accept_collect(self):
        self.client.force_login(self.ngo)
        self.client.post(reverse("claim", args=[self.don.pk]))
        self.refresh(); self.assertEqual(self.don.status, "pending")
        self.client.force_login(self.donor)
        self.client.post(reverse("accept", args=[self.don.pk]))
        self.refresh(); self.assertEqual(self.don.status, "requested")
        self.client.force_login(self.ngo)
        self.client.post(reverse("collect", args=[self.don.pk]))
        self.refresh(); self.assertEqual(self.don.status, "collected")

    def test_rejected_ngo_cannot_request_again(self):
        self.client.force_login(self.ngo)
        self.client.post(reverse("claim", args=[self.don.pk]))
        self.client.force_login(self.donor)
        self.client.post(reverse("reject", args=[self.don.pk]))
        self.client.force_login(self.ngo)
        self.client.post(reverse("claim", args=[self.don.pk]))
        self.refresh()
        self.assertEqual(self.don.status, "available")
        self.assertIsNone(self.don.ngo)

    def test_donor_blocked_from_ngo_desk(self):
        self.client.force_login(self.donor)
        self.assertEqual(self.client.get(reverse("ngo_desk")).status_code, 302)

    def test_expired_not_claimable(self):
        Donation.objects.filter(pk=self.don.pk).update(deadline=timezone.now() - timedelta(minutes=1))
        self.client.force_login(self.ngo)
        self.client.post(reverse("claim", args=[self.don.pk]))
        self.refresh(); self.assertEqual(self.don.state, "expired")