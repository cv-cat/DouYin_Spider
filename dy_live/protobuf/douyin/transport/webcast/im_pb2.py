"""Generated protocol buffer code."""
from google.protobuf import descriptor as _descriptor
from google.protobuf import descriptor_pool as _descriptor_pool
from google.protobuf import symbol_database as _symbol_database
from google.protobuf.internal import builder as _builder
_sym_db = _symbol_database.Default()
DESCRIPTOR = _descriptor_pool.Default().AddSerializedFile(b'\n\x1atransport/webcast/im.proto\x12\x14transport.webcast.im"(\n\nPushHeader\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t"\xd0\x01\n\tPushFrame\x12\r\n\x05SeqID\x18\x01 \x01(\x04\x12\r\n\x05LogID\x18\x02 \x01(\x04\x12\x0f\n\x07service\x18\x03 \x01(\x05\x12\x0e\n\x06method\x18\x04 \x01(\x05\x121\n\x07headers\x18\x05 \x03(\x0b2 .transport.webcast.im.PushHeader\x12\x18\n\x10payload_encoding\x18\x06 \x01(\t\x12\x14\n\x0cpayload_type\x18\x07 \x01(\t\x12\x0f\n\x07payload\x18\x08 \x01(\x0c\x12\x10\n\x08LodIDNew\x18\t \x01(\t"\xc9\x01\n\x0bPayloadInIm\x12A\n\x08Payloads\x18\x01 \x03(\x0b2/.transport.webcast.im.PayloadInIm.PayloadsEntry\x12\x14\n\x0cCompressType\x18\x02 \x01(\x05\x1a/\n\rPayloadsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\x0c:\x028\x01"0\n\x10CompressTypeEnum\x12\x08\n\x04NONE\x10\x00\x12\x08\n\x04ZLIB\x10\x01\x12\x08\n\x04ZSTD\x10\x02"\x80\x04\n\x07Request\x12\x0f\n\x07live_id\x18\x01 \x01(\x03\x12\x0b\n\x03aid\x18\x02 \x01(\x03\x12\x0f\n\x07room_id\x18\x03 \x01(\t\x12\x10\n\x08identity\x18\x04 \x01(\t\x12\x10\n\x08last_rtt\x18\x05 \x01(\t\x12\x14\n\x0cinternal_ext\x18\x06 \x01(\t\x12\x0e\n\x06cursor\x18\x07 \x01(\t\x12\x11\n\tdevice_id\x18\x08 \x01(\t\x12\x11\n\tunique_id\x18\t \x01(\t\x12\x17\n\x0fdevice_platform\x18\n \x01(\t\x12\x14\n\x0capp_language\x18\x0b \x01(\t\x12\x14\n\x0cversion_code\x18\x0c \x01(\t\x12\x1b\n\x13update_version_code\x18\r \x01(\t\x12\x19\n\x11resp_content_type\x18\x0e \x01(\t\x12\x13\n\x0bget_history\x18\x0f \x01(\t\x12\n\n\x02ac\x18\x10 \x01(\t\x12\x13\n\x0bkeep_method\x18\x11 \x01(\t\x12\x0e\n\x06stress\x18\x12 \x01(\t\x12\x10\n\x08recv_cnt\x18\x13 \x01(\x03\x12\x11\n\tparse_cnt\x18\x14 \x01(\x03\x12\x12\n\nfetch_rule\x18\x15 \x01(\t\x12\x10\n\x08ab_group\x18\x16 \x01(\t\x12\x13\n\x0blive_cursor\x18\x17 \x01(\t\x12\x13\n\x0bsub_room_id\x18\x18 \x01(\t\x12\x1e\n\x16need_persist_msg_count\x18\x19 \x01(\x03"\xb4\x03\n\x08Response\x12/\n\x08messages\x18\x01 \x03(\x0b2\x1d.transport.webcast.im.Message\x12\x0e\n\x06cursor\x18\x02 \x01(\t\x12\x16\n\x0efetch_interval\x18\x03 \x01(\x03\x12\x0b\n\x03now\x18\x04 \x01(\x03\x12\x14\n\x0cinternal_ext\x18\x05 \x01(\t\x12\x12\n\nfetch_type\x18\x06 \x01(\x05\x12E\n\x0croute_params\x18\x07 \x03(\x0b2/.transport.webcast.im.Response.RouteParamsEntry\x12\x1a\n\x12heartbeat_duration\x18\x08 \x01(\x03\x12\x10\n\x08need_ack\x18\t \x01(\x08\x12\x13\n\x0bpush_server\x18\n \x01(\t\x12\x13\n\x0blive_cursor\x18\x0b \x01(\t\x12\x17\n\x0fhistory_no_more\x18\x0c \x01(\x08\x12\x14\n\x0cproxy_server\x18\r \x01(\t\x12\x16\n\x0epush_server_v2\x18\x0e \x01(\t\x1a2\n\x10RouteParamsEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01"\xb1\x02\n\x07Message\x12\x0e\n\x06method\x18\x01 \x01(\t\x12\x0f\n\x07payload\x18\x02 \x01(\x0c\x12\x0e\n\x06msg_id\x18\x03 \x01(\x03\x12\x10\n\x08msg_type\x18\x04 \x01(\x05\x12\x0e\n\x06offset\x18\x05 \x01(\x03\x12\x17\n\x0fneed_wrds_store\x18\x06 \x01(\x08\x12\x14\n\x0cwrds_version\x18\x07 \x01(\x03\x12\x14\n\x0cwrds_sub_key\x18\x08 \x01(\t\x12F\n\rmessage_extra\x18\t \x03(\x0b2/.transport.webcast.im.Message.MessageExtraEntry\x12\x11\n\ttenant_id\x18\n \x01(\t\x1a3\n\x11MessageExtraEntry\x12\x0b\n\x03key\x18\x01 \x01(\t\x12\r\n\x05value\x18\x02 \x01(\t:\x028\x01"\xa2\x01\n\x16PreviewHistoryResponse\x12G\n\x04data\x18\x01 \x01(\x0b29.transport.webcast.im.PreviewHistoryResponse.ResponseData\x1a?\n\x0cResponseData\x12/\n\x08messages\x18\x01 \x03(\x0b2\x1d.transport.webcast.im.Message')
_globals = globals()
_builder.BuildMessageAndEnumDescriptors(DESCRIPTOR, _globals)
_builder.BuildTopDescriptorsAndMessages(DESCRIPTOR, 'transport.webcast.im_pb2', _globals)
if _descriptor._USE_C_DESCRIPTORS == False:
    DESCRIPTOR._options = None
    _globals['_PAYLOADINIM_PAYLOADSENTRY']._options = None
    _globals['_PAYLOADINIM_PAYLOADSENTRY']._serialized_options = b'8\x01'
    _globals['_RESPONSE_ROUTEPARAMSENTRY']._options = None
    _globals['_RESPONSE_ROUTEPARAMSENTRY']._serialized_options = b'8\x01'
    _globals['_MESSAGE_MESSAGEEXTRAENTRY']._options = None
    _globals['_MESSAGE_MESSAGEEXTRAENTRY']._serialized_options = b'8\x01'
    _globals['_PUSHHEADER']._serialized_start = 52
    _globals['_PUSHHEADER']._serialized_end = 92
    _globals['_PUSHFRAME']._serialized_start = 95
    _globals['_PUSHFRAME']._serialized_end = 303
    _globals['_PAYLOADINIM']._serialized_start = 306
    _globals['_PAYLOADINIM']._serialized_end = 507
    _globals['_PAYLOADINIM_PAYLOADSENTRY']._serialized_start = 410
    _globals['_PAYLOADINIM_PAYLOADSENTRY']._serialized_end = 457
    _globals['_PAYLOADINIM_COMPRESSTYPEENUM']._serialized_start = 459
    _globals['_PAYLOADINIM_COMPRESSTYPEENUM']._serialized_end = 507
    _globals['_REQUEST']._serialized_start = 510
    _globals['_REQUEST']._serialized_end = 1022
    _globals['_RESPONSE']._serialized_start = 1025
    _globals['_RESPONSE']._serialized_end = 1461
    _globals['_RESPONSE_ROUTEPARAMSENTRY']._serialized_start = 1411
    _globals['_RESPONSE_ROUTEPARAMSENTRY']._serialized_end = 1461
    _globals['_MESSAGE']._serialized_start = 1464
    _globals['_MESSAGE']._serialized_end = 1769
    _globals['_MESSAGE_MESSAGEEXTRAENTRY']._serialized_start = 1718
    _globals['_MESSAGE_MESSAGEEXTRAENTRY']._serialized_end = 1769
    _globals['_PREVIEWHISTORYRESPONSE']._serialized_start = 1772
    _globals['_PREVIEWHISTORYRESPONSE']._serialized_end = 1934
    _globals['_PREVIEWHISTORYRESPONSE_RESPONSEDATA']._serialized_start = 1871
    _globals['_PREVIEWHISTORYRESPONSE_RESPONSEDATA']._serialized_end = 1934