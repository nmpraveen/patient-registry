ARG PYTHON_BASE_IMAGE=python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2
FROM ${PYTHON_BASE_IMAGE}

ARG VCS_REF=unknown
ARG BUILD_CONTEXT_SHA256=unverified

LABEL org.opencontainers.image.source="https://github.com/nmpraveen/patient-registry" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.medtrack.build-context.schema="medtrack.build-context/v1" \
      org.medtrack.build-context.digest="${BUILD_CONTEXT_SHA256}"

ARG VCS_REF=unknown
ARG BUILD_CONTEXT_SHA256=unverified

LABEL org.opencontainers.image.source="https://github.com/nmpraveen/patient-registry" \
      org.opencontainers.image.revision="${VCS_REF}" \
      org.medtrack.build-context.schema="medtrack.build-context/v1" \
      org.medtrack.build-context.digest="${BUILD_CONTEXT_SHA256}"

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV MEDTRACK_IMAGE_REVISION="${VCS_REF}"

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Runtime allowlist. Keep synchronized with build PR #100; never use COPY . or ADD .
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

EXPOSE 8000

CMD ["gunicorn", "patient_registry.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
