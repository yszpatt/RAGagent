import os
import pytest
from sqlalchemy import create_engine


@pytest.fixture
def engine():
    url = os.environ.get("TEST_DATABASE_URL", "postgresql://kp:kp@localhost:5432/knowledgepilot")
    return create_engine(url)
