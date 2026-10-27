from app.jobs.document_runner import ingestion_concurrency_limit


def test_ingestion_concurrency_limit_default():
    assert ingestion_concurrency_limit() == 3
