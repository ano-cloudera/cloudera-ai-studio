from app.services.session_context import is_referential_follow_up


def test_perbandingan_alone_not_referential() -> None:
    assert is_referential_follow_up("Analisa perbandingan dengan industri standard") is False


def test_breakdown_is_referential() -> None:
    assert is_referential_follow_up("breakdown cabang palembang top 3 produk") is True


def test_compare_with_rank_hint_is_referential() -> None:
    assert is_referential_follow_up("bandingkan cabang pertama dan terakhir dari tabel tadi") is True
