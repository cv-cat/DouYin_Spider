from types import SimpleNamespace
from unittest.mock import patch

from dy_apis.douyin_api import DouyinAPI


class _Auth:
    cookie = {"s_v_web_id": "fp", "UIFID": "uifid"}
    webid = "webid"
    msToken = "mstoken"


def test_general_search_sends_selected_filter_values():
    response = SimpleNamespace(
        text="{}",
        status_code=200,
        headers={},
        json=lambda: {"data": []},
    )
    with patch("dy_apis.douyin_api.generate_a_bogus_pure", return_value="ab"), \
            patch("dy_apis.douyin_api.requests.get", return_value=response) as request:
        DouyinAPI.search_general_work(
            _Auth(), "猫", sort_type="2", publish_time="7",
            filter_duration="1-5", search_range="3", content_type="2",
        )

    query = request.call_args.kwargs["params"]
    assert query["search_source"] == "tab_search"
    assert query["is_filter_search"] == "1"
    assert query["filter_selected"] == (
        '{"sort_type":"2","publish_time":"7",'
        '"filter_duration":"1-5","search_range":"3","content_type":"2"}'
    )

