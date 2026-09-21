import pytest

from app.config import get_settings


@pytest.fixture(autouse=True)
def reset_settings_cache():
    """테스트마다 설정 캐시를 비운다. APP_MODE 를 바꿔 가며 쓰기 때문이다."""
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()
