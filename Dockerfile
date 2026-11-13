FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    LOJA_HOST=0.0.0.0 \
    LOJA_PORTA=8000 \
    LOJA_BANCO=/dados/loja.db

WORKDIR /app
RUN useradd --system --uid 10001 loja && mkdir /dados && chown loja /dados
COPY loja ./loja
USER loja

EXPOSE 8000
HEALTHCHECK --interval=5s --timeout=3s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/saude', timeout=2)"]
CMD ["python", "-m", "loja"]
