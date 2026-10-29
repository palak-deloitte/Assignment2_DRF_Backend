# Assignment 2: Django Backend Service

A Django REST Framework backend with token authentication, document upload and management, query history, and pagination.

## Endpoints

| Method | Path              | Description                                                | Auth  |
| ------ | ----------------- | ---------------------------------------------------------- | ----- |
| POST   | `/auth/register`  | Create an account; returns a token                         | None  |
| POST   | `/auth/login`     | Log in; returns a token                                    | None  |
| POST   | `/auth/logout`    | Invalidate the current token                               | Token |
| POST   | `/documents`      | Upload a file (.txt/.pdf) or send JSON `title` + `content` | Token |
| GET    | `/documents`      | List your documents (paginated)                            | Token |
| GET    | `/documents/{id}` | Retrieve one of your documents                             | Token |
| DELETE | `/documents/{id}` | Delete a document                                          | Token |
| POST   | `/query`          | Record a query in your history                             | Token |
| GET    | `/queries`        | List your query history (paginated)                        | Token |

All endpoints except register and login require the header:

```
Authorization: Token <token>
```

### Status codes

| Endpoint                         | Code | When                                                                      |
| -------------------------------- | ---- | ------------------------------------------------------------------------- |
| `/auth/register`                 | 201  | Account created                                                           |
|                                  | 400  | Username taken, weak password, or missing field                           |
| `/auth/login`                    | 200  | Success                                                                   |
|                                  | 401  | Wrong username or password                                                |
| `/auth/logout`                   | 204  | Session deleted                                                           |
| Any protected endpoint           | 401  | Token missing, invalid, or expired                                        |
| `POST /documents`                | 201  | Document created                                                          |
|                                  | 400  | Missing or empty title or content, unsupported file type, unreadable file |
|                                  | 413  | File or content larger than the limit                                     |
| `GET /documents/{id}`            | 200  | Success                                                                   |
|                                  | 404  | Not found, **or owned by someone else**                                   |
| `DELETE /documents/{id}`         | 204  | Deleted                                                                   |
|                                  | 403  | Document exists but you do not own it                                     |
|                                  | 404  | Document does not exist                                                   |
| `POST /query`                    | 201  | Query logged                                                              |
|                                  | 400  | `query_text` missing or empty                                             |
| `GET /documents`, `GET /queries` | 200  | Success                                                                   |
|                                  | 404  | `page` is out of range                                                    |

### Pagination

List endpoints accept `page` and `page_size` (default 10, maximum 100) and return:

```json
{
  "count": 25,
  "next": "http://.../documents?page=2",
  "previous": null,
  "results": []
}
```

Results are ordered newest first.

## Authentication

Login and registration create a `UserSession` row holding a random 64-character token that expires after **24 hours**. A custom DRF authentication class (`api/authentication.py`) looks the token up on every request, rejects expired sessions, and sets `request.user`. Logout deletes the session. Every user can hold several active sessions (for example, one per device).

## Models

| Model         | Fields                                           |
| ------------- | ------------------------------------------------ |
| `Document`    | id, title, content, uploaded_at, owner           |
| `QueryLog`    | id, query_text, result_summary, created_at, user |
| `UserSession` | id, user, token, created_at, expires_at          |

## Design decisions

- **Allowed file types:** `.txt` (UTF-8) and `.pdf`. Text is extracted on upload and stored in `Document.content`. The original file is not stored.
- **Maximum size:** 5 MB for uploaded files and for JSON content (`MAX_UPLOAD_BYTES` in `config/settings.py`). Anything larger returns 413.
- **Scanned PDFs** (images with no text layer) are rejected with 400, since there is no text to extract.
- **Ownership:** all reads are filtered by owner. For `GET /documents/{id}`, other users' documents return 404 so their existence is not revealed. For `DELETE`, the document is looked up first and a non-owner receives 403, as the spec requires.
- **The owner is never read from the request**, only taken from the authenticated user.
- **`result_summary`** is left empty in this assignment. It will be populated by the RAG pipeline in Assignment 3A.
- **Passwords** are hashed with Django's default hasher and validated with Django's password validators.
- **URLs** have no trailing slash, matching the specification.

## Setup

Requires Python 3.12.

```bash
python -m venv venv
venv\Scripts\activate            # Windows
# source venv/bin/activate       # macOS / Linux
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser   # optional, for /admin/
python manage.py runserver
```

The API runs at http://127.0.0.1:8000/. The admin panel is at `/admin/`.

## Tests

```bash
python -m pytest -v
```

The suite uses DRF's `APIClient` and a temporary database, so your development data is never touched. It covers authentication and token expiry, document upload limits and file types, ownership rules (403 vs 404), pagination, and per-user isolation of documents and queries.

## Project structure

```
config/             project settings and root URLs
api/
  models.py         Document, QueryLog, UserSession
  authentication.py token authentication backed by UserSession
  serializers.py    request and response validation
  views.py          API views
  permissions.py    IsOwner object permission
  pagination.py     page size rules
  uploads.py        file validation and text extraction
  tests/            automated tests
```

## Limitations

- The 413 check runs after the server has received the file. A production deployment should also limit request size at the web server.
- SQLite is used for development.
- No token refresh: users log in again after 24 hours.
