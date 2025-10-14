# -*- coding: utf-8 -*-
from fastapi.testclient import TestClient

import pytest
from z2p_svc.app import app


@pytest.fixture(name="client")
def _client():
    return TestClient(app)


def test_hello(client):
    """简单的起始测试
    :param client:
    :return:
    """
    resp = client.get("/")
    assert 200 == resp.status_code
    # 修复：实际响应包含version字段
    assert {"message": "Hello z2p", "version": "0"} == resp.json()