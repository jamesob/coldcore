# Dockerfile for running tests/lints
FROM docker.io/library/python:latest

WORKDIR /src
COPY ./requirements-dev.txt .
RUN pip install -r requirements-dev.txt
