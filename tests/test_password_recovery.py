from urllib.parse import urlparse,parse_qs
from tests.helpers import signup


def test_reset_links_are_single_use_and_invalidate_old_password(client,monkeypatch):
    signup(client,email='reset@example.test')
    from app.services import mailer
    links=[]
    monkeypatch.setattr(mailer,'send_reset',lambda email,url:links.append(url))
    client.post('/forgot-password',data={'email':'reset@example.test'})
    token=parse_qs(urlparse(links[0]).query)['token'][0]
    assert client.post('/reset-password',data={'token':token,'password':'new-password'},follow_redirects=False).status_code==303
    assert client.post('/reset-password',data={'token':token,'password':'another-password'}).status_code==400
    assert client.post('/login',data={'email':'reset@example.test','password':'password123'}).status_code==401
    assert client.post('/login',data={'email':'reset@example.test','password':'new-password'},follow_redirects=False).status_code==303


def test_unknown_email_gets_the_same_public_message(client):
    response=client.post('/forgot-password',data={'email':'missing@example.test'})
    assert response.status_code==200 and 'If that account exists' in response.text
