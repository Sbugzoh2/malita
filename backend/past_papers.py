from .db import get_session, PastPaper


def list_past_papers():
    """Metadata for every past paper, newest first — no file bytes, so this
    is cheap to call for a list view (Streamlit sidebar, mobile screen)."""
    with get_session() as db:
        rows = (
            db.query(PastPaper)
            .order_by(
                PastPaper.year.desc(), PastPaper.exam_series.asc(),
                PastPaper.paper_number.asc(), PastPaper.document_type.asc(),
                PastPaper.variant.asc(),
            )
            .all()
        )
        return [
            {
                "id": r.id, "title": r.title, "subject": r.subject, "grade": r.grade,
                "year": r.year, "month": r.month, "exam_series": r.exam_series,
                "document_type": r.document_type, "paper_number": r.paper_number,
                "variant": r.variant, "file_name": r.file_name, "file_size": r.file_size,
                "uploaded_at": r.uploaded_at,
            }
            for r in rows
        ]


def get_past_paper_file(paper_id: int):
    """Returns (file_name, file_data) for download, or None if not found."""
    with get_session() as db:
        row = db.query(PastPaper).filter(PastPaper.id == paper_id).first()
        if row is None:
            return None
        return row.file_name, row.file_data


def add_past_paper(title: str, year: int, paper_number: int, file_name: str,
                    file_data: bytes, variant: str = "English", month: str = None,
                    exam_series: str = "November (Final)", document_type: str = "Question Paper",
                    subject: str = "Mathematics", grade: int = 12,
                    uploaded_by: int = None) -> int:
    with get_session() as db:
        row = PastPaper(
            title=title, subject=subject, grade=grade, year=year, month=month,
            exam_series=exam_series, document_type=document_type,
            paper_number=paper_number, variant=variant, file_name=file_name,
            file_data=file_data, file_size=len(file_data), uploaded_by=uploaded_by,
        )
        db.add(row)
        db.flush()
        return row.id


def delete_past_paper(paper_id: int) -> None:
    with get_session() as db:
        db.query(PastPaper).filter(PastPaper.id == paper_id).delete()
