import pytest
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from sk_shared.middleware import setup_cors


def test_setup_cors_requires_explicit_origins():
    app = FastAPI()
    with pytest.raises(ValueError, match="explicit allow_origins"):
        setup_cors(app, [])


def test_setup_cors_applies_only_the_given_origins():
    app = FastAPI()
    setup_cors(app, ["https://app.sahulatkar.pk"])

    cors_middlewares = [m for m in app.user_middleware if m.cls is CORSMiddleware]
    assert len(cors_middlewares) == 1
    assert cors_middlewares[0].kwargs["allow_origins"] == ["https://app.sahulatkar.pk"]
    assert cors_middlewares[0].kwargs["allow_credentials"] is True
