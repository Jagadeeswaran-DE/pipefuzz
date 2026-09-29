import pytest

from pipefuzz.spark import create_spark_session


@pytest.fixture(scope="session")
def spark():
    session = create_spark_session()
    yield session
    session.stop()

