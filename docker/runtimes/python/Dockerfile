FROM python:3.12-slim

RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin codeverse

WORKDIR /workspace
USER 1000:1000

CMD ["python", "/workspace/main.py"]
