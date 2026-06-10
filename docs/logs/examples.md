In this example, the tt link is being fetched. request received, then yt-dlp requests kick in and then it tries to download lower quality and then fails with log level of WARNING.
Then gallery dl downloads image and all good.
```json
{"timestamp": "2026-06-04T19:00:04.908457+03:00", "level": "INFO", "message": "Request received", "event": "request_received", "request_id": "ed862ccc", "url": "https://vt.tiktok.com/ZSxKwJwxP/", "platform": "", "user": {"id": 12345678, "name": "Alice", "username": "user_alice"}, "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}}
{"timestamp": "2026-06-04T19:00:04.964073+03:00", "level": "INFO", "message": "download_video: running yt-dlp for https://vt.tiktok.com/ZSxKwJwxP/"}
{"timestamp": "2026-06-04T19:00:07.774591+03:00", "level": "INFO", "message": "download_video: retrying with lower quality for https://vt.tiktok.com/ZSxKwJwxP/"}
{"timestamp": "2026-06-04T19:00:10.635759+03:00", "level": "WARNING", "message": "download_video: yt-dlp failed (code 1): WARNING: [generic] Falling back on generic information extractor\nERROR: Unsupported URL: https://www.tiktok.com/@kefir1611/photo/7631604379170229524?_r=1&_t=ZS-96tW3wVcZTr\n"}
{"timestamp": "2026-06-04T19:00:13.160092+03:00", "level": "INFO", "message": "Request completed", "event": "request_completed", "request_id": "ed862ccc", "url": "https://vt.tiktok.com/ZSxKwJwxP/", "platform": "tiktok", "duration_ms": 8251, "success": true, "content_type": "image", "file_size_mb": 0.16}
```
I see several problems here, both logic and logs related. 
The logic problem is that it tries to fetch video on a photo post. While it works in the end, it is quite unoptimal.
Can we get a clue on what the content types is in metadata then fire either video or photo handler? Or do we need to have it sequential?
It couldnt get a video so it retried with lower res. Nice, same question, can we at this point go to image handler? 


While it is quite verbose, there are a lot of noise here.
We 100% need these logs to understand what happens to debug the app, but.
When the log system was introduced, you've said to me, that having same fields in all logs are industry standard. Well the logs here are obviously not the same regarding fields. We can def drop `"platform": "",` at request received. Not to mention, that request completed misses user and chat fields.

Do we need to make it "level": "WARNING" at these requests? It feels as if the level is not corresponding to seriousness of the error. And furthermore it did not fail at all as we got the image in the end.


I think that we need to make to log files, `requests.jsonl` and `request-details.jsonl`. In console everything will just be logged to stdout.
In files, we would get
`requests.jsonl`:
```json
{"timestamp": "2026-06-04T19:00:04.908457+03:00", "level": "INFO", "message": "Request received", "event": "request_received", "request_id": "ed862ccc", "url": "https://vt.tiktok.com/ZSxKwJwxP/", "user": {"id": 12345678, "name": "Alice", "username": "user_alice"}, "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}}
{"timestamp": "2026-06-04T19:00:13.160092+03:00", "level": "INFO", "message": "Request completed", "event": "request_completed", "request_id": "ed862ccc", "url": "https://vt.tiktok.com/ZSxKwJwxP/", "platform": "tiktok", "duration_ms": 8251, "success": true, "content_type": "image", "file_size_mb": 0.16}
```

`request-details.jsonl`:
```json
{"timestamp": "2026-06-04T19:00:04.964073+03:00", "level": "INFO", "message": "download_video: running yt-dlp", "url": "https://vt.tiktok.com/ZSxKwJwxP/", "request_id": "ed862ccc", "platform": "tiktok"}
{"timestamp": "2026-06-04T19:00:07.774591+03:00", "level": "INFO", "message": "download_video: retrying with lower quality", "url": "https://vt.tiktok.com/ZSxKwJwxP/", "request_id": "ed862ccc", "platform": "tiktok"}
{"timestamp": "2026-06-04T19:00:10.635759+03:00", "level": "WARNING", "message": "download_video: yt-dlp failed (code 1): WARNING: [generic] Falling back on generic information extractor\nERROR: Unsupported URL: https://www.tiktok.com/@kefir1611/photo/7631604379170229524?_r=1&_t=ZS-96tW3wVcZTr\n","url": "https://vt.tiktok.com/ZSxKwJwxP/", "request_id": "ed862ccc", "platform": "tiktok"}
```
As you can see, the requests file will contain only requests and requests details will have deeper info on what happens. We bind by request id. Also the message is now separated from url to simplify search.
Also i think it would be good to add platform to detail log if we have it at that point

---

As for `reply_to_retry`, i want them to be in `requests.jsonl` with the structure like for normal requests
```json
{"timestamp": "2026-06-03T21:34:03.842149+03:00", "level": "INFO", "message": "reply_to_retry url=https://www.instagram.com/reel/DYpyFA3IT-F/?igsh=MTNiMzZxa29rendybA== user=12345678 chat=-1003804964305"}
```

```json
{"timestamp": "2026-06-03T21:34:03.842149+03:00", "level": "INFO", "message": "Request received", "event": "reply_to_retry", "request_id": "eb862cbc", "url": "https://www.instagram.com/reel/DYpyFA3IT-F/?igsh=MTNiMzZxa29rendybA==", "user": {"id": 12345678, "name": "Alice", "username": "user_alice"}, "chat": {"id": -1003804964305, "name": "Test Group", "type": "supergroup"}}
```
And to create similar when it completes
```json
{"timestamp": "2026-06-03T21:34:03.842149+03:00", "level": "INFO", "message": "Request completed", "event": "reply_to_retry", "request_id": "eb862cbc", "url": "https://www.instagram.com/reel/DYpyFA3IT-F/?igsh=MTNiMzZxa29rendybA==", "platform": "instagram", "duration_ms": 9951, "success": true, "content_type": "image", "file_size_mb": 0.16}
```
All intermediate requests go to detailed logs.
Maybe need to think something better on messages and events for this case.

---
---


```py
    logger.info("download_audio: running yt-dlp for %s", url)
    logger.info("download_video: yt-dlp ok for %s", url)
```

```json
{"timestamp": "2026-06-03T14:34:03.835972+03:00", "level": "INFO", "message": "download_video: running yt-dlp for https://vt.tiktok.com/ZSxGpCwvt/"}
{"timestamp": "2026-06-03T14:34:13.212861+03:00", "level": "INFO", "message": "download_video: yt-dlp ok for https://vt.tiktok.com/ZSxGpCwvt/"}
```

twice almost the same log

```json
{"timestamp": "2026-06-03T14:35:50.453063+03:00", "level": "INFO", "message": "download_video: running yt-dlp for https://music.youtube.com/watch?v=uueRqEalZ7s&si=Xu33ojhvEQyWBemI"}
{"timestamp": "2026-06-03T14:35:56.974163+03:00", "level": "INFO", "message": "download_video: yt-dlp ok for https://music.youtube.com/watch?v=uueRqEalZ7s&si=Xu33ojhvEQyWBemI"}
```

```py
    logger.info("download_video: retrying with lower quality for %s", url)
        logger.warning("download_video: yt-dlp failed (code %d): %s", result.returncode, result.stderr[:500])

        logger.info("download_video: yt-dlp ok (fallback) for %s", url)
    logger.info("download_audio: running yt-dlp for %s", url)

        logger.warning("download_audio: yt-dlp failed (code %d): %s", result.returncode, result.stderr[:500])

        logger.info("download_audio: yt-dlp ok for %s", url)
```