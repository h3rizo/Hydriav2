from apps.inventory.models_vehicles import Vehicule

# Check the exact plates we're trying to match
plates_to_find = ['16733WWT', '0875TBK', '16689WWT', '11492WWT', '11493WWT', '0917TBP', '16735WWT', '16736WWT']

print('Searching for these plates in database:')
for plate in plates_to_find:
    found = Vehicule.objects.filter(immatriculation=plate).exists()
    status = 'FOUND' if found else 'NOT FOUND'
    print(f'  {plate}: {status}')

print()
print('Sample of actual plates in database (first 20):')
vehicles = Vehicule.objects.all()[:20]
for v in vehicles:
    print(f'  {v.immatriculation}')

print()
print(f'Total vehicles in database: {Vehicule.objects.count()}')
