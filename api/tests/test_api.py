from datetime import timedelta

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from rest_framework.test import APIClient

from api.models import Document, QueryLog, UserSession

pytestmark = pytest.mark.django_db   # every test gets a fresh, throwaway database

PASSWORD = "Str0ng-Pass-123"


# ---------- fixtures ----------

@pytest.fixture(autouse=True)
def fast_hashing(settings):
    # Cheap password hashing keeps the tests fast; production settings are untouched
    settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture
def alice(django_user_model):
    return django_user_model.objects.create_user("alice", password=PASSWORD)


@pytest.fixture
def bob(django_user_model):
    return django_user_model.objects.create_user("bob", password=PASSWORD)


def client_for(user):
    """An APIClient that sends this user's token on every request."""
    session = UserSession.objects.create(user=user)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {session.token}")
    return client


@pytest.fixture
def anon():
    return APIClient()


@pytest.fixture
def alice_client(alice):
    return client_for(alice)


@pytest.fixture
def bob_client(bob):
    return client_for(bob)


def make_docs(owner, n):
    for i in range(n):
        Document.objects.create(owner=owner, title=f"Doc {i}", content=f"text {i}")


# ---------- auth ----------

def test_register_success(anon):
    r = anon.post("/auth/register", {"username": "carol", "password": PASSWORD}, format="json")
    assert r.status_code == 201
    assert "token" in r.json()
    assert "password" not in r.json()["user"]


def test_register_duplicate_username(anon, alice):
    r = anon.post("/auth/register", {"username": "alice", "password": PASSWORD}, format="json")
    assert r.status_code == 400


def test_register_weak_password(anon):
    r = anon.post("/auth/register", {"username": "carol", "password": "123"}, format="json")
    assert r.status_code == 400


def test_login_success(anon, alice):
    r = anon.post("/auth/login", {"username": "alice", "password": PASSWORD}, format="json")
    assert r.status_code == 200
    assert "token" in r.json()


def test_login_wrong_password(anon, alice):
    r = anon.post("/auth/login", {"username": "alice", "password": "wrong"}, format="json")
    assert r.status_code == 401


def test_logout_invalidates_token(alice):
    client = client_for(alice)
    assert client.post("/auth/logout").status_code == 204
    assert client.post("/auth/logout").status_code == 401   # same token, now deleted


def test_expired_token_rejected(alice):
    session = UserSession.objects.create(
        user=alice, expires_at=timezone.now() - timedelta(seconds=1)
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {session.token}")
    assert client.get("/documents").status_code == 401


def test_protected_endpoints_require_token(anon):
    assert anon.get("/documents").status_code == 401
    assert anon.post("/query", {"query_text": "hi"}, format="json").status_code == 401
    assert anon.get("/queries").status_code == 401


# ---------- POST /documents ----------

def test_create_document_json(alice_client, alice):
    r = alice_client.post("/documents", {"title": "My doc", "content": "Some text"}, format="json")
    assert r.status_code == 201
    assert r.json()["owner"] == alice.id
    assert Document.objects.filter(owner=alice, title="My doc").exists()


def test_create_document_missing_title(alice_client):
    r = alice_client.post("/documents", {"content": "Some text"}, format="json")
    assert r.status_code == 400


def test_create_document_blank_content(alice_client):
    r = alice_client.post("/documents", {"title": "T", "content": "   "}, format="json")
    assert r.status_code == 400


def test_owner_cannot_be_spoofed(alice_client, alice, bob):
    r = alice_client.post(
        "/documents", {"title": "T", "content": "C", "owner": bob.id}, format="json"
    )
    assert r.status_code == 201
    assert r.json()["owner"] == alice.id


def test_upload_txt_file(alice_client):
    f = SimpleUploadedFile("notes.txt", b"hello from a file")
    r = alice_client.post("/documents", {"file": f}, format="multipart")
    assert r.status_code == 201
    assert r.json()["title"] == "notes.txt"
    assert r.json()["content"] == "hello from a file"


def test_upload_with_custom_title(alice_client):
    f = SimpleUploadedFile("notes.txt", b"hello")
    r = alice_client.post("/documents", {"file": f, "title": "Custom"}, format="multipart")
    assert r.status_code == 201
    assert r.json()["title"] == "Custom"


def test_upload_unsupported_type(alice_client):
    f = SimpleUploadedFile("data.csv", b"a,b,c")
    r = alice_client.post("/documents", {"file": f}, format="multipart")
    assert r.status_code == 400


def test_upload_corrupt_pdf(alice_client):
    f = SimpleUploadedFile("broken.pdf", b"this is not a pdf")
    r = alice_client.post("/documents", {"file": f}, format="multipart")
    assert r.status_code == 400


def test_upload_too_large(alice_client, settings):
    settings.MAX_UPLOAD_BYTES = 10          # shrink the limit instead of sending 5 MB
    f = SimpleUploadedFile("big.txt", b"x" * 11)
    r = alice_client.post("/documents", {"file": f}, format="multipart")
    assert r.status_code == 413


def test_json_content_too_large(alice_client, settings):
    settings.MAX_UPLOAD_BYTES = 10
    r = alice_client.post("/documents", {"title": "T", "content": "x" * 11}, format="json")
    assert r.status_code == 413


# ---------- GET /documents (pagination) ----------

def test_list_default_page_size_and_shape(alice_client, alice):
    make_docs(alice, 12)
    r = alice_client.get("/documents")
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 12
    assert len(body["results"]) == 10
    assert body["next"] is not None
    assert body["previous"] is None


def test_list_second_page(alice_client, alice):
    make_docs(alice, 12)
    body = alice_client.get("/documents?page=2").json()
    assert len(body["results"]) == 2
    assert body["next"] is None
    assert body["previous"] is not None


def test_list_custom_page_size(alice_client, alice):
    make_docs(alice, 12)
    body = alice_client.get("/documents?page_size=5").json()
    assert len(body["results"]) == 5


def test_list_page_out_of_range(alice_client, alice):
    make_docs(alice, 3)
    assert alice_client.get("/documents?page=999").status_code == 404


def test_list_only_own_documents(alice_client, bob_client, alice):
    make_docs(alice, 3)
    assert alice_client.get("/documents").json()["count"] == 3
    assert bob_client.get("/documents").json()["count"] == 0


# ---------- GET / DELETE /documents/{id} ----------

def test_get_own_document(alice_client, alice):
    doc = Document.objects.create(owner=alice, title="T", content="C")
    r = alice_client.get(f"/documents/{doc.id}")
    assert r.status_code == 200
    assert r.json()["id"] == doc.id


def test_get_other_users_document_is_404(bob_client, alice):
    doc = Document.objects.create(owner=alice, title="T", content="C")
    assert bob_client.get(f"/documents/{doc.id}").status_code == 404


def test_get_missing_document_is_404(alice_client):
    assert alice_client.get("/documents/99999").status_code == 404


def test_delete_other_users_document_is_403(bob_client, alice):
    doc = Document.objects.create(owner=alice, title="T", content="C")
    assert bob_client.delete(f"/documents/{doc.id}").status_code == 403
    assert Document.objects.filter(id=doc.id).exists()      # still there


def test_delete_own_document(alice_client, alice):
    doc = Document.objects.create(owner=alice, title="T", content="C")
    assert alice_client.delete(f"/documents/{doc.id}").status_code == 204
    assert not Document.objects.filter(id=doc.id).exists()


def test_delete_missing_document_is_404(alice_client):
    assert alice_client.delete("/documents/99999").status_code == 404


# ---------- /query and /queries ----------

def test_create_query(alice_client, alice):
    r = alice_client.post("/query", {"query_text": "What is FastAPI?"}, format="json")
    assert r.status_code == 201
    body = r.json()
    assert body["query_text"] == "What is FastAPI?"
    assert body["user"] == alice.id
    assert body["result_summary"] == ""
    assert QueryLog.objects.filter(user=alice).count() == 1


@pytest.mark.parametrize("payload", [{"query_text": ""}, {"query_text": "   "}, {}])
def test_create_query_invalid(alice_client, payload):
    assert alice_client.post("/query", payload, format="json").status_code == 400
    assert QueryLog.objects.count() == 0


def test_list_queries_paginated_and_private(alice_client, bob_client, alice, bob):
    for i in range(12):
        QueryLog.objects.create(user=alice, query_text=f"q{i}")
    QueryLog.objects.create(user=bob, query_text="bob's query")

    body = alice_client.get("/queries").json()
    assert set(body) == {"count", "next", "previous", "results"}
    assert body["count"] == 12
    assert len(body["results"]) == 10
    assert all(item["user"] == alice.id for item in body["results"])

    assert bob_client.get("/queries").json()["count"] == 1