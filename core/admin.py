from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Donation, FoodNeed, User


@admin.register(User)
class FSUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("FoodShare", {"fields": ("role", "organisation", "phone", "verified")}),)
    list_display = ("username", "organisation", "role", "verified", "phone")
    list_filter = ("role", "verified")
    actions = ["verify"]

    @admin.action(description="Verify selected NGOs")
    def verify(self, request, qs):
        qs.filter(role=User.NGO).update(verified=True)


admin.site.register(Donation, list_display=("food", "donor", "area", "portions", "deadline", "status", "ngo"), list_filter=("status", "area"))
admin.site.register(FoodNeed, list_display=("ngo", "area", "meals", "active"))
