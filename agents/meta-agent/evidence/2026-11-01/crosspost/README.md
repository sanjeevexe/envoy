# The cross-post dry run (Nov 1, 2026, 23:22–23:36 ET)

The Spark agent (`muse-spark-1.3`, effort low) called showcase's learned posting routines as MCP tools, on the Pixel 5
("Envoy's phone"), through a `:8765` test copy of Envoy, never the live API. **Nothing was posted.** Every post stopped at
the app's final button and was declined on the copy, by its user.

**Setup:**
- **The copy:** its own data dir and outbox, 0 push subscriptions, "always ask" for Instagram, TikTok and YouTube, and the
  four routines shared with agents ("Share with agents"). The key was the copy's "Spark agent" (read, run, triggers).
- **Before each run** (`docs/demo-showcase.md`): `scripts/instagram_take.py`, then `eval/run_showcase.py setup-youtube`,
  then a labelled test clip pushed last ("XPOST 1", then "XPOST 2").
- **The copy's user** was a small script in the session's scratch, not in the repo. It said yes to using the phone after
  10 s and declined each post 20 s after it was asked, as `eval/run_showcase.py` does.
- **Captures:**
  - Page captures are 1920×1080 headless Chrome.
  - Each final screen's approval screenshot showed the right clip, caption and poll. They stay outside the repo because
    TikTok's shows the phone's nearby places.

## `run1-three-posts.json`: three posts (main `5d757fa`)

This run used the same reel, TikTok and YouTube routines as main `aa4614e`. The copy's phone settings matched the live
API's: only Instagram is set to the phone.

1. **The request:** "Post my newest video from my phone to Instagram as a Reel, to TikTok, and as a YouTube Short, all
   with JVKE's "golden hour". Caption (and the Short's title): "One clip, three apps"."
2. **First calls:** Spark called `instagram_reel_song`, `tiktok_post_sound` and `youtube_short_sound` at once, without
   `phone`.
   - Instagram went to the Pixel.
   - TikTok and YouTube failed at once: "The emulator for this app (Real-app phone) isn't running right now. Ask again
     with "on my phone"…".
   - Spark called those two again with `phone: "phone"`, then one `wait_for_task` on all three.
3. **Phone use:** each task first asked "Envoy wants to use Envoy's phone for this task", so the dock showed three cards
   (`run1-phone-ok-answered.png`, after they were answered). The posts then ran one at a time on the Pixel.
4. **Final buttons**, timed from when each task had the phone:
   - Instagram's **Share** after 53 s (`run1-waiting-instagram-share.png`);
   - TikTok's **Post** after 75 s (`run1-waiting-tiktok-post.png`);
   - YouTube's **Upload Short** after 42 s.

   Each was declined. Spark: "All three drafts were prepared … but you declined the final share in Envoy, so nothing was
   posted to Instagram, TikTok, or YouTube." (`run1-all-declined.png`)
5. **Cost:**
   - Spark: 11 model calls, $0.044.
   - Envoy: TikTok used 7 vision calls ($0.020); Instagram and YouTube used none.

## `run2-four-posts.json`: four posts, with the Story poll (main `aa4614e`)

On the copy, Instagram, TikTok and YouTube were all set to the phone (Settings › Phones).

1. **The request** was the same as run 1, plus: "Also put it on my Instagram story with a poll: "Golden hour or blue
   hour?", options "Golden" and "Blue"."
2. **Calls:** Spark made four routine calls, all going straight to the Pixel, then one `wait_for_task` on all four.
3. **Phone use:** four phone-use asks stacked in the dock (`run2-four-phone-asks.png`).
4. **Final buttons**, timed from when each task had the phone:
   - **Upload Short** after 40 s;
   - **Post** after 86 s;
   - **Your story** after 31 s (`run2-waiting-story.png`);
   - **Share** after 59 s.

   All were declined. Spark: "All four were prepared but not posted — you declined the final share step for the Reel,
   TikTok, YouTube Short, and story poll." (`run2-all-declined.png`)
5. **Cost:**
   - Spark: 11 model calls, $0.043.
   - Envoy: TikTok used 7 vision calls ($0.018). YouTube's search step needed no repair in either run.

## What the page showed

- **The dock:** each waiting post's card names its button ("Share", "Post", "Upload Short", "Your story") and the routine's
  purpose. Its live timer is blank in the headless captures, but it ticks in a real browser ("12 s" on the YouTube card,
  checked at 1920×1080).
- **The feed:** every routine call is shown with its arguments and task id. A single "wait_for_task" row covers all the
  tasks ("3 tasks: waiting for the user's OK, running, running"). Each answer stays as a line ("declined · 21 s").
- **The conversation:** Spark kept count after each no ("TikTok was also declined, I'll keep waiting on the Instagram
  reel and story"). Two rough edges:
  - It once said "please approve them" about phone-use asks that had just been answered.
  - A waiting pill turns into "You said no" where it first appeared, so in the final transcript it sits above Spark's
    "please approve" line.
- **Phone-use cards after these runs:** they now read "Use Envoy's phone?" instead of Envoy's own sentence, "Envoy wants
  to use Envoy's phone for this task". The captures above show the old title.
