FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CG_ENV=production \
    PORT=7860

RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app

COPY --chown=user requirements-runtime.txt .
RUN pip install --user -r requirements-runtime.txt

COPY --chown=user . .
RUN mkdir -p data/cache data/uploads evidence

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
    CMD python -c "import os,urllib.request as u; u.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','7860'), timeout=4)"

CMD ["sh", "-c", "exec python -m uvicorn clauseguard.sandbox.api:app --host 0.0.0.0 --port ${PORT}"]
