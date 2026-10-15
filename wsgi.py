"""Punto de entrada WSGI:  gunicorn wsgi:app   |   flask --app wsgi run"""
from app import create_app

app = create_app()
