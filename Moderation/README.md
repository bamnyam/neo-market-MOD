# Neo Market - Moderation Service

Moderation service of the Neo Market platform built with Django, DRF, PostgreSQL, Docker and uv.

## Tech Stack

- Python 3.14
- Django 5
- Django REST Framework
- PostgreSQL 16
- Docker / Docker Compose
- uv
- Ruff
- Pytest

## Local Development

Install dependencies:

```bash
cd Moderation
make install
```

Run development server:

```bash
make run
```

Application will be available at:

```text
http://localhost:8000
```

## Docker

From repository root:

```bash
docker compose up --build
```

Moderation service will be available at:

```text
http://localhost:8003
```
