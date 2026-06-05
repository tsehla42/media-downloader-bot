# Guest Mode Implementation Session — 2026-06-05

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
- `python-telegram-bot` 22.7 (latest, released Mar 2026) supports Bot API 9.5 only
- PR #5239 open for Bot API 10.0 support (not merged)
- `aiogram` 3.28.2 already supports Bot API 10.0

### Key API Fields (Bot API 10.0)
- `Update.guest_message` — the update type for guest queries
- `Message.guest_bot_caller_user` — who mentioned the bot
- `Message.guest_bot_caller_chat` — which chat it was mentioned in
- `Message.guest_query_id` — ID for replying
- Method `answerGuestQuery(guest_query_id, result: InlineQueryResult)` — to reply

### answerGuestQuery Format
- Uses `InlineQueryResult` format (same as inline mode)
- Text: `InlineQueryResultArticle` with `input_message_content.message_text`
- Photo: `InlineQueryResultPhoto` with `photo_file_id`
- Video: `InlineQueryResultVideo` with `video_file_id`

## Design Decisions

### Critical Constraint: One Polling Loop
Telegram allows only **one `getUpdates` session per bot token**. Two polling loops would fight each other and drop updates.

### Chosen Approach: Unified Polling
Replace `app.run_polling()` with a custom unified polling loop that:
1. Fetches ALL update types via raw httpx (`message`, `guest_message`, `callback_query`, `my_chat_member`)
2. Routes regular updates through python-telegram-bot's `Application.process_update()`
3. Routes guest updates to custom handler in `src/guest.py`

### Authorization
Same `ALLOWED_USER_IDS` check via `is_user_allowed()` (new public wrapper in auth.py).

### Reply Behavior
- Always reply to the tag message (not the URL message)
- URL extraction checks both tag message AND replied-to message
- Guest reply-to-retry doesn't conflict with existing reply-to-retry (different update types)

### Branch on GUEST_MODE_ENABLED
- `GUEST_MODE_ENABLED=true`: Use unified polling via GuestModePoller
- `GUEST_MODE_ENABLED=false`: Use standard `app.run_polling()` (no guest mode)

## Implementation

### Branch: `feature/guest-mode` (9 commits)

### Files Created
- `src/guest.py` — GuestModePoller with unified polling, guest message handling, download pipeline, InlineQueryResult builders
- `tests/test_guest.py` — 25 unit tests

### Files Modified
- `src/bot.py` — Branches on GUEST_MODE_ENABLED, unified polling loop
- `src/config.py` — Added `GUEST_MODE_ENABLED` (default: false)
- `src/auth.py` — Added public `is_user_allowed()` wrapper
- `requirements.txt` — Added `httpx`
- `.env` — Added `GUEST_MODE_ENABLED=true`
- `.env.example` — Added GUEST_MODE_ENABLED documentation

### Commits
```
a21aecb test(guest): add unit tests for InlineQueryResult builders and guest handler
11e7158 fix(bot): eliminate dual-polling bug — branch on GUEST_MODE_ENABLED, clean lifecycle
d86d239 fix(bot): preserve old run_polling as commented code for easy revert
70c7c24 feat(bot): integrate unified polling with GuestModePoller
fe549ac fix(guest): create output_dir correctly, show first image for media groups, clarify gallery-dl fallback
2738b17 feat(guest): add URL extraction, download pipeline, and InlineQueryResult builders
4a0e551 fix(guest): address code review — reuse httpx client, public auth API, default off
6280c38 feat(guest): add GuestModePoller with unified polling loop
f527a6d deps+config: add httpx and GUEST_MODE_ENABLED setting for guest mode
```

### Test Results
- 234 tests passing (209 existing + 25 new)

## Code Review Findings (Fixed)

1. **Dual-polling bug** (Critical) — GuestModePoller and app.updater both ran getUpdates. Fixed by branching on GUEST_MODE_ENABLED.
2. **httpx client per iteration** — Created new client on every poll. Fixed by reusing instance attribute.
3. **Missing os.makedirs(output_dir)** — Video downloads would fail. Fixed.
4. **_media_group_result discards file_ids** — Now shows first image instead of text fallback.
5. **Private _is_allowed import** — Added public `is_user_allowed()` wrapper.
6. **GUEST_MODE_ENABLED default** — Changed from "true" to "false" until production-ready.

## Known Limitations

1. **Saved Messages pollution** — `_upload_to_telegram` sends files to `chat_id: "me"` to get file_id. Every guest download creates a permanent message in Saved Messages.
2. **Media groups** — InlineQueryResult doesn't support media groups. Multi-image posts show only the first image.
3. **Library dependency** — Using raw httpx for polling and answerGuestQuery. When python-telegram-bot adds Bot API 10.0 support, swap to native handling.

## Migration Path

When python-telegram-bot adds Bot API 10.0 support:
1. Upgrade: `pip install python-telegram-bot>=23.0`
2. Replace unified polling with `app.run_polling(allowed_updates=[..., "guest_message"])`
3. Add `MessageHandler(filters.UpdateType.GUEST_MESSAGE, handle_guest)`
4. Replace raw `answerGuestQuery` calls with library method
5. Remove `httpx` dependency

## How to Enable

1. Open @BotFather → your bot settings → enable "Guest Mode"
2. Set `GUEST_MODE_ENABLED=true` in `.env`
3. Deploy from `feature/guest-mode` branch
4. Tag `@yourbotname https://youtube.com/watch?v=xyz` in any chat

## UzbekGPT Research

Attempted to check https://git.hkr.at.by/cgit.cgi/uzbekgpt for implementation details, but the repo was not accessible via GitHub API or web fetch. The bot uses ollama with gemma4:31b-cloud model and already supports guest mode (Bot API 10.0).
