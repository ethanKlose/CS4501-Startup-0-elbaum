from concurrent.futures import ThreadPoolExecutor
from sqlalchemy.orm import sessionmaker
from app.db import Base, make_engine
from app.models import User, Plan, Meal, PantryItem
from app.services import inventory


def test_two_workers_settle_the_same_purchase_once(tmp_path):
    engine=make_engine('sqlite:///'+str(tmp_path/'parallel.db'))
    Base.metadata.create_all(engine)
    factory=sessionmaker(engine,expire_on_commit=False)
    with factory() as s:
        u=User(email='parallel@example.test',password_hash='unused');s.add(u);s.flush()
        p=Plan(user_id=u.id,settings={'inventory':{'purchases':[dict(key='rice|cup',name='rice',unit='cup',quantity=2,cost=1)]}})
        s.add(p);s.commit();pid=p.id
    def settle():
        with factory() as s:
            p=s.get(Plan,pid)
            inventory.settle(s,p);s.commit()
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _:settle(),range(2)))
    with factory() as s:
        stock=s.query(PantryItem).all()
        assert len(stock)==1 and stock[0].quantity==2
