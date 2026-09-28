import re

import dy_live.protobuf.douyin.bizIm.webcast.data_pb2 as data
import dy_live.protobuf.douyin.bizIm.webcast.im_pb2 as im


def format_user(t: data.TextPieceUser) -> str:
    u: data.User = t.user
    return f'{u.nickname}\u200b({u.id})'


def format_string(t: str) -> str:
    return t


def format_image(t: data.TextPieceImage) -> str:
    r = ''
    if t.image.url_list:
        r = '[image](' + t.image.url_list[0] + ')'
    return r


def format_gift(t: data.TextPieceGift) -> str:
    return f'{t.name_ref.default_pattern}(ID {t.gift_id})'


formatters = {
    'user': format_user,
    'string': format_string,
    '': format_string,
    'image': format_image,
    'gift': format_gift,
}


# renderer for webcast.data.Text
def render_text(text: data.Text) -> str:
    pattern: str = text.default_pattern
    pieces = text.pieces
    result = pattern
    for m in re.findall(r'\{[^}]+\}', pattern):
        if ':' in m:
            i, k = m[1:-1].split(':')
        else:
            i, k = m[1:-1], 'string'
        v = getattr(pieces[int(i)], k + '_value')

        t = formatters[k](v)

        result = result.replace(m, t)
    return result
