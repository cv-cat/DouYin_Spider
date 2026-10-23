from datetime import datetime
import json
from types import SimpleNamespace

from google.protobuf import json_format
from google.protobuf.message import Message

from .renderer import *
from .compression import *


def json_loads_object(s: str | bytes | bytearray):
    return json.loads(s, object_hook=lambda d: SimpleNamespace(**d))


def format_readable_time(ts: int, mili=False):
    if isinstance(ts, float):
        ts *= 1000
        mili = True
    ts = int(ts)
    if mili:
        return datetime.fromtimestamp(ts / 1000).strftime(f'%Y-%m-%d %H:%M:%S.{ts%1000:03}')
    else:
        return datetime.fromtimestamp(ts).strftime('%Y-%m-%d %H:%M:%S')


def parse_readable_time(ts: str):
    return datetime.strptime(ts.split('.', 1)[0], '%Y-%m-%d %H:%M:%S').timestamp()


def message_to_json(m: Message):
    return json_format.MessageToJson(m, preserving_proto_field_name=True, ensure_ascii=False, indent=None)
