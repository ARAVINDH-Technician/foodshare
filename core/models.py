from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    DONOR, NGO = "donor", "ngo"
    ROLES = [(DONOR, "Donor (hotel, hall, college, event)"), (NGO, "NGO / volunteer")]
    role = models.CharField(max_length=5, choices=ROLES, default=DONOR)
    organisation = models.CharField(max_length=120, blank=True)
    phone = models.CharField(max_length=15, blank=True)
    verified = models.BooleanField(default=False, help_text="NGOs must be verified by an admin before requesting food.")

    @property
    def display_name(self):
        return self.organisation or self.get_full_name() or self.username


class Donation(models.Model):
    AVAILABLE, PENDING, REQUESTED, COLLECTED, CANCELLED = "available", "pending", "requested", "collected", "cancelled"
    STATUS = [(AVAILABLE, "Available"), (PENDING, "Pending approval"), (REQUESTED, "Confirmed"),
              (COLLECTED, "Collected"), (CANCELLED, "Cancelled")]
    TYPES = [(t, t) for t in ("Hotel / restaurant", "Marriage hall", "College event", "Other event")]
    donor = models.ForeignKey(User, on_delete=models.CASCADE, related_name="donations")
    donor_type = models.CharField(max_length=30, choices=TYPES)
    food = models.CharField("Food description", max_length=200)
    portions = models.PositiveIntegerField("Meal portions")
    area = models.CharField(max_length=80)
    address = models.TextField("Pickup address")
    deadline = models.DateTimeField("Collect before")
    safe_declared = models.BooleanField(default=False)
    status = models.CharField(max_length=10, choices=STATUS, default=AVAILABLE)
    ngo = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="claims")
    rejected_by = models.ManyToManyField(User, blank=True, related_name="rejected_donations")
    created = models.DateTimeField(auto_now_add=True)
    requested_at = models.DateTimeField(null=True, blank=True)
    responded_at = models.DateTimeField(null=True, blank=True)
    collected_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    @property
    def state(self):
        if self.status in (self.AVAILABLE, self.PENDING) and self.deadline <= timezone.now():
            return "expired"
        return self.status

    @property
    def label(self):
        return "Expired" if self.state == "expired" else self.get_status_display()

    @property
    def confirmed(self):
        return self.status in (self.REQUESTED, self.COLLECTED)

    @property
    def badge(self):
        return {"available": "text-bg-success", "pending": "text-bg-info", "requested": "text-bg-warning",
                "collected": "text-bg-primary", "expired": "text-bg-danger", "cancelled": "text-bg-secondary"}[self.state]

    def __str__(self):
        return f"{self.food} ({self.portions}) - {self.area}"


class FoodNeed(models.Model):
    ngo = models.ForeignKey(User, on_delete=models.CASCADE, related_name="needs")
    area = models.CharField(max_length=80)
    meals = models.PositiveIntegerField("Meals needed")
    active = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]