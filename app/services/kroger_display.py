"""Presentation-only shopping progress; never changes cart payloads or choices."""
import math
import re


def ingredient_icon(name):
    words=set(re.findall(r'[a-z]+',str(name).casefold()))
    groups=[({'banana','bananas'},'🍌'),({'apple','apples'},'🍎'),({'carrot','carrots'},'🥕'),
        ({'tomato','tomatoes'},'🍅'),({'broccoli','spinach','lettuce','kale'},'🥬'),({'potato','potatoes'},'🥔'),
        ({'egg','eggs'},'🥚'),({'milk','yogurt','cheese'},'🥛'),({'rice','oats','quinoa','cereal'},'🌾'),
        ({'bread','toast','tortilla','tortillas'},'🍞'),({'chicken','turkey'},'🍗'),
        ({'bean','beans','lentil','lentils'},'🫘'),({'pasta','spaghetti'},'🍝'),({'oil','butter'},'🫙')]
    return next((symbol for terms,symbol in groups if words & terms),'🛒')


def summary(draft):
    rows=(draft or {}).get('rows',[])
    selected=[row['selection'] for row in rows if row.get('selection')]
    by_upc={}
    known_total=0.0;unknown=0
    for item in selected:
        count=item.get('packages',1)
        price=item.get('price')
        if isinstance(price,(int,float)) and not isinstance(price,bool) and math.isfinite(price):
            known_total+=price*count
        else:unknown+=1
        key=item['upc']
        if key not in by_upc:by_upc[key]=dict(name=item['name'],packages=0,image_url=item.get('image_url'))
        by_upc[key]['packages']+=count
    return dict(total=len(rows),selected=len(selected),remaining=len(rows)-len(selected),
        percent=round(100*len(selected)/len(rows)) if rows else 0,
        products=len(by_upc),packages=sum(item.get('packages',1) for item in selected),
        known_total=round(known_total,2),unknown_prices=unknown,preview=list(by_upc.values())[:5],
        more=max(0,len(by_upc)-5))
