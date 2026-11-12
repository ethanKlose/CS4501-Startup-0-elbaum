"""Render the actual planning route in an isolated in-memory app for DOM tests."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
os.environ.update(DATABASE_URL='sqlite://',ANTHROPIC_API_KEY='',OPENAI_API_KEY='',RATE_LIMIT_ENABLED='0',APP_ENV='development')
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker
from app import main
from app.db import Base,get_db,make_engine

engine=make_engine('sqlite://')
Base.metadata.create_all(engine)
sessions=sessionmaker(bind=engine,autoflush=False,expire_on_commit=False)
main.init_db=lambda:None  # in-memory tables above; production databases are never opened
app=main.create_app()
def connection():
    with sessions() as db:yield db
app.dependency_overrides[get_db]=connection
with TestClient(app,follow_redirects=False) as client:
    client.get('/health')
    def post(path,data):
        return client.post(path,data={'csrf_token':client.cookies['csrf_token'],**data})
    assert post('/register',{'email':'dom-render@example.test','password':'DomRenderPass123!'}).status_code==303
    if '--first' not in sys.argv:
        values={'budget':'150'}
        if '--goals' in sys.argv:
            values.update(goals_present='1',goals=['high_protein','calorie_target'],protein_target='120',calorie_target='2200')
        assert post('/survey',values).status_code==303
    if '--pantry-fragment' in sys.argv:
        assert post('/pantry/add',{'name':'rice','quantity':'2','unit':'cup'}).status_code==303
        response=client.get('/pantry',headers={'Accept':'application/json'})
        assert response.status_code==200
        sys.stdout.buffer.write(response.json()['html'].encode('utf-8'))
        raise SystemExit(0)
    response=client.get('/survey')
    assert response.status_code==200
    sys.stdout.buffer.write(response.text.encode('utf-8'))
