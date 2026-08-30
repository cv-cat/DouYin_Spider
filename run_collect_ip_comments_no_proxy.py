"""Run collect_ip_comments with inherited proxy variables removed."""

import os


for name in (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
):
    os.environ.pop(name, None)

from collect_ip_comments import main


if __name__ == "__main__":
    raise SystemExit(main())
