from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.utils import timezone
from .models import Donation, FoodNeed, User


class Styled:
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for f in self.fields.values():
            w = f.widget
            w.attrs["class"] = ("form-check-input" if isinstance(w, forms.CheckboxInput)
                                else "form-select" if isinstance(w, forms.Select) else "form-control")


class SignupForm(Styled, UserCreationForm):
    email = forms.EmailField()

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "email", "role", "organisation", "phone")

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["phone"].required = True
        self.fields["organisation"].label = "Organisation / hotel / hall / college name"

    def clean(self):
        d = super().clean()
        if d.get("role") == User.NGO and not d.get("organisation"):
            self.add_error("organisation", "NGOs must enter their organisation name.")
        return d


class DonationForm(Styled, forms.ModelForm):
    class Meta:
        model = Donation
        fields = ("donor_type", "food", "portions", "area", "address", "deadline", "safe_declared")
        widgets = {"deadline": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "address": forms.Textarea(attrs={"rows": 2})}
        labels = {"safe_declared": "I declare this food is freshly prepared, stored at a safe temperature and safe to eat until the deadline."}

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["deadline"].input_formats = ["%Y-%m-%dT%H:%M"]

    def clean_deadline(self):
        d = self.cleaned_data["deadline"]
        if d <= timezone.now():
            raise forms.ValidationError("The deadline must be in the future.")
        return d

    def clean_safe_declared(self):
        if not self.cleaned_data["safe_declared"]:
            raise forms.ValidationError("You must confirm the food is safe to share.")
        return True

    def clean_area(self):
        return self.cleaned_data["area"].strip().title()


class NeedForm(Styled, forms.ModelForm):
    class Meta:
        model = FoodNeed
        fields = ("area", "meals")

    def clean_area(self):
        return self.cleaned_data["area"].strip().title()
