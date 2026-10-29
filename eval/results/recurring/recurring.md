# Chat sets up recurring jobs, live (2026-10-29T13:15:49)

muse-spark-1.3 (standard tier): 7 model calls, $0.01809.

| You said | What happened | Trigger (off, asks each time) | Calls | ms |
| --- | --- | --- | --- | --- |
| Every Friday at 6 PM, order my usual from Thai Basil | Set this up? Every Friday at 6:00 PM: order your usual from Thai Basil | {"weekly_on": {"days": ["fri"], "at": "18:00"}} · order my usual from Thai Basil | 1 | 1901 |
| check my flight status every weekday morning at 7:30 | Set this up? Every weekday at 7:30 AM: check your flight status | {"weekly_on": {"days": ["mon", "tue", "wed", "thu", "fri"], "at": "07:30"}} · check my flight status | 1 | 1435 |
| Whenever SkyLark emails me that check-in is open, check me in for my flight | Set this up? Whenever an email from “SkyLark” about “check-in is open” arrives: check you in for your flight | {"sender_contains": "SkyLark", "subject_contains": "check-in is open", "after_rowid": 0, "memory_db": "mem-10b4a1030"} · check me in for my flight | 1 | 3890 |
| When my flight's gate changes, look up my boarding time | Set this up? Whenever your flight's gate changes: look up your boarding time | {"entity_type": "Flight", "attributes": ["gate"], "after_seq": 0, "memory_db": "mem-10b4a1030"} · look up my boarding time | 1 | 1918 |
| Check me in 24 hours before every flight | Set this up? 24 h before every flight: check you in | {"entity_type": "Flight", "date_attr": "date", "time_attr": "depart_time", "minutes_before": 1440} · Check me in | 1 | 1884 |
| Check me in before my flight to Chicago tomorrow | chat as before (task): Check me in for my flight to Chicago tomorrow |  | 2 | 5004 |
