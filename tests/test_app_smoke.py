from app.main import create_app


def test_create_app(mock_config):
    app = create_app(mock_config)
    assert app.layout is not None

