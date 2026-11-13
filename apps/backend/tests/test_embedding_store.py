import os
import tempfile
import numpy as np
import pytest
from app.services.embedding_store import EmbeddingStore

@pytest.fixture
def temp_store():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    store = EmbeddingStore(db_path=path)
    yield store
    if os.path.exists(path):
        os.remove(path)

def test_folder_lifecycle(temp_store):
    folder = temp_store.create_or_update_folder(
        folder_id="folder-123",
        name="Annual Gala",
        drive_folder_id="drive-abc",
        access_token="token-xyz",
        status="indexing",
        photo_count=50,
    )
    assert folder["id"] == "folder-123"
    assert folder["name"] == "Annual Gala"
    assert folder["photo_count"] == 50
    assert folder["status"] == "indexing"

    folders = temp_store.list_folders()
    assert len(folders) == 1
    assert folders[0]["id"] == "folder-123"

    temp_store.update_folder_status("folder-123", "ready")
    updated = temp_store.get_folder("folder-123")
    assert updated["status"] == "ready"

def test_face_encodings_and_search(temp_store):
    temp_store.create_or_update_folder(
        folder_id="folder-1",
        name="Test Album",
        drive_folder_id="drive-1",
        access_token="fake-token",
        status="ready",
        photo_count=2,
    )

    encoding_a = np.ones(128, dtype=np.float64) * 0.1
    encoding_b = np.ones(128, dtype=np.float64) * 0.9

    temp_store.save_face_encodings(
        folder_id="folder-1",
        file_id="photo-1",
        file_name="alice.jpg",
        encodings=[encoding_a],
        download_url="https://drive.google.com/photo1",
    )

    temp_store.save_face_encodings(
        folder_id="folder-1",
        file_id="photo-2",
        file_name="bob.jpg",
        encodings=[encoding_b],
        download_url="https://drive.google.com/photo2",
    )

    query_a = np.ones(128, dtype=np.float64) * 0.12
    matches = temp_store.search_faces("folder-1", query_a, tolerance=0.6)

    assert len(matches) == 1
    assert matches[0]["file_id"] == "photo-1"
    assert matches[0]["file_name"] == "alice.jpg"
    assert matches[0]["confidence"] > 0.8

    token = temp_store.get_file_access_token("photo-1")
    assert token == "fake-token"

def test_reset_folder_faces_clears_existing_rows(temp_store):
    temp_store.create_or_update_folder(
        folder_id="folder-reset",
        name="Reset Album",
        drive_folder_id="drive-reset",
        status="ready",
        photo_count=1,
    )
    temp_store.save_face_encodings(
        folder_id="folder-reset",
        file_id="file-1",
        file_name="one.jpg",
        encodings=[np.ones(128, dtype=np.float64) * 0.2],
    )
    assert temp_store.get_folder("folder-reset")["faces_count"] == 1

    temp_store.reset_folder_faces("folder-reset")

    assert temp_store.get_folder("folder-reset")["faces_count"] == 0
    assert temp_store.get_folder_faces("folder-reset") == []

def test_save_face_encodings_is_idempotent_per_file(temp_store):
    temp_store.create_or_update_folder(
        folder_id="folder-dup",
        name="Dup Album",
        drive_folder_id="drive-dup",
        status="indexing",
        photo_count=1,
    )
    enc = np.ones(128, dtype=np.float64) * 0.3
    temp_store.save_face_encodings(
        folder_id="folder-dup",
        file_id="file-1",
        file_name="dup.jpg",
        encodings=[enc],
    )
    temp_store.save_face_encodings(
        folder_id="folder-dup",
        file_id="file-1",
        file_name="dup.jpg",
        encodings=[enc, enc * 0.5],
    )

    assert len(temp_store.get_folder_faces("folder-dup")) == 2
    assert temp_store.get_folder("folder-dup")["faces_count"] == 2

def test_search_faces_handles_zero_tolerance(temp_store):
    temp_store.create_or_update_folder(
        folder_id="folder-tol",
        name="Tol Album",
        drive_folder_id="drive-tol",
        status="ready",
        photo_count=1,
    )
    temp_store.save_face_encodings(
        folder_id="folder-tol",
        file_id="file-1",
        file_name="one.jpg",
        encodings=[np.ones(128, dtype=np.float64) * 0.1],
    )
    assert temp_store.search_faces("folder-tol", np.ones(128, dtype=np.float64) * 0.1, tolerance=0.0) == []
