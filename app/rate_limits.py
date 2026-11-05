"""Bound abuse using counters shared through the application database."""
import hashlib
import math
import os
import time
from sqlalchemy import delete
from app.db import get_db
from app.models import SecurityCounter


def hit(db, bucket, identity, limit, window, now=None):
    now=time.time() if now is None else now
    key=hashlib.sha256(f'{bucket}:{identity}:{int(now//window)}'.encode()).hexdigest()
    table=SecurityCounter.__table__
    dialect=db.get_bind().dialect.name
    if dialect=='sqlite':
        from sqlalchemy.dialects.sqlite import insert
    elif dialect=='postgresql':
        from sqlalchemy.dialects.postgresql import insert
    else:
        raise RuntimeError('Rate limiting requires SQLite or PostgreSQL')
    statement=insert(table).values(key=key,count=1,expires_at=(int(now//window)+1)*window)
    count=db.execute(statement.on_conflict_do_update(index_elements=['key'],set_={'count':table.c.count+1}).returning(table.c.count)).scalar_one()
    db.execute(delete(SecurityCounter).where(SecurityCounter.expires_at < now))
    db.commit()
    return count<=limit


async def enforce(request):
    if os.environ.get('RATE_LIMIT_ENABLED','1')=='0':return True
    route=request.url.path
    if route in {'/login','/register','/forgot-password','/reset-password'}:
        bucket,limit,window='auth',int(os.environ.get('AUTH_RATE_LIMIT','20')),900
        identity=request.client.host if request.client else 'unknown'
    elif route in {'/plan/generate','/plan/regenerate','/plan/next-week'} or route.endswith('/swap'):
        bucket,limit,window='generation',int(os.environ.get('GENERATION_RATE_LIMIT','10')),3600
        identity=str(request.session.get('user_id') or (request.client.host if request.client else 'unknown'))
    else:return True
    provider=request.app.dependency_overrides.get(get_db,get_db)
    gen=provider()
    now=time.time()
    request.state.rate_retry_after=max(1,math.ceil((int(now//window)+1)*window-now))
    try:return hit(next(gen),bucket,identity,limit,window,now=now)
    finally:gen.close()
