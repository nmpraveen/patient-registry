FROM python:3.12.13-slim-trixie

ARG VCS_REF=unknown
ARG MEDTRACK_GIT_TREE=unknown
ARG MEDTRACK_CONTEXT_POLICY=unverified

LABEL org.opencontainers.image.source="https://github.com/nmpraveen/patient-registry" \
      org.opencontainers.image.revision="${VCS_REF}" \
      net.naveenhospital.medtrack.git-tree="${MEDTRACK_GIT_TREE}" \
      net.naveenhospital.medtrack.build-context="git-archive-allowlist-v1" \
      net.naveenhospital.medtrack.context-policy="${MEDTRACK_CONTEXT_POLICY}"

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

EXPOSE 8000

CMD ["gunicorn", "patient_registry.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "60"]
