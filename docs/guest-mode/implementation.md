# Guest Mode Technical Reference

> **Session date:** 2026-06-05

## Summary

Implemented Telegram Bot API 10.0 Guest Mode for the media downloader bot. Users can now tag @botname in ANY chat (groups, P2P, or chats the bot isn't in) with a URL to download media.

## Research Phase

### Telegram Bot API Updates Found

**Bot API 10.0 (May 8, 2026)** — Guest Mode:
- Bots can receive messages and reply in chats they're NOT members of
- Users mention bot with `@username` in any chat
- Bot receives `guest_message` update (separate from `message`)
- Bot replies using `answerGuestQuery()` method (not `sendMessage`)
- Bot only sees the specific message it was tagged in + replies to that message
- Bot CANNOT see chat member list or other messages
- Up to 3 guest bots can be mentioned per message
- Enable via BotFather → MiniApp → enable "Guest Mode"

**Bot API 9.6 (April 3, 2026)** — Managed Bots:
- "Manager bot" creates and controls child bots for users

**Bot API 9.5 (March 1, 2026)** — Streaming responses, sendMessageDraft

### Library Status
- `python-telegram-bot` git master (commit `0fb567818036`) — full Bot API 10.0 support
- PR #5239 merged 2026-06-07. PR #5229 ("Full Support for Bot API 10.0") merged 2026-06-09
- Installed via `pip install python-telegram-bot @ git+https://github.com/python-telegram-bot/python-telegram-bot.git@master`

### Key API Fields (Bot API 10.0)
- `Update.guest_message` — the update type for guest queries
- `Message.from_user` — who mentioned the bot (Telegram sends `from` field, ptb maps to `from_user`)
- `Message.guest_bot_caller_chat` — which chat it was mentioned in
- `Message.guest_query_id` — ID for replying
- Method `answerGuestQuery(guest_query_id, result: InlineQueryResult)` — to reply

### answerGuestQuery Format
- Uses `InlineQueryResult` format (same as inline mode)
- Text: `InlineQueryResultArticle` with `input_message_content.message_text`
- Photo: `InlineQueryResultPhoto` with `photo_file_id`
- Video: `InlineQueryResultVideo` with `video_file_id`

## Design Decisions

### Chosen Approach: ptb Native Handler
After python-telegram-bot merged Bot API 10.0 support (PR #5229, 2026-06-09), the implementation was migrated from raw httpx-based GuestModePoller to native ptb handler:
- `MessageHandler(filters.UpdateType.GUEST_MESSAGE, handle_guest)` — standard ptb handler
- `context.bot.answer_guest_query()` — ptb native API call
- Standard `app.run_polling()` — no custom polling loop needed

### Handler Ordering (Critical)
`filters.TEXT` matches guest messages because `Update.effective_message` now includes `guest_message`. The guest handler MUST be registered BEFORE the `handle_url` text handler in `bot.py`, otherwise the text handler consumes the update first.

### Caller Identification
Telegram sends caller info as the standard `from` field on the message. ptb maps this to `Message.from_user`, NOT `Message.guest_bot_caller_user`. The `guest_bot_caller_user` attribute exists on the Message class but is not populated by the API.

### InlineQueryResult as Raw Dicts
ptb's `InlineQueryResultVideo`/`InlineQueryResultPhoto` constructors require `video_url`/`photo_url` parameters. When `video_file_id`/`photo_file_id` is passed via `api_kwargs`, Telegram still tries to fetch the placeholder URL and fails with "Failed to get http url content". Solution: build results as raw dicts with `video_file_id`/`photo_file_id` directly, bypassing ptb's type system.

### Storage Channel for file_ids
`answerGuestQuery` requires InlineQueryResult with `file_id`s (not URLs or local paths). Files are uploaded to a private storage channel (`STORAGE_CHANNEL_ID`) via httpx to get permanent `file_id`s that Telegram recognizes.

### Authorization
Same `ALLOWED_USER_IDS` check via `is_user_allowed()` (public wrapper in auth.py).

### Reply Behavior
- Always reply to the tag message (not the URL message)
- URL extraction checks both tag message AND replied-to message
- Guest reply-to-retry doesn't conflict with existing reply-to-retry (different update types)

## Implementation

### Branch: `feature/guest-mode`

### Files Created
- `src/guest.py` — Guest message handler, download pipeline, InlineQueryResult builders (raw dicts), file upload to storage channel
- `tests/test_guest.py` — Unit tests for guest handler and InlineQueryResult builders

### Files Modified
- `src/bot.py` — Guest handler registered BEFORE text handler, `allowed_updates` includes `guest_message` when enabled
- `src/config.py` — Added `GUEST_MODE_ENABLED` (default: false), `STORAGE_CHANNEL_ID`
- `src/auth.py` — Added public `is_user_allowed()` wrapper
- `requirements.txt` — Added `httpx`
- `.env` — Added `GUEST_MODE_ENABLED=true`, `STORAGE_CHANNEL_ID`
- `.env.example` — Added GUEST_MODE_ENABLED and STORAGE_CHANNEL_ID documentation

### Key Commits
```
2570770 fix bot not building
297b5d3 refactor(bot): revert to standard polling with native guest message handler
fe70aef refactor(guest): replace GuestModePoller with ptb native handle_guest handler
b548691 deps: pin python-telegram-bot to git master for Bot API 10.0 support
```

### Test Results
- Tests passing (209 existing + 25 new guest tests)

## Code Review Findings (Fixed)

1. **Dual-polling bug** (Critical) — GuestModePoller and app.updater both ran getUpdates. Fixed by branching on GUEST_MODE_ENABLED.
2. **httpx client per iteration** — Created new client on every poll. Fixed by reusing instance attribute.
3. **Missing os.makedirs(output_dir)** — Video downloads would fail. Fixed.
4. **_media_group_result discards file_ids** — Now shows first image instead of text fallback.
5. **Private _is_allowed import** — Added public `is_user_allowed()` wrapper.
6. **GUEST_MODE_ENABLED default** — Changed from "true" to "false" until production-ready.
7. **Handler ordering** (Critical) — `filters.TEXT` matches guest messages via `effective_message`. Guest handler must be registered BEFORE text handler.
8. **Caller identification** — `guest_bot_caller_user` is not populated by the API. Use `from_user` (Telegram sends `from`, ptb maps to `from_user`).
9. **InlineQueryResult placeholder URLs** — ptb's `InlineQueryResultVideo`/`Photo` require placeholder URLs that Telegram tries to fetch. Fixed by using raw dicts with `video_file_id`/`photo_file_id`.
10. **Storage channel** — Replaced Saved Messages (`chat_id: "me"`) with dedicated storage channel to avoid pollution.

## Known Limitations

1. **Media groups** — InlineQueryResult doesn't support media groups. Multi-image posts show only the first image.
2. **Storage channel required** — Guest mode needs a private channel (`STORAGE_CHANNEL_ID`) for file uploads to get `file_id`s. Bot must be admin with post permissions.
3. **httpx for uploads** — File uploads to storage channel still use raw httpx (not ptb). Could be replaced with ptb's `send_video`/`send_photo` methods.

## Migration Complete

The migration from raw httpx-based GuestModePoller to ptb native handler is complete:
- ✅ Standard `app.run_polling()` with `allowed_updates` including `guest_message`
- ✅ `MessageHandler(filters.UpdateType.GUEST_MESSAGE, handle_guest)` — native ptb handler
- ✅ `context.bot.answer_guest_query()` — ptb native API call
- ⚠️ File uploads to storage channel still use raw httpx (could be migrated to ptb)

## How to Enable

1. Open @BotFather → your bot settings → Mode Settings → enable "Guest Chat Mode"
2. Create a private channel (or use existing one)
3. Add bot as admin with post permissions
4. Forward a message from the channel to @userinfobot to get the channel ID
5. Set `GUEST_MODE_ENABLED=true` and `STORAGE_CHANNEL_ID=-100XXXXXXXXX` in `.env`
6. Deploy from `feature/guest-mode` branch
7. Tag `@yourbotname https://youtube.com/watch?v=xyz` in any chat where the bot is NOT a member

## UzbekGPT Research

Attempted to check https://git.hkr.at.by/cgit.cgi/uzbekgpt for implementation details, but the repo was not accessible via GitHub API or web fetch. The bot uses ollama with gemma4:31b-cloud model and already supports guest mode (Bot API 10.0).
