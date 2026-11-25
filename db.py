from datetime import date
from pathlib import Path
import sqlite3


DB_PATH = Path(__file__).resolve().parent / "data" / "kitap.db"


def get_connection():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    return connection


def initialize():
    with get_connection() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT,
                publisher TEXT,
                cover_path TEXT,
                kitapyurdu_url TEXT,
                total_pages INTEGER NOT NULL DEFAULT 0,
                isbn TEXT,
                publication_year TEXT,
                shelf TEXT NOT NULL DEFAULT 'Okunacak',
                finished_at TEXT,
                rating INTEGER NOT NULL DEFAULT 0,
                note TEXT,
                created_at TEXT
            );
            CREATE TABLE IF NOT EXISTS reading_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                book_id INTEGER NOT NULL,
                pages INTEGER NOT NULL,
                read_date TEXT NOT NULL,
                FOREIGN KEY(book_id) REFERENCES books(id) ON DELETE CASCADE
            );
            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            """
        )


def find_duplicate(isbn, title, author):
    with get_connection() as connection:
        if isbn:
            row = connection.execute(
                "SELECT id FROM books WHERE isbn = ? AND isbn != ''", (isbn,)
            ).fetchone()
            if row:
                return row
        return connection.execute(
            "SELECT id FROM books WHERE lower(title)=lower(?) AND lower(coalesce(author,''))=lower(?)",
            (title, author),
        ).fetchone()


def add_book(book):
    with get_connection() as connection:
        cursor = connection.execute(
            """
            INSERT INTO books
            (title, author, publisher, cover_path, kitapyurdu_url, total_pages, isbn,
             publication_year, shelf, finished_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                book["title"], book["author"], book["publisher"], book["cover_path"],
                book["kitapyurdu_url"], book["total_pages"], book["isbn"],
                book["publication_year"], book["shelf"], book["finished_at"],
                date.today().isoformat(),
            ),
        )
        return cursor.lastrowid


def update_cover(book_id, cover_path):
    with get_connection() as connection:
        connection.execute("UPDATE books SET cover_path=? WHERE id=?", (cover_path, book_id))


def list_books(shelf):
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT * FROM books WHERE shelf=? ORDER BY created_at DESC, id DESC", (shelf,)
        ).fetchall()
        books = []
        for row in rows:
            book = dict(row)
            latest = connection.execute(
                "SELECT pages FROM reading_logs WHERE book_id=? ORDER BY read_date DESC, id DESC LIMIT 1",
                (row["id"],),
            ).fetchone()
            book["progress_pages"] = latest["pages"] if latest else 0
            books.append(book)
        return books


def get_book(book_id):
    with get_connection() as connection:
        return connection.execute("SELECT * FROM books WHERE id=?", (book_id,)).fetchone()


def shelf_counts():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT shelf, COUNT(*) AS count FROM books GROUP BY shelf"
        ).fetchall()
        return {row["shelf"]: row["count"] for row in rows}


def update_shelf(book_id, shelf, finished_at):
    with get_connection() as connection:
        connection.execute(
            "UPDATE books SET shelf=?, finished_at=? WHERE id=?", (shelf, finished_at, book_id)
        )


def add_reading_log(book_id, pages, read_date):
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO reading_logs(book_id, pages, read_date) VALUES (?, ?, ?)",
            (book_id, pages, read_date),
        )


def latest_pages(book_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT pages FROM reading_logs WHERE book_id=? ORDER BY read_date DESC, id DESC LIMIT 1",
            (book_id,),
        ).fetchone()
        return row["pages"] if row else 0


def get_logs(book_id):
    with get_connection() as connection:
        return connection.execute(
            "SELECT * FROM reading_logs WHERE book_id=? ORDER BY read_date DESC, id DESC",
            (book_id,),
        ).fetchall()


def delete_log(log_id):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT book_id FROM reading_logs WHERE id=?", (log_id,)
        ).fetchone()
        if row:
            connection.execute("DELETE FROM reading_logs WHERE id=?", (log_id,))
            return row["book_id"]
        return None


def update_rating(book_id, rating, note):
    with get_connection() as connection:
        connection.execute(
            "UPDATE books SET rating=?, note=? WHERE id=?", (rating, note, book_id)
        )


def estimate_finish_days(book_id):
    with get_connection() as connection:
        book = connection.execute(
            "SELECT total_pages FROM books WHERE id=?", (book_id,)
        ).fetchone()
        if not book:
            return None
        logs = connection.execute(
            """
            SELECT pages, read_date FROM reading_logs
            WHERE book_id=? ORDER BY read_date ASC, id ASC
            """,
            (book_id,),
        ).fetchall()
        if len(logs) < 1:
            return None

    by_day = {}
    for log in logs:
        by_day[log["read_date"]] = max(by_day.get(log["read_date"], 0), log["pages"])
    ordered = sorted(by_day.items())
    if len(ordered) == 1:
        return max(1, int((book["total_pages"] - ordered[0][1]) // ordered[0][1])) if ordered[0][1] else None

    recent = ordered[-7:]
    total_progress = recent[-1][1] - recent[0][1]
    if len(recent) > 1:
        from datetime import datetime
        day_span = max(1, (datetime.strptime(recent[-1][0], "%Y-%m-%d").date()
                           - datetime.strptime(recent[0][0], "%Y-%m-%d").date()).days)
        speed = total_progress / day_span
    else:
        speed = recent[-1][1] - 0
    remaining = book["total_pages"] - ordered[-1][1]
    if speed <= 0:
        return None
    return max(1, int(remaining / speed))


def get_setting(key, default):
    with get_connection() as connection:
        row = connection.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key, value):
    with get_connection() as connection:
        connection.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def completed_in_year(year):
    with get_connection() as connection:
        row = connection.execute(
            "SELECT COUNT(*) AS count FROM books WHERE shelf='Okundu' AND substr(finished_at,1,4)=?",
            (str(year),),
        ).fetchone()
        return row["count"]


def monthly_pages(year):
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT substr(read_date,6,2) AS month, MAX(pages) AS pages
            FROM reading_logs
            WHERE substr(read_date,1,4)=?
            GROUP BY substr(read_date,6,2)
            ORDER BY month
            """,
            (str(year),),
        ).fetchall()
    result = [0] * 12
    for row in rows:
        result[int(row["month"]) - 1] = row["pages"]
    return result


def reading_streak():
    with get_connection() as connection:
        rows = connection.execute(
            "SELECT DISTINCT read_date FROM reading_logs ORDER BY read_date DESC"
        ).fetchall()
    if not rows:
        return 0
    dates = [date.fromisoformat(row["read_date"]) for row in rows]
    streak = 1
    for previous, current in zip(dates, dates[1:]):
        if (previous - current).days == 1:
            streak += 1
        else:
            break
    return streak
