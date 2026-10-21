# Forecast-led patrol pilot: what the field app would need

Built 15 Oct 2026 after Akkshay said "as u deem fit to be best". See README "Patrol pilot" and INTEGRATION.md.
Protocol v3 additions (person-hour parts, shakedown gate, unique fires, blind review, per-beat CSV with block) built the same day; see INTEGRATION.md "Protocol v3 additions".
Checked against the engine on 15 Oct 2026. Sizes are rough working time.

| # | Gap | What exists now | What it would take | Size |
|---|---|---|---|---|
| 1 | Check tasks for predicted cells | Tasks (`incidents`) come only from satellite points: one point, a beat, a due time. Photo/GPS proof, review and the 7% re-check all hang off an incident. | Reuse `incidents` with a new `kind` (alert / predicted / chance), plus `cell_geom` (polygon), `issue_date`, `due_from`/`due_utc` (2-day window), `arm` (fixed / calendar / forecast), `model_hash` and `near_active_fire`. A POST /api/v1/tasks (or CSV import) for the model's daily picks. The guard card draws the cell and says "check this cell". The proof distance is measured to the cell edge, not to a point. The dashboard filters by arm. This lets the whole proof/review flow work unchanged. | 1-1.5 days |
| 2 | Burn age on reports | `outcome` active_fire / burnt_out, `fire_out_utc` | A `burn_age` column (burning now / 1-2 days / older), one picker on the form, one API field | 1 h |
| 3 | "No fire, no fresh burn" outcome | The outcomes are active_fire, burnt_out, no_fire, outside_forest and controlled_burn. `no_fire` counts as a false alert. | Add `nothing_found`, offered only on predicted tasks. Stats count it as a completed check, not a false alert. | 1-2 h |
| 4 | Crew-day log | Phone positions every few minutes while the app is open, auto "reached" at 200 m, `visited_utc`, `crew` per report | A `shifts` table (staff, start/end time and GPS, crew size) with Start/End day buttons in the guard app. Staff-hours = shift length × crew; travel comes from the positions already stored. | 0.5 day |
| 5 | Chance find (fire seen on the way) | Nothing: every report needs a task | A "Report a fire here" button that creates a `kind=chance` incident at the phone position, then the normal report form and photo proof | 0.5 day (after 1) |
| 6a | Auto-link a found fire to alerts | `near_recent` (1 km, 7 days) is shown for alerts but not stored on reports | On an active_fire/burnt_out report, store links to any satellite alert within 1.5 km in the last 3 days. "Previously active" vs "new" falls out of that. | 2-3 h |
| 6b | Post-season "missed fires" report | Alerts, scars per alert (scars.py), visits per incident | A script, per arm: alerts and burn scars in the arm's beats with no visit within 2 days. It needs a beat → arm table (who is in which arm), which the protocol must supply. | 0.5 day |

Total: about 3-4 days of work, most of it in item 1. Items 2, 3 and 6a are small and independent. Items 5 and 6b depend on 1 (the `kind` and `arm` fields).

Open points for the protocol owner:
- Is the arm assigned per beat or per task? 6b assumes per beat.
- Does a predicted cell use the 500 m grid cell polygon from ratapani/mp_grid? I assume yes.
- Does the forecast arm send cells near an active fire as tasks, or only flag them? The flag is stored either way.
