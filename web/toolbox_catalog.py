CRAWL_TOOL_GROUPS = [
    {
        "title": "作品与评论",
        "items": [
            {
                "label": "用户作品分页",
                "operation": "get_user_work_info",
                "fields": [
                    {"name": "user_url", "placeholder": "用户主页链接"},
                    {"name": "max_cursor", "placeholder": "max_cursor", "value": "0"},
                ],
            },
            {
                "label": "一级评论分页",
                "operation": "get_work_out_comment",
                "fields": [
                    {"name": "work_url", "placeholder": "作品链接"},
                    {"name": "cursor", "placeholder": "cursor", "value": "0"},
                ],
            },
            {
                "label": "全部一级评论",
                "operation": "get_work_all_out_comment",
                "fields": [
                    {"name": "work_url", "placeholder": "作品链接"},
                ],
            },
            {
                "label": "二级评论分页",
                "operation": "get_work_inner_comment",
                "fields": [
                    {"name": "comment_json", "placeholder": "一级评论 JSON", "kind": "textarea"},
                    {"name": "cursor", "placeholder": "cursor", "value": "0"},
                    {"name": "count", "placeholder": "count", "value": "3"},
                ],
            },
            {
                "label": "全部二级评论",
                "operation": "get_work_all_inner_comment",
                "fields": [
                    {"name": "comment_json", "placeholder": "一级评论 JSON", "kind": "textarea"},
                ],
            },
            {
                "label": "全部评论",
                "operation": "get_work_all_comment",
                "fields": [
                    {"name": "work_url", "placeholder": "作品链接"},
                ],
            },
        ],
    },
    {
        "title": "高级搜索",
        "items": [
            {
                "label": "通用搜索分页",
                "operation": "search_general_work",
                "fields": [
                    {"name": "query", "placeholder": "关键词"},
                    {"name": "sort_type", "placeholder": "排序", "value": "0"},
                    {"name": "publish_time", "placeholder": "发布时间", "value": "0"},
                    {"name": "offset", "placeholder": "offset", "value": "0"},
                    {"name": "search_range", "placeholder": "搜索范围"},
                    {"name": "filter_duration", "placeholder": "时长过滤"},
                    {"name": "content_type", "placeholder": "内容形式"},
                ],
            },
            {
                "label": "搜索用户指定数量",
                "operation": "search_some_user",
                "fields": [
                    {"name": "query", "placeholder": "关键词"},
                    {"name": "num", "placeholder": "数量", "value": "10"},
                ],
            },
            {
                "label": "搜索用户分页",
                "operation": "search_user",
                "fields": [
                    {"name": "query", "placeholder": "关键词"},
                    {"name": "offset", "placeholder": "offset", "value": "0"},
                    {"name": "num", "placeholder": "数量", "value": "25"},
                    {"name": "douyin_user_fans", "placeholder": "粉丝过滤"},
                    {"name": "douyin_user_type", "placeholder": "用户类型"},
                ],
            },
            {
                "label": "搜索直播分页",
                "operation": "search_live",
                "fields": [
                    {"name": "query", "placeholder": "关键词"},
                    {"name": "offset", "placeholder": "offset", "value": "0"},
                    {"name": "num", "placeholder": "数量", "value": "25"},
                ],
            },
            {
                "label": "搜索直播指定数量",
                "operation": "search_some_live",
                "fields": [
                    {"name": "query", "placeholder": "关键词"},
                    {"name": "num", "placeholder": "数量", "value": "10"},
                ],
            },
            {
                "label": "视频搜索指定数量",
                "operation": "search_some_video_work",
                "fields": [
                    {"name": "query", "placeholder": "关键词"},
                    {"name": "num", "placeholder": "数量", "value": "10"},
                    {"name": "sort_type", "placeholder": "排序", "value": "0"},
                    {"name": "publish_time", "placeholder": "发布时间", "value": "0"},
                    {"name": "filter_duration", "placeholder": "时长过滤"},
                ],
            },
            {
                "label": "视频搜索分页",
                "operation": "search_video_work",
                "fields": [
                    {"name": "query", "placeholder": "关键词"},
                    {"name": "offset", "placeholder": "offset", "value": "0"},
                    {"name": "count", "placeholder": "数量", "value": "16"},
                    {"name": "sort_type", "placeholder": "排序", "value": "0"},
                    {"name": "publish_time", "placeholder": "发布时间", "value": "0"},
                    {"name": "filter_duration", "placeholder": "时长过滤"},
                ],
            },
        ],
    },
    {
        "title": "收藏与关系",
        "items": [
            {
                "label": "用户喜欢列表",
                "operation": "get_user_favorite",
                "fields": [
                    {"name": "sec_id", "placeholder": "sec_id"},
                    {"name": "max_cursor", "placeholder": "max_cursor", "value": "0"},
                    {"name": "num", "placeholder": "数量", "value": "18"},
                ],
            },
            {
                "label": "收藏夹列表",
                "operation": "get_collect_list",
                "fields": [],
            },
            {
                "label": "移动收藏作品",
                "operation": "move_collect_aweme",
                "fields": [
                    {"name": "aweme_id", "placeholder": "aweme_id"},
                    {"name": "collect_name", "placeholder": "收藏夹名称"},
                    {"name": "collect_id", "placeholder": "collect_id"},
                ],
            },
            {
                "label": "移除收藏作品",
                "operation": "remove_collect_aweme",
                "fields": [
                    {"name": "aweme_id", "placeholder": "aweme_id"},
                    {"name": "collect_name", "placeholder": "收藏夹名称"},
                    {"name": "collect_id", "placeholder": "collect_id"},
                ],
            },
            {
                "label": "粉丝列表分页",
                "operation": "get_user_follower_list",
                "fields": [
                    {"name": "user_id", "placeholder": "user_id"},
                    {"name": "sec_id", "placeholder": "sec_id"},
                    {"name": "max_time", "placeholder": "max_time", "value": "0"},
                    {"name": "count", "placeholder": "数量", "value": "20"},
                ],
            },
            {
                "label": "粉丝指定数量",
                "operation": "get_some_user_follower_list",
                "fields": [
                    {"name": "user_id", "placeholder": "user_id"},
                    {"name": "sec_id", "placeholder": "sec_id"},
                    {"name": "num", "placeholder": "数量", "value": "20"},
                ],
            },
            {
                "label": "关注列表分页",
                "operation": "get_user_following_list",
                "fields": [
                    {"name": "user_id", "placeholder": "user_id"},
                    {"name": "sec_id", "placeholder": "sec_id"},
                    {"name": "max_time", "placeholder": "max_time", "value": "0"},
                    {"name": "count", "placeholder": "数量", "value": "20"},
                ],
            },
            {
                "label": "关注指定数量",
                "operation": "get_some_user_following_list",
                "fields": [
                    {"name": "user_id", "placeholder": "user_id"},
                    {"name": "sec_id", "placeholder": "sec_id"},
                    {"name": "num", "placeholder": "数量", "value": "20"},
                ],
            },
        ],
    },
    {
        "title": "通知与诊断",
        "items": [
            {
                "label": "通知分页",
                "operation": "get_notice_list",
                "fields": [
                    {"name": "min_time", "placeholder": "min_time", "value": "0"},
                    {"name": "max_time", "placeholder": "max_time", "value": "0"},
                    {"name": "count", "placeholder": "数量", "value": "10"},
                    {"name": "notice_group", "placeholder": "notice_group", "value": "700"},
                ],
            },
            {
                "label": "通知指定数量",
                "operation": "get_some_notice_list",
                "fields": [
                    {"name": "num", "placeholder": "数量", "value": "20"},
                    {"name": "notice_group", "placeholder": "notice_group", "value": "700"},
                ],
            },
            {
                "label": "推荐流",
                "operation": "get_feed",
                "fields": [
                    {"name": "count", "placeholder": "数量", "value": "20"},
                    {"name": "refresh_index", "placeholder": "refresh_index", "value": "2"},
                ],
            },
            {
                "label": "获取我的 uid",
                "operation": "get_my_uid",
                "fields": [],
            },
            {
                "label": "获取我的 sec_uid",
                "operation": "get_my_sec_uid",
                "fields": [],
            },
            {
                "label": "获取 device_id",
                "operation": "get_device_id",
                "fields": [],
            },
        ],
    },
]


LIVE_TOOL_GROUPS = [
    {
        "title": "直播商品与榜单",
        "items": [
            {
                "label": "直播商品分页",
                "operation": "get_live_production",
                "fields": [
                    {"name": "url", "placeholder": "直播间 URL"},
                    {"name": "room_id", "placeholder": "room_id"},
                    {"name": "author_id", "placeholder": "author_id"},
                    {"name": "offset", "placeholder": "offset", "value": "0"},
                ],
            },
            {
                "label": "全部直播商品",
                "operation": "get_all_live_production",
                "fields": [
                    {"name": "url", "placeholder": "直播间 URL"},
                ],
            },
            {
                "label": "直播商品详情",
                "operation": "get_live_production_detail",
                "fields": [
                    {"name": "url", "placeholder": "直播间 URL"},
                    {"name": "ec_promotion_id", "placeholder": "ec_promotion_id"},
                    {"name": "sec_author_id", "placeholder": "sec_author_id"},
                    {"name": "live_room_id", "placeholder": "live_room_id"},
                ],
            },
            {
                "label": "直播榜单",
                "operation": "get_rank_list",
                "fields": [
                    {"name": "room_id", "placeholder": "room_id"},
                    {"name": "anchor_id", "placeholder": "anchor_id"},
                    {"name": "sec_anchor_id", "placeholder": "sec_anchor_id"},
                ],
            },
            {
                "label": "直播房间详情",
                "operation": "get_webcast_detail",
                "fields": [
                    {"name": "user_id", "placeholder": "user_id"},
                    {"name": "room_id", "placeholder": "room_id"},
                    {"name": "url", "placeholder": "直播间 URL"},
                ],
            },
        ],
    },
]
