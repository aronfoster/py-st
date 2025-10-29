def test_import() -> None:
    import py_st  # noqa: F401


def test_import_services() -> None:
    # Fails if dataclass has mutable defaults
    from py_st.services.systems import MarketGoods  # noqa: F401
