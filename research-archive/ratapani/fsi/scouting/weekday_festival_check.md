# Do fires start more on certain weekdays or around Holi? (FSI thread, 16 Oct 2026)

**Data and method.** 3,483 first-day ignitions, 15 Feb-15 Jun 2017-26, from `data/ignition_points.csv` (median ignition time, IST). Each day's count is compared with a 15-day running mean for the same season, which removes the seasonal curve. Code: `code/akkshay_checks/cal.py`.

**Weekday: no effect.** Observed / expected ignitions by day of week:

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|
| 0.98 | 0.98 | 1.01 | 1.01 | 0.95 | 1.05 | 1.01 |

The chi-square test gives p = 0.82, so no weekly market (haat) or Sunday cycle shows at the sanctuary level.

**Holi (2017-26):**
- **Day before Holi** (Holika Dahan bonfire night): 95 ignitions against 64 expected (1.47x).
- **Days +3 and +4 after Holi:** 1.33x and 1.27x.
- **Holi day and the two days after:** low, 0.83-0.90x.
- **How reliable:** the day-to-day noise for a 10-year sum is about ±0.3, so the eve and the +3/+4 peaks are hints, not proof. [inference] The pattern fits people holding off on the festival itself and burning before and after.

**Use.** A weekday input is not worth adding. A "Holi eve" flag might help the daily budget (calendar vs forecast), but it is weak. Check it on all-MP data, which has about 80x more fires, before using it.
