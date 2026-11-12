"""Rebuild the expanded mappings from the documented USDA SR Legacy CSV ZIP.
Usage: python -m scripts.import_expanded_nutrition /path/to/source.zip
No API key or network request; never accesses the application database.
"""
import csv,io,json,hashlib,zipfile,sys
from pathlib import Path
root=Path(__file__).resolve().parent.parent;p=root/'app/data/ingredients.json';data=json.loads(p.read_text())
if len(sys.argv)!=2:raise SystemExit('Pass the downloaded USDA SR Legacy CSV ZIP path.')
archive=Path(sys.argv[1])
assert hashlib.sha256(archive.read_bytes()).hexdigest()==data['archive_sha256']
z=zipfile.ZipFile(archive);prefix=z.namelist()[0]
def rows(name):return csv.DictReader(io.TextIOWrapper(z.open(prefix+name),encoding='utf-8-sig'))
foods={int(r['fdc_id']):r for r in rows('food.csv')}
# Recipe measures and demo retail packs are explicit assumptions, not USDA package prices.
# name, USDA FDC ID, recipe unit, grams/unit, package quantity in that unit, demo price
selected=[
('quinoa',168917,'cup',185,6,5.99),('brown rice',169704,'cup',195,8,3.49),('bulgur',170287,'cup',182,6,3.99),('pearl barley',170285,'cup',157,6,3.29),('millet',168871,'cup',174,6,3.99),('wild rice',168897,'cup',164,4,5.99),('couscous',169700,'cup',157,6,3.49),
('walnuts',170187,'tbsp',7,28,5.49),('pistachios',170184,'tbsp',8,28,7.49),('cashews',170162,'tbsp',8.6,26,5.49),('chia seeds',170554,'tbsp',12,19,4.99),('flaxseed',169414,'tbsp',10,23,3.99),('pumpkin seeds',170556,'tbsp',10,23,4.99),('sesame seeds',170150,'tbsp',9,12,3.49),
('strawberries',167762,'cup',152,3,3.99),('raspberries',167755,'cup',123,1.4,3.99),('blackberries',173946,'cup',144,1.2,3.49),('mango',169910,'cup',165,3,4.49),('pineapple',169124,'cup',165,4,3.49),('kiwi',168153,'each',69,6,3.99),('orange',169097,'each',131,4,3.49),('pear',169118,'each',178,3,3.49),('grapes',174683,'cup',151,3,4.99),
('asparagus',168389,'cup',134,3.4,3.99),('brussels sprouts',170383,'cup',88,5.2,3.49),('cauliflower',169986,'cup',107,5,3.49),('zucchini',169291,'cup',124,4,2.49),('eggplant',169228,'cup',82,5,2.49),('beets',169145,'cup',136,3,2.99),('red cabbage',169977,'cup',89,8,2.49),('arugula',169387,'cup',20,7,2.99),('kale',168421,'cup',67,3,2.49),('radishes',169276,'cup',116,2,1.49),('butternut squash',169295,'cup',140,5,3.49),('cremini mushrooms',168434,'cup',70,3.2,2.49),
('white beans',175203,'cup',179,2.3,1.29),('edamame',168411,'cup',155,3,3.49),('ricotta cheese',171248,'cup',246,1.7,3.99),('feta cheese',173420,'oz',28.3495,6,3.99),('goat cheese',173435,'oz',28.3495,4,3.99),('tahini',170189,'tbsp',15,30,5.49),('pork tenderloin',168249,'oz',28.3495,16,6.99),('sockeye salmon',173691,'oz',28.3495,16,14.99),('mackerel',175119,'oz',28.3495,16,8.99),('cod fillet',171955,'oz',28.3495,16,10.99),
]
ids={r[1] for r in selected};nutrients={i:{} for i in ids}
for r in rows('food_nutrient.csv'):
 identifier=int(r['fdc_id']);n=int(r['nutrient_id'])
 if identifier in ids and n in (1008,1003):nutrients[identifier][n]=float(r['amount'])
offers_path=root/'app/data/package_prices.json';prices=json.loads(offers_path.read_text())
for name,identifier,unit,grams,quantity,price in selected:
 assert 1008 in nutrients[identifier] and 1003 in nutrients[identifier],name
 food=foods[identifier]
 data['ingredients'][name]=dict(fdc_id=identifier,usda_description=food['description'],calories_per_100g=nutrients[identifier][1008],protein_per_100g=nutrients[identifier][1003],grams_per_unit={unit:grams},source_url=f'https://fdc.nal.usda.gov/food-details/{identifier}/nutrients',publication_date=food['publication_date'])
 prices['offers'][name+'|'+unit]=dict(name=name,unit=unit,package_quantity=quantity,package_price=price,source='Built-in demo estimate',observed_on=None)
data['measure_note']=data['measure_note'].split(' New grains')[0]+' New grains (quinoa, brown rice, bulgur, barley, millet, wild rice and couscous) and white beans/edamame use cooked cup measures; seafood and pork use raw edible ounces. New retail pack sizes are separate demo estimates expressed in the same recipe units.'
data['ingredients']=dict(sorted(data['ingredients'].items()));p.write_text(json.dumps(data,indent=2)+'\n');offers_path.write_text(json.dumps(prices,indent=2)+'\n')
print('Sourced ingredients:',len(data['ingredients']),'new:',len(selected),'price entries:',len(prices['offers']))
