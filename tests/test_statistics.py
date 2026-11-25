import db
from datetime import date


def test_annual_goal_status(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kitap.db")
    db.initialize()
    db.set_setting("annual_goal", "24")
    assert db.get_setting("annual_goal", "24") == "24"
    assert db.completed_in_year(date.today().year) == 0


def test_estimate_with_logs(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "kitap.db")
    db.initialize()
    book_id = db.add_book({
        "title": "Test",
        "author": "Yazar",
        "publisher": "",
        "cover_path": "",
        "kitapyurdu_url": "",
        "total_pages": 300,
        "isbn": "",
        "publication_year": "",
        "shelf": "Okunuyor",
        "finished_at": None,
    })
    db.add_reading_log(book_id, 100, "2026-11-20")
    db.add_reading_log(book_id, 150, "2026-11-21")
    estimate = db.estimate_finish_days(book_id)
    assert estimate == 3
