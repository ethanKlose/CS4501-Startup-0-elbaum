import hashlib
import logging
import os
import secrets
import time
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, update
from app.db import get_db
from app.deps import render
from app.models import User, PasswordReset
from app.security import hash_password
from app.services import mailer
from app.services.locking import lock_user
from app.services.preferences import get_preferences, save_preferences

router=APIRouter()


@router.get('/forgot-password')
def forgot_form(request:Request):
    return render(request,'forgot_password.html')


@router.post('/forgot-password')
def forgot(request:Request,email:str=Form(''),db=Depends(get_db)):
    user=db.scalar(select(User).where(User.email==email.strip().lower()))
    if user:
        token=secrets.token_urlsafe(32)
        db.add(PasswordReset(token_hash=hashlib.sha256(token.encode()).hexdigest(),user_id=user.id,expires_at=time.time()+1800))
        db.commit()
        base=os.environ.get('PUBLIC_BASE_URL','http://127.0.0.1:8000').rstrip('/')
        try:mailer.send_reset(user.email,base+'/reset-password?token='+token)
        except Exception:logging.getLogger(__name__).error('Password reset delivery failed; check SMTP configuration')
    return render(request,'forgot_password.html',sent=True)


@router.get('/reset-password')
def reset_form(request:Request,token:str=''):
    return render(request,'reset_password.html',token=token,error=None)


@router.post('/reset-password')
def reset(request:Request,token:str=Form(''),password:str=Form(''),db=Depends(get_db)):
    digest=hashlib.sha256(token.encode()).hexdigest()
    row=db.get(PasswordReset,digest)
    if len(password)<8:
        return render(request,'reset_password.html',status_code=400,token=token,error='Use at least 8 characters.')
    if not row or row.used or row.expires_at<=time.time():
        return render(request,'reset_password.html',status_code=400,token='',error='This link is invalid or expired. Request a new one.')
    lock_user(db,row.user_id)
    claimed=db.execute(update(PasswordReset).where(PasswordReset.token_hash==digest,PasswordReset.used.is_(False),PasswordReset.expires_at>time.time()).values(used=True).returning(PasswordReset.user_id)).scalar_one_or_none()
    if claimed is None:
        db.rollback()
        return render(request,'reset_password.html',status_code=400,token='',error='This link has already been used.')
    user=db.get(User,claimed);user.password_hash=hash_password(password)
    prefs=get_preferences(db,user.id);prefs['auth_version']=prefs.get('auth_version',0)+1
    save_preferences(db,user.id,prefs)
    db.execute(update(PasswordReset).where(PasswordReset.user_id==user.id).values(used=True))
    db.commit();request.session.clear()
    return RedirectResponse('/login?reset=1',303)
