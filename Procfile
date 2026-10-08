web: flask --app wsgi db upgrade && flask --app wsgi seed-base && flask --app wsgi sync-passwords && gunicorn wsgi:app --worker-class gthread --workers 2 --threads 8 --timeout 120
