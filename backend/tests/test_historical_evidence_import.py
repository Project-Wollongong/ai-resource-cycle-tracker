from datetime import datetime
from pathlib import Path

from app.config import settings
from app.models import Stock
from app.services.historical_evidence_import import import_historical_evidence


FIXTURE = Path(__file__).parents[2] / "docs" / "beta02-acceptance" / "pdfs" / "S01.pdf"


def test_historical_import_is_hash_idempotent(db_session, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "evidence_root", str(tmp_path))
    stock = Stock(code="IMP", name="Import Co", commodity="gold")
    db_session.add(stock); db_session.commit()

    first, created = import_historical_evidence(db_session, stock=stock, local_pdf_path=FIXTURE, title="June 5B", source_date=datetime(2026, 6, 30))
    db_session.commit()
    second, created_again = import_historical_evidence(db_session, stock=stock, local_pdf_path=FIXTURE, title="June 5B", source_date=datetime(2026, 6, 30))

    assert created is True and created_again is False
    assert second.id == first.id
    assert first.historical_baseline is True
    assert first.text_status == "extracted"


def test_imported_title_is_routed_as_an_appendix_5b():
    """P03 decides whether to read past the summary from the headline alone.

    A descriptive title such as "Historical 5B report 2024-12-31" classifies as
    nothing, so section 8 — the funding-runway block, which sits around page 30
    of a combined filing — is never reached and the import yields no financial
    facts at all. It fails silently: the document imports, parses, and produces
    zero.
    """
    import importlib.util
    from datetime import datetime
    from pathlib import Path

    from app.services.p3_classification_service import classify_announcement

    script = Path(__file__).resolve().parents[2] / "scripts" / "import_announcements.py"
    spec = importlib.util.spec_from_file_location("import_announcements", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    title = module._document_title("5B", datetime(2024, 12, 31))

    assert classify_announcement(title, None, []).document.standard_form == "Appendix 5B"
    assert "2024-12-31" in title


def test_an_unknown_document_kind_still_gets_a_usable_title():
    import importlib.util
    from datetime import datetime
    from pathlib import Path

    script = Path(__file__).resolve().parents[2] / "scripts" / "import_announcements.py"
    spec = importlib.util.spec_from_file_location("import_announcements", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    title = module._document_title("MRE", datetime(2026, 6, 30))

    assert "MRE" in title and "2026-06-30" in title
