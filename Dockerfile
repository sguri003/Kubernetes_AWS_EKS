FROM python:3.10-slim

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python manage.py collectstatic --noinput

EXPOSE 8000
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "web_app.wsgi:application"]


#CMD ["gunicorn", "web_app.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "2"]
