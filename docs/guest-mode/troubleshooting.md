# Guest Mode Troubleshooting

## Common Issues

### Guest messages not received

**Symptom:** Bot doesn't respond when mentioned in chats

**Possible causes:**
1. `GUEST_MODE_ENABLED=false` in .env
2. Bot not enabled for guest mode in BotFather
3. `STORAGE_CHANNEL_ID` not set or bot not admin in channel

**Debug steps:**
1. Check logs for `guest_message` events
2. Verify `GUEST_MODE_ENABLED=true` in .env
3. Check BotFather settings: BotFather → /mybots → Bot Settings → MiniApp → Enable Guest Mode

### answerGuestQuery fails

**Symptom:** Bot receives guest message but reply fails

**Possible causes:**
1. Invalid `guest_query_id`
2. Bot not admin in storage channel
3. InlineQueryResult format incorrect

**Debug steps:**
1. Check logs for `answer_guest_query` errors
2. Verify bot is admin in `STORAGE_CHANNEL_ID`
3. Check InlineQueryResult format (raw dicts, not ptb objects)

### Files not uploaded to storage channel

**Symptom:** Bot downloads file but can't reply

**Possible causes:**
1. Storage channel doesn't exist
2. Bot not admin in channel
3. File too large for Telegram

**Debug steps:**
1. Check logs for `upload_to_storage` errors
2. Verify channel ID in `STORAGE_CHANNEL_ID`
3. Check bot permissions in channel

## Error Messages

### "Guest query ID required"
- Missing `guest_query_id` in update
- Check if guest mode is properly enabled

### "Storage channel not configured"
- `STORAGE_CHANNEL_ID` not set in .env
- Set it to a private channel ID

### "Not authorized"
- User not in allowlist
- Check `ALLOWED_USER_IDS` and `allowed-contacts.json`

## Debug Logging

Enable debug logging to see detailed guest mode flow:

```bash
LOG_LEVEL=DEBUG
```

Look for these log events:
- `guest_message received` - Bot received guest query
- `guest_mode: processing URL` - URL extracted and being processed
- `guest_mode: reply sent` - Reply sent successfully
- `guest_mode: reply failed` - Reply failed (check error details)
