import requests
import pytest

from src.public_census_http import PublicCensusHttpClient, PublicCensusHttpError


class _Session:
    def __init__(self, response):
        self.response = response
        self.headers = {}

    def get(self, *args, **kwargs):
        return self.response


def _response(body: bytes):
    response = requests.Response()
    response.status_code = 200
    response.reason = "OK"
    response._content = body
    response.url = "https://api.exchange.coinbase.com/products/BTC-USD/candles"
    response.headers = {"Content-Type": "application/json"}
    return response


def test_default_public_client_still_rejects_top_level_array(tmp_path):
    client = PublicCensusHttpClient(
        base_url="https://api.exchange.coinbase.com",
        source_name="test",
        raw_root=tmp_path,
    )
    client.session = _Session(_response(b"[[1,2,3,4,5,6]]"))
    with pytest.raises(PublicCensusHttpError, match="unexpected top-level JSON shape"):
        client.get_json("/products/BTC-USD/candles")
    assert len(client.raw_recorder.written_paths) == 1


def test_public_client_can_explicitly_accept_top_level_array_without_changing_default(tmp_path):
    client = PublicCensusHttpClient(
        base_url="https://api.exchange.coinbase.com",
        source_name="test",
        raw_root=tmp_path,
    )
    client.session = _Session(_response(b"[[1,2,3,4,5,6]]"))
    result = client.get_json(
        "/products/BTC-USD/candles",
        top_level_container="array",
    )
    assert result.payload == [[1, 2, 3, 4, 5, 6]]
    assert len(client.raw_recorder.written_paths) == 1


def test_public_client_rejects_unknown_top_level_container(tmp_path):
    client = PublicCensusHttpClient(
        base_url="https://api.exchange.coinbase.com",
        source_name="test",
        raw_root=tmp_path,
    )
    with pytest.raises(ValueError, match="top_level_container"):
        client.get_json("/x", top_level_container="scalar")
