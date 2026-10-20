import os
from django.db import connection

def check_columns():
    with connection.cursor() as cursor:
        cursor.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'plannings'")
        columns = [row[0] for row in cursor.fetchall()]
        print(f"Columns in 'plannings' table: {columns}")

if __name__ == "__main__":
    import django
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hydria.settings')
    django.setup()
    check_columns()
