# Guest Mode Logging — Requirements (Implemented)

All requirements below have been implemented. This document is kept for reference.

## Status: ✅ Implemented

- Events renamed to `guest_request_received` / `guest_request_completed`
- Guest requests logged to `requests.jsonl` (via `requests_logger`)
- Structured `user`, `chat`, `reply` fields added
- `reply_to_retry` events split into `reply_to_retry_received` / `reply_to_retry_completed`
- Only logged when URL is present (no spam logging)

---

## Original Requirements

Previous behaviour of guest mode logging is good enough, we just need to move some entries and add more fields
```json
{"timestamp": "2026-06-10T20:41:50.042963+03:00", "level": "INFO", "message": "guest_message received", "event": "guest_message", "request_id": "8e314411", "guest_query_id": "2697475888970155636", "caller_id": 12345678, "caller_name": "Alice", "caller_username": "user_alice", "text": "@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/"}
{"timestamp": "2026-06-10T20:41:50.045858+03:00", "level": "INFO", "message": "guest_mode: processing URL", "url": "https://vt.tiktok.com/ZS9Gg6dGp/", "caller_id": 12345678, "guest_query_id": "2697475888970155636"}
{"timestamp": "2026-06-10T20:41:50.047014+03:00", "level": "INFO", "message": "download_video: running yt-dlp", "url": "https://vt.tiktok.com/ZS9Gg6dGp/"}
{"timestamp": "2026-06-10T20:41:52.808687+03:00", "level": "INFO", "message": "download_video: retrying with lower quality", "url": "https://vt.tiktok.com/ZS9Gg6dGp/"}
{"timestamp": "2026-06-10T20:42:00.042760+03:00", "level": "INFO", "message": "download_video: yt-dlp ok (fallback)", "url": "https://vt.tiktok.com/ZS9Gg6dGp/"}
{"timestamp": "2026-06-10T20:42:04.768463+03:00", "level": "INFO", "message": "guest_mode: reply sent", "url": "https://vt.tiktok.com/ZS9Gg6dGp/", "caller_id": 12345678, "guest_query_id": "2697475888970155636"}
```

- Make events `guest_message_received` and `guest_message_completed` to differentiate by event type
- Move these events in requests file
- Add more info in guest requests to differentiate by message type

By message type i mean that it should be cleary visible, if the message is a reply or not. I think we can do this:
add a field called `reply`. 
If user sends a plain message into a chat mentioning a bot with the URL in that same message, and it is not a reply, then of course we do not consider it as a reply.
If however user replies to some message by tagging bot on previous message, then we consider this a reply. We need to log not only caller and chat, but also the properties of the message that is replied to.

Current log:
```json
{"timestamp": "2026-06-10T20:41:50.042963+03:00", "level": "INFO", "message": "guest_message received", "event": "guest_message", "request_id": "8e314411", "guest_query_id": "2697475888970155636", "caller_id": 12345678, "caller_name": "Alice", "caller_username": "user_alice", "text": "@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/"}
```

Expected logs for non reply (1) and reply (2) messages:

```json
{"timestamp": "2026-06-10T20:41:50.042963+03:00", "level": "INFO", "message": "Guest request received", "event": "guest_request_received", "request_id": "8e314411", "guest_query_id": "2697475888970155636", "url": "@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/", "user": {"id": 123456789012345678, "name": "Alice", "username": "user_alice"}, "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}, "reply": null}

{"timestamp": "2026-06-10T20:41:50.042963+03:00", "level": "INFO", "message": "Guest request received", "event": "guest_request_received", "request_id": "8e314411", "guest_query_id": "2697475888970155636", "url": "@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/", "user": {"id": 123456789012345678, "name": "Alice", "username": "user_alice"}, "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}, "reply": {"user_id": 87654321, "name": "Bob", "username": "user_bob", "message": "message text here"}}
```

If the reply data is hard to get, then just use reply:true or false.

Note that we want Guest request received only when there is a URL, so the bot is not logging every spam message. This is possible to implement, cause in p2p messages, logs only appear if user sends an actual link

---

Here are the examples of `reply_to_retry` entries (now using `reply_to_retry_received` / `reply_to_retry_completed`):

```json

{"timestamp": "2026-06-09T21:46:26.777275+03:00", "level": "INFO", "message": "Reply to retry received", "event": "reply_to_retry_received", "request_id": "ab805f84", "url": "https://www.instagram.com/reel/DYYdI2DpEJE/?utm_source=ig_web_copy_link", "user": {"id": 87654321, "name": "Bob", "username": "user_bob"}, "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}}

{"timestamp": "2026-06-09T21:46:29.553513+03:00", "level": "INFO", "message": "Reply to retry completed", "event": "reply_to_retry_completed", "request_id": "ab805f84", "url": "https://www.instagram.com/reel/DYYdI2DpEJE/?utm_source=ig_web_copy_link", "platform": "instagram", "duration_ms": 2776, "success": true, "content_type": "video", "file_size_mb": 2.61, "user": {"id": 87654321, "name": "Bob", "username": "user_bob"}, "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}}

```

✅ Fixed: Events now use `reply_to_retry_received` and `reply_to_retry_completed` to match default logging behaviour.



Here are the examples of default `request_received` entries

```json

{"timestamp": "2026-06-09T23:48:18.190920+03:00", "level": "INFO", "message": "Request received", "event": "request_received", "request_id": "2b49ab85", "url": "https://youtube.com/shorts/K2OW0-_ne64", "user": {"id": 87654321, "name": "Bob", "username": "user_bob"}, "chat": {"id": 87654321, "name": null, "type": "private"}}

{"timestamp": "2026-06-09T23:48:23.302319+03:00", "level": "INFO", "message": "Request completed", "event": "request_completed", "request_id": "2b49ab85", "url": "https://youtube.com/shorts/K2OW0-_ne64", "platform": "youtube", "duration_ms": 5111, "success": false, "content_type": "video", "file_size_mb": 3.06, "user": {"id": 87654321, "name": "Bob", "username": "user_bob"}, "chat": {"id": 87654321, "name": null, "type": "private"}}

```
