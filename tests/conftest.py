import pytest

from escalation_router.config import DEFAULT_DATA_DIR, build_toolbox


@pytest.fixture
def toolbox():
    return build_toolbox(DEFAULT_DATA_DIR)
