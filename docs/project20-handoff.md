# 项目 17 → 项目 20 评论交接协议

项目 17 负责筛选评论并生成批次，项目 20 负责在浏览器中匹配并转发。

## ID 约定

- `command_id`：整批任务的唯一 ID，用于追踪和幂等重试。
- `targets[].comment_id`：单条抖音评论 ID，来源于抓包字段 `cid`。
- 两者不能互换。项目 20 优先且严格按 `comment_id` 匹配；缺少该字段时才使用“完整正文 + 作者昵称”。

## 上游生成命令

```powershell
python collect_ip_comments.py "https://www.douyin.com/video/123" `
  --region 湖北 `
  --output datas/ip_comments.json `
  --handoff-output datas/project20_command.json
```

如需重试同一批次，增加 `--command-id` 并复用原值。命令结束时会输出 `command_id` 和交接文件路径。

## MCP 调用

将生成的 JSON 完整作为项目 20 `submit_comment_command` 的 `command` 参数，并显式传入 `confirm_send: true`。真实转发必须由调用方明确确认。

```json
{
  "command": {
    "schema_version": "douyin.comment-forward.v1",
    "command_id": "dy-123-a1b2c3d4e5f6",
    "video_url": "https://www.douyin.com/video/123",
    "aweme_id": "123",
    "targets": [
      {
        "comment_id": "comment-1",
        "author_nickname": "Alice",
        "comment_text": "目标评论"
      }
    ]
  },
  "confirm_send": true
}
```

同一 MCP 进程内重复提交相同 `command_id` 和相同内容，会返回已有运行状态；相同 `command_id` 携带不同内容会被拒绝。
