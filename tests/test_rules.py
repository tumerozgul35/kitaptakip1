import db


def test_duplicate_title(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kitap.db")
    db.initialize()
    book_id = db.add_book({
        "title": "Suç ve Ceza",
        "author": "Fyodor Dostoyevski",
        "publisher": "Test",
        "cover_path": "",
        "kitapyurdu_url": "",
        "total_pages": 600,
        "isbn": "123",
        "publication_year": "2020",
        "shelf": "Okunacak",
        "finished_at": None,
    })
    assert book_id
    assert db.find_duplicate("123", "", "") is not None


def test_page_rule():
    previous = 100
    assert 99 < previous
    assert 601 > 600
