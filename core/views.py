import csv
from functools import wraps

from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import DonationForm, NeedForm, SignupForm
from .models import Donation, FoodNeed, User

D = Donation


def role_required(role):
    def deco(view):
        @login_required
        @wraps(view)
        def wrapper(request, *a, **k):
            if request.user.role != role:
                messages.error(request, "That page is only for %s accounts." % ("donor" if role == User.DONOR else "NGO"))
                return redirect("home")
            return view(request, *a, **k)
        return wrapper
    return deco


def open_qs():
    return D.objects.filter(status=D.AVAILABLE, deadline__gt=timezone.now())


def home(request):
    now, area, status = timezone.now(), request.GET.get("area", "").strip(), request.GET.get("status", "")
    qs = D.objects.select_related("donor", "ngo")
    if area:
        qs = qs.filter(area__iexact=area)
    if status == "expired":
        qs = qs.filter(status__in=(D.AVAILABLE, D.PENDING), deadline__lte=now)
    elif status == "available":
        qs = qs.filter(status=D.AVAILABLE, deadline__gt=now)
    elif status in (D.PENDING, D.REQUESTED, D.COLLECTED, D.CANCELLED):
        qs = qs.filter(status=status)
    stats = {"open": open_qs().aggregate(s=Sum("portions"))["s"] or 0,
             "collected": D.objects.filter(status=D.COLLECTED).aggregate(s=Sum("portions"))["s"] or 0,
             "donations": D.objects.count(), "ngos": User.objects.filter(role=User.NGO, verified=True).count()}
    areas = D.objects.order_by("area").values_list("area", flat=True).distinct()
    return render(request, "home.html", {"rows": qs[:100], "areas": areas, "area": area, "status": status, "stats": stats})


def signup(request):
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        if user.role == User.NGO:
            messages.info(request, "Account created. An admin must verify your organisation before you can request food.")
            return redirect("ngo_desk")
        messages.success(request, "Welcome! You can now post surplus food.")
        return redirect("donor_desk")
    return render(request, "signup.html", {"form": form})


@role_required(User.DONOR)
def donor_desk(request):
    form = DonationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        d = form.save(commit=False)
        d.donor = request.user
        d.save()
        messages.success(request, "Donation posted. Verified NGOs can now request it.")
        return redirect("donor_desk")
    rows = request.user.donations.select_related("ngo")
    return render(request, "donor_desk.html", {"form": form, "rows": rows})


@require_POST
@role_required(User.DONOR)
def cancel(request, pk):
    n = D.objects.filter(pk=pk, donor=request.user, status=D.AVAILABLE).update(status=D.CANCELLED)
    messages.success(request, "Donation cancelled.") if n else messages.error(request, "Only available donations can be cancelled.")
    return redirect("donor_desk")


@require_POST
@role_required(User.DONOR)
def accept(request, pk):
    now = timezone.now()
    n = D.objects.filter(pk=pk, donor=request.user, status=D.PENDING, deadline__gt=now).update(
        status=D.REQUESTED, responded_at=now)
    messages.success(request, "Accepted. The NGO can now see your address and phone.") if n else \
        messages.error(request, "That request can no longer be accepted.")
    return redirect("donor_desk")


@require_POST
@role_required(User.DONOR)
def reject(request, pk):
    d = D.objects.filter(pk=pk, donor=request.user, status=D.PENDING).first()
    if d and d.ngo_id:
        d.rejected_by.add(d.ngo_id)
        D.objects.filter(pk=pk, status=D.PENDING).update(status=D.AVAILABLE, ngo=None, requested_at=None)
        messages.success(request, "Rejected. That NGO cannot request this food again. Other NGOs can.")
    else:
        messages.error(request, "That request can no longer be rejected.")
    return redirect("donor_desk")


@role_required(User.NGO)
def ngo_desk(request):
    form = NeedForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        n = form.save(commit=False)
        n.ngo = request.user
        n.save()
        messages.success(request, "Food need posted.")
        return redirect("ngo_desk")
    available = open_qs().exclude(rejected_by=request.user).select_related("donor") if request.user.verified else []
    ctx = {"form": form, "open": available,
           "mine": D.objects.filter(ngo=request.user).select_related("donor"),
           "needs": request.user.needs.filter(active=True)}
    return render(request, "ngo_desk.html", ctx)


@require_POST
@role_required(User.NGO)
def claim(request, pk):
    if not request.user.verified:
        messages.error(request, "Your organisation is not verified yet.")
        return redirect("ngo_desk")
    d = open_qs().filter(pk=pk).first()
    if d and d.rejected_by.filter(pk=request.user.pk).exists():
        messages.error(request, "The donor declined your earlier request for this food.")
        return redirect("ngo_desk")
    n = open_qs().filter(pk=pk).update(status=D.PENDING, ngo=request.user, requested_at=timezone.now())
    messages.success(request, "Request sent. You get the pickup address and phone once the donor accepts.") if n else \
        messages.error(request, "Sorry, that food is no longer available.")
    return redirect("ngo_desk")


@require_POST
@role_required(User.NGO)
def collect(request, pk):
    n = D.objects.filter(pk=pk, ngo=request.user, status=D.REQUESTED).update(status=D.COLLECTED, collected_at=timezone.now())
    messages.success(request, "Marked as collected.") if n else messages.error(request, "Could not update that donation.")
    return redirect("ngo_desk")


@require_POST
@role_required(User.NGO)
def close_need(request, pk):
    get_object_or_404(FoodNeed, pk=pk, ngo=request.user)
    FoodNeed.objects.filter(pk=pk).update(active=False)
    return redirect("ngo_desk")


def dashboard(request):
    rows = {}
    row = lambda a: rows.setdefault(a, {"area": a, "surplus": 0, "needed": 0, "collected": 0, "expired": 0})
    counts = {"collected": 0, "expired": 0, "cancelled": 0, "total": 0}
    delays, responses = [], []
    for d in D.objects.all():
        r, s = row(d.area), d.state
        counts["total"] += 1
        if s == "available":
            r["surplus"] += d.portions
        elif s == "collected":
            r["collected"] += d.portions
            if d.requested_at and d.collected_at:
                delays.append((d.collected_at - d.requested_at).total_seconds() / 3600)
        elif s == "expired":
            r["expired"] += d.portions
        if d.responded_at and d.requested_at:
            responses.append((d.responded_at - d.requested_at).total_seconds() / 60)
        if s in counts:
            counts[s] += 1
    for n in FoodNeed.objects.filter(active=True):
        row(n.area)["needed"] += n.meals
    top = max([max(r["surplus"], r["needed"]) for r in rows.values()] + [1])
    for r in rows.values():
        r["gap"] = r["surplus"] - r["needed"]
        r["s_pct"], r["n_pct"] = r["surplus"] * 100 // top, r["needed"] * 100 // top
    done = counts["collected"] + counts["expired"]
    ctx = {"rows": sorted(rows.values(), key=lambda r: -abs(r["gap"])), "counts": counts,
           "success": round(counts["collected"] * 100 / done) if done else None,
           "delay": round(sum(delays) / len(delays), 1) if delays else None,
           "response": round(sum(responses) / len(responses)) if responses else None}
    return render(request, "dashboard.html", ctx)


@login_required
def export_csv(request):
    resp = HttpResponse(content_type="text/csv")
    resp["Content-Disposition"] = 'attachment; filename="foodshare-report.csv"'
    w = csv.writer(resp)
    w.writerow(["Donor", "Food", "Portions", "Area", "Deadline", "Status", "NGO", "Posted", "Requested", "Donor responded", "Collected"])
    for d in D.objects.select_related("donor", "ngo"):
        w.writerow([d.donor.display_name, d.food, d.portions, d.area, d.deadline.isoformat(), d.state,
                    d.ngo.display_name if d.ngo else "", d.created.isoformat(),
                    d.requested_at.isoformat() if d.requested_at else "",
                    d.responded_at.isoformat() if d.responded_at else "",
                    d.collected_at.isoformat() if d.collected_at else ""])
    return resp


def safety(request):
    return render(request, "safety.html")