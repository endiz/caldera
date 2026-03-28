import pytest
import app

from http import HTTPStatus


@pytest.fixture
def expected_caldera_info():
    return {
        'access': 'RED',
        'application': 'Caldera',
        'can_write': True,
        'plugins': [],
        'role': 'RED',
        'version': app.get_version()
    }


class TestHealthApi:
    async def test_get_health(self, api_v2_client, api_cookies, expected_caldera_info):
        resp = await api_v2_client.get('/api/v2/health', cookies=api_cookies)
        assert resp.status == HTTPStatus.OK
        output_info = await resp.json()
        assert output_info == expected_caldera_info

    async def test_unauthorized_get_health(self, api_v2_client):
        resp = await api_v2_client.get('/api/v2/health')
        assert resp.status == HTTPStatus.UNAUTHORIZED

    async def test_get_health_for_purple_user(self, api_v2_client, purple_api_cookies):
        resp = await api_v2_client.get('/api/v2/health', cookies=purple_api_cookies)
        assert resp.status == HTTPStatus.OK
        output_info = await resp.json()
        assert output_info['access'] == 'RED'
        assert output_info['role'] == 'PURPLE'
        assert output_info['can_write'] is False

    async def test_get_health_for_purple_api_key(self, api_v2_client):
        resp = await api_v2_client.get('/api/v2/health', headers={'KEY': 'PURPLEADMIN123'})
        assert resp.status == HTTPStatus.OK
        output_info = await resp.json()
        assert output_info['access'] == 'RED'
        assert output_info['role'] == 'PURPLE'
        assert output_info['can_write'] is False
