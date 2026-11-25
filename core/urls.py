from django.contrib.auth import views as auth
from django.urls import path
from . import views as v

urlpatterns = [
    path("", v.home, name="home"),
    path("signup/", v.signup, name="signup"),
    path("login/", auth.LoginView.as_view(), name="login"),
    path("logout/", auth.LogoutView.as_view(), name="logout"),
    path("donor/", v.donor_desk, name="donor_desk"),
    path("donor/cancel/<int:pk>/", v.cancel, name="cancel"),
    path("donor/accept/<int:pk>/", v.accept, name="accept"),
    path("donor/reject/<int:pk>/", v.reject, name="reject"),
    path("ngo/", v.ngo_desk, name="ngo_desk"),
    path("ngo/claim/<int:pk>/", v.claim, name="claim"),
    path("ngo/collect/<int:pk>/", v.collect, name="collect"),
    path("ngo/need/<int:pk>/close/", v.close_need, name="close_need"),
    path("analytics/", v.dashboard, name="dashboard"),
    path("analytics/export.csv", v.export_csv, name="export_csv"),
    path("food-safety/", v.safety, name="safety"),
]