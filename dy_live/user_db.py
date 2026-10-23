import hashlib
import os
from typing import Any, Callable, List

from rocksdict import Rdict, Options

from google.protobuf.message import Message
from google.protobuf.descriptor import FieldDescriptor
from google.protobuf.json_format import ParseDict
from dy_live.protobuf.douyin.bizIm.webcast.data_pb2 import User
from dy_live.protobuf.douyin.bizIm.webcast import im_pb2 as im
from dy_live.protobuf.douyin.bizIm.webcast import data_pb2 as data

''' See gatherUsers() below
ActivityEmojiGroupsMessage
AssetEffectUtilMessage
AudioChatMessage
BattleEndPunishMessage
BattlePowerContainerMessage
BattleRankSeasonMessage
BattleStatusMessage
BattleTeamTaskMessage
BindingGiftMessage
ChatLikeMessage
ChatMessage
CommonDotMessage
ControlMessage
DecorationModifyMethod
DecorationUpdateMessage
EasterEggDataMessage
EmojiChatMessage
ExhibitionChatMessage
FansclubMessage
GiftMessage
GiftPlayEventMessage
GiftSortMessage
HotChatMessage
InRoomBannerMessage
InteractEffectMessage
LightGiftMessage
LikeMessage
LinkerContributeMessage
LinkMessage
LinkMicArmiesMethod
LinkMicBattleFinishMethod
LinkMicBattleMethod
LinkMicMethod
LinkmicPlayModeUpdateScoreMessage
LinkSettingNotifyMessage
LotteryDrawResultEventMessage
LotteryEventNewMessage
LowPcuGuideMessage
LuckyBoxEndMessage
LuckyBoxMessage
LuckyBoxRewardMessage
LuckyBoxTempStatusMessage
MemberMessage
NotifyEffectMessage
PrivilegeScreenChatMessage
PrizeNoticeMessage
ProfitGameStatusMessage
ProfitInteractionScoreMessage
RanklistHourEntranceMessage
ResidentGuestMessage
RoomCommentTopicMessage
RoomDataSyncMessage
RoomMessage
RoomNotifyMessage
RoomRankMessage
RoomStatsMessage
RoomStreamAdaptationMessage
RoomUserSeqMessage
ScreenChatMessage
SocialMessage
ToastMessage
'''


def _isFieldRepeated(field) -> bool:
    """both map<> and repeated"""
    try:
        # TODO upgrade requirement of google protobuf to >= 7.x
        return field.is_repeated
    except AttributeError:
        return field.label == FieldDescriptor.LABEL_REPEATED


def clearRepeatedFieldsForMerge(m: Message, m_: Message):
    for field, value in m_.ListFields():
        if _isFieldRepeated(field):
            m.ClearField(field.name)
        elif field.message_type is not None:
            clearRepeatedFieldsForMerge(getattr(m, field.name), value)


KNOWN_USER_TYPES = [
    User,
    data.BattleUserInfo.BaseUserInfo,
    im.LinkMicArmies.UserArmies.UserArmy,
    data.BattleArmy.RankUser,
]


def userFromKnownObjects(o: Message) -> User | None:
    if isinstance(o, User):
        return o
    elif isinstance(o, data.BattleUserInfo.BaseUserInfo):
        u = User()
        u.id = o.user_id
        u.id_str = o.user_id_str
        u.nickname = o.nick_name
        u.gender = o.gender
        u.sec_uid = o.sec_uid
        u.avatar_thumb.CopyFrom(o.avatar_thumb)
        u.user_open_id = o.open_id
        return u
    elif isinstance(o, im.LinkMicArmies.UserArmies.UserArmy):
        u = User()
        u.id = o.user_id
        u.nickname = o.nickname
        u.avatar_thumb.CopyFrom(o.avatar_thumb)
        u.user_open_id = o.open_id
        return u
    elif isinstance(o, data.BattleArmy.RankUser):
        u = User()
        u.id = o.user_id
        u.id_str = o.user_id_str
        u.nickname = o.nickname
        u.webcast_uid = o.webcast_uid
        u.avatar_thumb.CopyFrom(o.avatar_thumb)
        u.user_open_id = o.open_id
        return u
    return None


def _getMessageField(m: Message, path: str, result: List[Any]):
    if m is None or path is None:
        return
    while (m is not None) and len(path) > 0:
        dot = path.find('.')
        dot = len(path) if dot == -1 else dot
        field, path = path[:dot], path[dot + 1:]
        if field.endswith('[]'):
            for e in getattr(m, field[:-2]):
                _getMessageField(e, path, result)
            return
        elif field.endswith('{}'):
            for e in getattr(m, field[:-2]).values():
                _getMessageField(e, path, result)
            return
        else:
            if not m.HasField(field):  # field is not set
                return
            m = getattr(m, field)
    result.append(m)


def getMessageField(m: Message, path: str) -> List[Any]:
    result = []
    _getMessageField(m, path, result)
    return result


def getMessageFields(m: Message, paths: List[str]) -> List[Any]:
    result = []
    for path in paths:
        _getMessageField(m, path, result)
    return result


def visitObjectInMessage(m: Message, Ts: List[type], func: Callable) -> None:
    """
    Ts: object types
    """
    if type(m) in Ts:
        func(m)
        return
    if not isinstance(m, Message):
        return
    for field, value in m.ListFields():
        if _isFieldRepeated(field):
            if (field.message_type is not None) and field.message_type.GetOptions().map_entry:  # map<> field
                for k, v in value.items():
                    visitObjectInMessage(k, Ts, func)
                    visitObjectInMessage(v, Ts, func)
            else:  # repeated field
                for e in value:
                    visitObjectInMessage(e, Ts, func)
        else:
            visitObjectInMessage(value, Ts, func)


def getObjectFromMessageRecursive(m: Message, Ts: List[type]) -> List[Any]:
    result = []
    visitObjectInMessage(m, Ts, lambda o: result.append(o))
    return result


class UserDB():

    def __init__(self, path: str = './user'):
        os.makedirs(path, exist_ok=True)
        options = Options(raw_mode=False)
        options.create_if_missing(True)
        # options.load_latest(db_path)
        self.db = Rdict(path, options=options)
        self._count = len([*self.db.keys()])

    def __del__(self):
        if hasattr(self, 'db'):
            self.db.close()

    def flush(self):
        self.db.flush()

    def get(self, id: int) -> User | None:
        b = self.db.get(id)
        if b:
            u = User.FromString(b)
            return u

    def __getitem__(self, key: int) -> User | None:
        return self.get(key)

    def count(self) -> int:
        return self._count

    def update(self, u_: User):
        u_ = userFromKnownObjects(u_)
        if u_ is None:
            return
        id = u_.id or int(u_.id_str or 0)
        if id in (0, 111111):
            return
        u_bytes = self.db.get(id)
        if u_bytes:
            u = User.FromString(u_bytes)
            clearRepeatedFieldsForMerge(u, u_)
            u.MergeFrom(u_)
            self.db[id] = u.SerializeToString()
        else:
            self._count += 1
            self.db[id] = u_.SerializeToString()

    def updateMany(self, users: List['User']):
        for u in users:
            self.update(u)

    def updateFromFields(self, m: Message, paths: List[str]):
        for path in paths:
            self.updateFromField(m, path)

    def updateFromField(self, m: Message, path: str):
        self.updateMany(getMessageField(m, path))

    def updateFromDict(self, u_: dict):
        u = ParseDict(u_, User(), ignore_unknown_fields=True)
        self.update(u)

    def updateFromMessageRecursive(self, m: Message):
        visitObjectInMessage(m, KNOWN_USER_TYPES, self.update)


def gatherUsers(user_db: 'UserDB', method: str, m: Message):
    user_object_field = {
        'AssetEffectUtilMessage': ['common.user'],
        'AudioChatMessage': ['user', 'rtf_content.pieces[].user_value.user'],
        'BindingGiftMessage': ['msg.user'],
        'ChatMessage': ['user', 'rtf_content.pieces[].user_value.user', 'rtf_content_v2.pieces[].user_value.user'],
        'EasterEggDataMessage': ['battle_easter_egg_info.user_map{}'],
        'EmojiChatMessage': ['user'],
        'ExhibitionChatMessage': ['display_text.pieces[].user_value.user'],
        'FansclubMessage': ['user'],
        'GiftMessage': ['user', 'to_user'],
        'ItemShareMessage': ['share_text.pieces[].user_value.user'],
        'LikeMessage': ['user'],
        'LinkMessage': None,  # None for recursive way
        'LinkMicArmiesMethod': ['user_armies_list[].user_armies[]'],
        'LinkMicBattleFinishMethod': ['battle_armies[].rank_list[]', 'user_infos{}.user'],
        'LinkMicBattleMethod': ['user_infos{}.user'],
        'LinkmicPlayModeUpdateScoreMessage': ['from_user', 'to_user'],
        'LuckyBoxMessage': ['user'],
        'MemberMessage': ['user'],  # Do we really need to know about random users ?
        'NotifyEffectMessage': ['text_v2.display_items[].text_item.text.pieces[].user_value.user'],
        'PrivilegeScreenChatMessage': ['user'],
        'RoomMessage': ['common.display_text.pieces[].user_value.user'],
        'RoomNotifyMessage': ['common.display_text.pieces[].user_value.user'],
        'RoomRankMessage': ['audience_ranks[].user'],
        'RoomUserSeqMessage': ['ranks[].user'],
        'ScreenChatMessage': ['user'],
        'SocialMessage': ['user'],
        'GroupLiveMemberChangeMessage': ['members[].user'],
        "RoomIntroMessage": ['user'],
    }
    paths = user_object_field.get(method, None)
    if method == 'MemberMessage':
        user_db.updateMany(u for u in getMessageFields(m, paths) if u.pay_grade.level > 10)
    elif method in user_object_field:
        if paths is None:
            user_db.updateFromMessageRecursive(m)
        else:
            user_db.updateFromFields(m, paths)


def dump(path: str):
    user = UserDB(path)
    print(f'{"ID":>20} {"pay grade level":>16} {"fans club level":>16}  {"nickname":16}')
    print(f'{"-" * 20} {"-" * 16} {"-" * 16}  {"-" * 8}')
    for i, u in user.db.items():
        u = user[i]
        print(f'{i:>20} {u.pay_grade.level:16} {u.fans_club.data.level:16} {u.nickname:16}')


if __name__ == '__main__':
    import shutil
    from google.protobuf.json_format import Parse
    import dy_live.protobuf.douyin.bizIm.webcast.im_pb2 as im

    shutil.rmtree('./user_db_test', ignore_errors=True)

    user = UserDB('./user_db_test')

    s = r'''{ "common": { "method": "WebcastNotifyEffectMessage" }, "text_v2": { "display_items": [ { "display_item_type": 2, "text_item": { "text": { "key": "privilege_grade_level_up", "default_pattern": "{0:user} 升级至Lv.{1:string}", "default_format": { "color": "#ffffff", "weight": 400, "use_remote_clor": true }, "pieces": [ { "type": 11, "format": { "color": "#ffffff", "weight": 400, "use_remote_clor": true }, "user_value": { "user": { "id": "78978777887979", "nickname": "测试用户" } } }, { "type": 1, "format": { "color": "#ffffff", "weight": 400, "use_remote_clor": true }, "string_value": "31" } ] } } } ] }
    }'''

    m = Parse(s, im.NotifyEffectMessage())
    user.updateFromField(m, 'text_v2.display_items[].text_item.text.pieces[].user_value.user')

    print(
        [user[k].nickname for k in user.db.keys()]
    )

    print(getObjectFromMessageRecursive(m, [str]))

    s2 = r'''{"common": {"method": "WebcastChatMessage", "room_id": "7683537420911479567"}, "user": {"id": "9999999999999", "short_id": "2222222", "nickname": "猜不猜.", "gender": 1, "level": 1}, "content": "@沐光海德  这个好", "event_time": "1788969826", "individual_chat_priority": 80, "rtf_content_v2": {"key": "chat_rtf_content", "default_pattern": "{0:user}{1:string}", "default_format": {"color": "#ffffffff", "weight": 400}, "pieces": [{"type": 11, "format": {"color": "#8CE7FF", "weight": 400, "use_remote_clor": true}, "user_value": {"user": {"id": "8888888888888888", "short_id": "111111111", "nickname": "沐光海德", "gender": 1, "follow_info": {"following_count": "5", "follower_count": "5", "follow_status": "2", "follower_count_str": "0", "following_count_str": "0"}}, "self_show_real_name": true, "left_additional_content": "@"}}, {"type": 1, "format": {"color": "#FFFFFF", "weight": 400, "use_remote_clor": true}, "string_value": "  这个好"}]}}
    '''
    m2 = Parse(s2, im.ChatMessage())
    print(getObjectFromMessageRecursive(m2, [User]))

    dump("user_db_test")
