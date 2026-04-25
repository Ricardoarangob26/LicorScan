import json
json_path = r'C:\Users\rarango\Documents\LicorScan\data\raw\exito_20260423T153510Z_xhr.json'
with open(json_path, 'r', encoding='utf-8') as f:
    data = json.load(f)
print(f'Total: {len(data)}')
licores_keywords = ['licores', 'vinhos', 'cervezas', 'alcohol', 'ron', 'aguardiente', 'whisky', 'vodka', 'tequila', 'ginebra']
licores = [p for p in data if p.get('category') and any(kw in p['category'].lower() for kw in licores_keywords)]
print(f'Licores: {len(licores)}')
print('Muestra (nombre|precio|url|imagen|categoria):')
for p in data[:12]:
    print(f\"{p.get('name')}|{p.get('price_cop')}|{p.get('url')}|{p.get('image_url')}|{p.get('category')}\")
