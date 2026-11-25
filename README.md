# FoodShare India (Django)

Setup (Python 3.10+):
    python -m venv venv && source venv/bin/activate      # Windows: venv\Scripts\activate
    pip install -r requirements.txt
    python manage.py makemigrations core
    python manage.py migrate
    python manage.py createsuperuser
    python manage.py test
    python manage.py runserver

Open http://127.0.0.1:8000. Admin panel: /admin/ -> Users -> select NGO users -> action "Verify selected NGOs".

Production env vars: DEBUG=0, SECRET_KEY=<long random>, ALLOWED_HOSTS=yourdomain, CSRF_TRUSTED_ORIGINS=https://yourdomain
then `python manage.py collectstatic`. Free hosting: PythonAnywhere.

Database settings can be supplied with `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, and `DB_PORT`.
The default database is named `foodshare` on localhost with user `root` and no password.
