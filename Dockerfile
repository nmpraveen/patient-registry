ARG PYTHON_BASE_IMAGE=python:3.12.13-alpine3.23@sha256:601d3d3797e90e2534782e69c85fafb7971b43f24c7b1b079b7e48dd435e458d
FROM ${PYTHON_BASE_IMAGE}

ARG VCS_REF=unknown
ARG BUILD_CONTEXT_SHA256=unverified

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MEDTRACK_IMAGE_REVISION="${VCS_REF}"

WORKDIR /app

RUN apk add --no-cache \
        libcrypto3=3.5.8-r0 \
        libssl3=3.5.8-r0 \
        sqlite-libs=3.53.4-r0 \
    && addgroup -S -g 10001 medtrack \
    && adduser -S -D -H -u 10001 -G medtrack medtrack \
    && mkdir -p /app/staticfiles /app/backups \
    && chown 10001:10001 /app/staticfiles /app/backups \
    && chmod 1777 /tmp

COPY requirements.txt /app/requirements.txt
RUN python -m pip install --no-cache-dir --require-hashes -r /app/requirements.txt \
    && python -m pip check

# Runtime allowlist. Never replace these copies with COPY . or ADD .
COPY manage.py VERSION CHANGELOG.md /app/
COPY patient_registry /app/patient_registry
COPY api /app/api
COPY patients /app/patients
COPY templates /app/templates

# Apply commit-specific metadata after dependency installation so changing the
# reviewed revision does not invalidate the hash-locked dependency layer.
LABEL org.opencontainers.image.source="https://github.com/nmpraveen/patient-registry" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.medtrack.build-context.schema="medtrack.build-context/v1" \
      org.medtrack.build-context.digest="${BUILD_CONTEXT_SHA256}"

USER 10001:10001

EXPOSE 8000

CMD ["gunicorn", "patient_registry.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
