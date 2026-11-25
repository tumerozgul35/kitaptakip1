import os
from datetime import datetime
from functools import wraps
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, flash, redirect, render_template, request, session, url_for

import db
import scraper


BASE_DIR = Path(__file__).resolve().parent
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "yerel-gelistirme-anahtari")
TZ = ZoneInfo("Europe/Istanbul")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def now_local():
    return datetime.now(TZ)


@app.before_request
def initialize_database():
    db.initialize()


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form.get("username") == "test" and request.form.get("password") == "123":
            session.clear()
            session["logged_in"] = True
            return redirect(url_for("library"))
        flash("Kullanıcı adı veya şifre hatalı.", "danger")
    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
@login_required
def library():
    active_shelf = request.args.get("raf", "Okunuyor")
    if active_shelf not in ("Okunacak", "Okunuyor", "Okundu"):
        active_shelf = "Okunuyor"
    books = db.list_books(active_shelf)
    counts = db.shelf_counts()
    return render_template("library.html", books=books, active_shelf=active_shelf, counts=counts)


@app.route("/ara")
@login_required
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return render_template("search.html", query="", results=[], search_error="")

    try:
        results = scraper.search_books(query)
        if not results:
            return render_template(
                "search.html",
                query=query,
                results=[],
                search_error="Kitap bulunamadı, elle ekleyebilirsin",
            )
        return render_template("search.html", query=query, results=results, search_error="")
    except scraper.ScraperError:
        return render_template(
            "search.html",
            query=query,
            results=[],
            search_error="Şu an kitap aranamıyor, elle ekleyebilirsin",
        )


@app.route("/kitap/ekle", methods=["POST"])
@login_required
def add_book():
    shelf = request.form.get("shelf", "Okunacak")
    if shelf not in ("Okunacak", "Okunuyor", "Okundu"):
        shelf = "Okunacak"

    try:
        total_pages = int(request.form.get("total_pages") or 0)
    except (TypeError, ValueError):
        total_pages = 0
    if total_pages <= 0:
        flash("Sayfa sayısı 1 veya daha büyük olmalıdır.", "danger")
        return redirect(request.referrer or url_for("library"))

    cover_path = request.form.get("cover_path", "")
    existing = db.find_duplicate(
        request.form.get("isbn", ""),
        request.form.get("title", ""),
        request.form.get("author", ""),
    )
    if existing:
        flash("Bu kitap zaten kitaplığında.", "warning")
        return redirect(url_for("library", raf=shelf))

    book = {
        "title": request.form.get("title", "").strip(),
        "author": request.form.get("author", "").strip(),
        "publisher": request.form.get("publisher", "").strip(),
        "cover_path": cover_path,
        "kitapyurdu_url": request.form.get("url", "").strip(),
        "total_pages": total_pages,
        "isbn": request.form.get("isbn", "").strip(),
        "publication_year": request.form.get("publication_year", "").strip(),
        "shelf": shelf,
        "finished_at": now_local().date().isoformat() if shelf == "Okundu" else None,
    }
    if not book["title"]:
        flash("Kitap adı zorunlu.", "danger")
        return redirect(request.referrer or url_for("library"))

    book_id = db.add_book(book)
    if request.form.get("download_cover") == "1" and book["kitapyurdu_url"]:
        cover_url = request.form.get("cover_url", "")
        if cover_url:
            saved = scraper.download_cover(cover_url, book_id)
            if saved:
                db.update_cover(book_id, saved)
    flash("Kitap kitaplığınıza eklendi.", "success")
    return redirect(url_for("library", raf=shelf))


@app.route("/kitap/<int:book_id>")
@login_required
def book_detail(book_id):
    book = db.get_book(book_id)
    if not book:
        return redirect(url_for("library"))
    logs = db.get_logs(book_id)
    estimate = db.estimate_finish_days(book_id)
    return render_template("book_detail.html", book=book, logs=logs, estimate=estimate)


@app.route("/kitap/<int:book_id>/raf", methods=["POST"])
@login_required
def change_shelf(book_id):
    shelf = request.form.get("shelf")
    if shelf not in ("Okunacak", "Okunuyor", "Okundu"):
        return redirect(url_for("book_detail", book_id=book_id))
    finished_at = now_local().date().isoformat() if shelf == "Okundu" else None
    db.update_shelf(book_id, shelf, finished_at)
    return redirect(url_for("library", raf=shelf))


@app.route("/kitap/<int:book_id>/okuma", methods=["POST"])
@login_required
def add_reading_log(book_id):
    book = db.get_book(book_id)
    if not book:
        return redirect(url_for("library"))
    try:
        pages = int(request.form.get("pages"))
    except (TypeError, ValueError):
        flash("Geçerli bir sayfa numarası girin.", "danger")
        return redirect(url_for("book_detail", book_id=book_id))

    previous = db.latest_pages(book_id)
    total = int(book["total_pages"])
    if pages <= 0:
        flash("Okunan sayfa 1 veya daha büyük olmalıdır.", "danger")
    elif total <= 0:
        flash("Önce toplam sayfa sayısını girin.", "danger")
    elif pages > total:
        flash("Okunan sayfa toplam sayfadan büyük olamaz.", "danger")
    elif pages < previous:
        flash("Okunan sayfa önceki kayıttan küçük olamaz.", "danger")
    else:
        db.add_reading_log(book_id, pages, now_local().date().isoformat())
        if pages == total:
            db.update_shelf(book_id, "Okundu", now_local().date().isoformat())
            flash("Tebrikler, kitabı bitirdiniz!", "success")
        else:
            db.update_shelf(book_id, "Okunuyor", None)
            flash("Okuma kaydı eklendi.", "success")
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/okuma/<int:log_id>/sil", methods=["POST"])
@login_required
def delete_reading_log(log_id):
    book_id = db.delete_log(log_id)
    if book_id:
        latest = db.latest_pages(book_id)
        book = db.get_book(book_id)
        if book and latest < int(book["total_pages"]):
            db.update_shelf(book_id, "Okunuyor" if latest > 0 else "Okunacak", None)
    return redirect(url_for("book_detail", book_id=book_id) if book_id else url_for("library"))


@app.route("/kitap/<int:book_id>/puan", methods=["POST"])
@login_required
def update_rating(book_id):
    try:
        rating = int(request.form.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0
    if rating < 0 or rating > 5:
        rating = 0
    db.update_rating(book_id, rating, request.form.get("note", "").strip())
    return redirect(url_for("book_detail", book_id=book_id))


@app.route("/istatistik")
@login_required
def statistics():
    target = db.get_setting("annual_goal", "24")
    try:
        target = int(target)
    except (TypeError, ValueError):
        target = 24
    year = now_local().year
    completed = db.completed_in_year(year)
    difference = completed - target
    if difference >= 0:
        target_status = f"Bu yıl {completed}/{target}, hedefe {abs(difference)} kitap öndesin"
    else:
        target_status = f"Bu yıl {completed}/{target}, hedefin {abs(difference)} kitap gerisindesin"

    return render_template(
        "statistics.html",
        target=target,
        target_status=target_status,
        monthly=db.monthly_pages(year),
        streak=db.reading_streak(),
    )


@app.route("/ayarlar", methods=["GET", "POST"])
@login_required
def settings():
    if request.method == "POST":
        try:
            goal = int(request.form.get("annual_goal", 24))
        except (TypeError, ValueError):
            goal = 24
        if goal < 1:
            goal = 24
        db.set_setting("annual_goal", str(goal))
        flash("Ayarlar kaydedildi.", "success")
        return redirect(url_for("settings"))
    return render_template("settings.html", annual_goal=db.get_setting("annual_goal", "24"))


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5010)

