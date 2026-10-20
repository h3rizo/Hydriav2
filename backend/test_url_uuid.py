import uuid

# Tester la conversion UUID
uuid_str = '5e70939a-aa39-4da1-aa98-5518c9d3923d'

print(f"UUID string: {uuid_str}")
print(f"Type: {type(uuid_str)}")

try:
    uuid_obj = uuid.UUID(uuid_str)
    print(f"UUID objet: {uuid_obj}")
    print(f"Type: {type(uuid_obj)}")
    print(f"Conversion OK")
except Exception as e:
    print(f"Erreur conversion: {e}")

# Test avec tirets manquants (au cas où)
uuid_no_dash = uuid_str.replace('-', '')
print(f"\nSans tirets: {uuid_no_dash}")
try:
    uuid_obj2 = uuid.UUID(uuid_no_dash)
    print(f"UUID objet: {uuid_obj2}")
except Exception as e:
    print(f"Erreur: {e}")
