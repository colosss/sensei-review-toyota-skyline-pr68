"""Environment smoke only; these are not application findings."""
import socket

import pytest
import requests
import responses


def test_external_dns_is_blocked_by_review_runner():
    with pytest.raises(OSError, match='External DNS blocked'):
        socket.getaddrinfo('review-smoke.invalid', 443)


@responses.activate
def test_fake_integration_returns_only_synthetic_data():
    responses.add(responses.GET, 'https://review-smoke.invalid/sheet',
                  json={'students': [{'id': 'synthetic-A', 'position': 1}]}, status=200)
    result = requests.get('https://review-smoke.invalid/sheet', timeout=1).json()
    assert result == {'students': [{'id': 'synthetic-A', 'position': 1}]}
