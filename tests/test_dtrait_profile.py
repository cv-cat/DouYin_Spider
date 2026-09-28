from utils.dtrait_features import build_blob
from utils.dtrait_profile import load_dtrait_profile


CAPTURED_BLOB = (
    "IAAAAADQIC0FVqIh4kBm/yLQO48ZI8SHsdUkUnQhRSUtc6pZJoXtgvcnqvUbwih5/"
    "ufyKR3SnsMqMtFjyisa3jq/LEbrp0It3oooWy6x8OwMLzYf+ukwKpioVDEAAAAAMi"
    "Zm67kzi/GgODSiHrKONRJqRnA2hZHFNjcbzZ0NOFhf5lQ5ucywezqnDTbrO0LJZ588"
    "JQFrBT3os+69Pnc1cw4/6hH+lkBcuWKWR5QWrJM="
)


def test_devtools_profile_rebuilds_captured_blob():
    profile = load_dtrait_profile()
    assert build_blob(profile) == CAPTURED_BLOB

