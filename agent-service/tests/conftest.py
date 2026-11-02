"""Shared test isolation and the small API boundary used by several suites."""

from collections.abc import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_mysql_agent
from app.main import create_app


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Classify existing flat test files without moving or rewriting them."""
    for item in items:
        name = item.path.name
        if name in {"test_evaluation.py", "test_reviewed20.py", "test_jev_routing_corpus.py"}:
            layer = "evaluation"
        elif name == "test_mcp_integration.py":
            layer = "integration"
        elif name == "test_api.py":
            layer = "api"
        else:
            layer = "unit"
        item.add_marker(getattr(pytest.mark, layer))


@pytest.fixture
def api_app() -> Iterator[FastAPI]:
    app = create_app()
    previous = dict(app.dependency_overrides)
    try:
        yield app
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.fixture
def api_client(api_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(api_app) as client:
        yield client


@pytest.fixture
def override_agent(api_app: FastAPI):
    def install(agent: object) -> None:
        api_app.dependency_overrides[get_mysql_agent] = lambda: agent
    return install
