FROM python:3.11-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY scripts scripts
ENV DATABASE_URL=sqlite:////data/platejoy.db PYTHONPATH=/srv
VOLUME /data
EXPOSE 8000
CMD ["sh", "-c", "python scripts/seed.py && uvicorn app.main:app --host 0.0.0.0 --port 8000"]
