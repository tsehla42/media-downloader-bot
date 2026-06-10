# Guest API in Group Chats

How the guest API works when users mention the bot in group chats.

## Overview

When a user mentions `@botname` in a group chat, the bot receives a `guest_message` update and can reply using `answerGuestQuery()`.

## Flow

1. User sends message mentioning `@botname` with a URL
2. Telegram sends `guest_message` update to bot
3. Bot extracts URL from message text
4. Bot downloads media using platform handlers
5. Bot uploads file to storage channel to get `file_id`
6. Bot replies via `answerGuestQuery()` with InlineQueryResult

## Key Points

- Bot only sees the specific message it was tagged in
- Bot can see replies to that specific message
- Bot CANNOT see other messages in the group
- Bot CANNOT see chat member list
- Up to 3 guest bots can be mentioned per message

## Example

User sends:
```
@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/
```

Bot receives:
```json
{
  "guest_message": {
    "message_id": 123,
    "from": {"id": 12345678, "first_name": "Alice"},
    "chat": {"id": -1003804964305, "type": "supergroup"},
    "text": "@mmebodevbot https://vt.tiktok.com/ZS9Gg6dGp/",
    "guest_query_id": "2697475888970155636",
    "guest_bot_caller_chat": {"id": -1003804964305}
  }
}
```

Bot replies via `answerGuestQuery()`:
```python
await context.bot.answer_guest_query(
    guest_query_id="2697475888970155636",
    result={
        "type": "video",
        "id": "123",
        "video_file_id": "BAACAgIAAxk...",
        "title": "TikTok Video"
    }
)
```

## Implementation

```python
# src/guest.py
async def handle_guest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle guest_message updates."""
    guest_msg = update.guest_message
    caller_id = guest_msg.from_user.id
    guest_query_id = guest_msg.guest_query_id
    
    # Extract URL from message
    url = extract_url(guest_msg.text)
    if not url:
        # Reply with error
        await context.bot.answer_guest_query(
            guest_query_id=guest_query_id,
            result={
                "type": "article",
                "id": "error",
                "title": "No URL found",
                "input_message_content": {"message_text": "Please include a URL to download"}
            }
        )
        return
    
    # Download media
    # ... platform detection and download logic ...
    
    # Upload to storage channel
    file_id = await upload_to_storage(file_path, context)
    
    # Reply with result
    await context.bot.answer_guest_query(
        guest_query_id=guest_query_id,
        result={
            "type": "video",
            "id": str(message_id),
            "video_file_id": file_id,
            "title": title
        }
    )
```

## Related

- [Guest Mode](../guest-mode/) - Full guest mode documentation
- [Request Logging](../logs/requests.md) - How guest requests are logged
