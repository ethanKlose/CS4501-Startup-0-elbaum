"""SMTP in production, a private local outbox for local development."""
import json
import os
import smtplib
import ssl
import secrets
from email.message import EmailMessage
from pathlib import Path
from app.config import settings


def send_reset(email, url):
    host=os.environ.get('SMTP_HOST')
    if not host:
        if settings.production:
            raise RuntimeError('SMTP_HOST is required for password recovery in production')
        outbox=Path(os.environ.get('LOCAL_MAIL_DIR','.local-mail'))
        outbox.mkdir(mode=0o700,parents=True,exist_ok=True)
        target=outbox/(secrets.token_hex(12)+'.json')
        target.write_text(json.dumps({'to':email,'subject':'Reset your PlateJoy password','url':url},indent=2))
        target.chmod(0o600)
        return
    message=EmailMessage()
    message['From']=os.environ.get('SMTP_FROM','no-reply@platejoy.local')
    message['To']=email;message['Subject']='Reset your PlateJoy password'
    message.set_content('Reset your password within 30 minutes:\n'+url+'\nIgnore this message if you did not request it.')
    port=int(os.environ.get('SMTP_PORT','587'))
    client=smtplib.SMTP_SSL if port==465 else smtplib.SMTP
    with client(host,port,timeout=15,**({'context':ssl.create_default_context()} if port==465 else {})) as smtp:
        if port!=465:smtp.starttls(context=ssl.create_default_context())
        if os.environ.get('SMTP_USERNAME'):smtp.login(os.environ['SMTP_USERNAME'],os.environ.get('SMTP_PASSWORD',''))
        smtp.send_message(message)
