from builder.header import Header


class _Auth:
    def __init__(self):
        self.calls = []

    def session_dtrait_header(self, api, **kwargs):
        self.calls.append((api, kwargs))
        assert kwargs["strict"] is True
        assert kwargs["allow_static"] is False
        return "d0_rsa_aes"


def test_write_header_requires_path_bound_dtrait():
    auth = _Auth()
    headers = Header().with_session_dtrait("/aweme/v1/web/commit/item/digg/", auth)

    assert headers.get()["x-tt-session-dtrait"] == "d0_rsa_aes"
    assert auth.calls[0][0] == "/aweme/v1/web/commit/item/digg/"

