# Parametric Overhead Crane Drawing Generator

A full stack web app that generates a dimensioned 2D drawing of a
single-girder, top-running EOT overhead crane from user inputs, and lets
users save, reopen and edit designs. Built for the Modern Crane Co
take-home assignment.

## How to run

Requirements: Python 3.8 or newer. No packages to install.

```sh
./run.sh
```

Then open http://127.0.0.1:8000 in a browser.

Alternatively: `python3 server.py`

The server creates `data/crane.db` (SQLite) on first run. That folder is
gitignored, so each fresh checkout starts with an empty design list.

## Stack and why

- **Python 3 standard library only** (`http.server` ThreadingHTTPServer
  plus `sqlite3`). Zero-install: anyone with Python can run it with one
  command, and there is no dependency drift to break the submission.
- **SQLite file database.** One file, no server to configure, and it fits
  the data model (a handful of saved designs) exactly.
- **Server-side SVG generation.** The drawing is built in `crane.py` from
  the same validated inputs and derived values the API returns, so the
  picture can never disagree with the numbers. The browser only displays
  the SVG the server produced.
- **No frontend framework, no CDN, no external fonts.** Plain HTML, CSS
  and JavaScript in `static/`, so the UI works offline.

## Project layout

| File | Contents |
| --- | --- |
| `crane.py` | Crane model: input validation, derived values, SVG drawing. No web code. |
| `server.py` | HTTP server, JSON API, SQLite persistence, static file serving. |
| `static/index.html`, `static/styles.css`, `static/app.js` | The UI. |
| `tests/test_crane.py` | Unit tests for validation, derivation and SVG output. |
| `run.sh` | One-command start script. |
| `DECISIONS.md` | Written by Muhammad Huzaifa Aqeel in his own words, without AI. |
| `AI_LOG.md` | Tools used, key prompts, and one time the AI was wrong. |

## API

| Method | Endpoint | Notes |
| --- | --- | --- |
| GET | `/api/health` | `{"status": "ok"}` |
| POST | `/api/preview` | `{inputs}` returns `{inputs, derived, warnings, svg}`. No database write. |
| POST | `/api/designs` | Creates a design, returns 201 with the design including derived values. |
| GET | `/api/designs` | List ordered by most recently updated (id, name, span, capacity, lift, duty, updated_at). |
| GET | `/api/designs/{id}` | Full design including derived values and SVG. 404 if missing. |
| PUT | `/api/designs/{id}` | Updates a design. 400 on invalid input, 404 if missing. |
| DELETE | `/api/designs/{id}` | Returns 204. 404 if missing. |
| GET | `/api/designs/{id}/drawing.svg` | The drawing as `image/svg+xml`. 404 if missing. |

All validation failures return HTTP 400 with
`{"errors": {"field": "message"}}`. Other errors return
`{"error": "..."}`. Malformed JSON returns HTTP 400.

## Inputs and ranges

| Input | Range / rule |
| --- | --- |
| name | Required string, 3 to 80 characters |
| span_m | 5 to 30 m, distance between runway rail centrelines |
| capacity_t (SWL) | 1 to 20 t |
| lift_height_m | 3 to 18 m, floor to hook at highest position |
| trolley_position_m | Optional, defaults to span / 2, must be 1.0 to span minus 1.0 |
| duty_class | A3, A4 or A5, default A4 |
| notes | Optional string, max 500 characters |

Validation runs on the server for every request. The browser also shows
server validation errors under the relevant field, but client checks are
never trusted.

## Derived values and formula sources

All derived lengths are rounded to 3 decimal places in the JSON. Values
marked "estimate" in the UI are rules of thumb, not engineering data.

| Value | Formula | Source / confidence |
| --- | --- | --- |
| Girder depth | span / depth factor, clamped 0.40 to 1.90 m. Factors: A3 = 20, A4 = 18, A5 = 16 | Rule of thumb, span/depth ratio of 16 to 20 is a common starting point for crane girders. Estimate. |
| Girder width | girder depth x 0.55 | Rule of thumb for a box girder proportion. Estimate. |
| Plate thickness | 10 mm up to 5 t, 12 mm up to 10 t, 16 mm above | Rule of thumb stepped by capacity. Estimate. |
| Headroom | 0.85 + 0.04 x capacity | Estimate for hoist plus hook block height. |
| Hook block height | 0.50 + 0.025 x capacity | Estimate. |
| End carriage height | 0.45 m | Fixed estimate. |
| Girder bottom | lift height + headroom | Geometry: the girder sits above the hook travel plus the hoist. |
| Rail top | girder bottom minus end carriage height | Geometry: the end carriage connects the rail to the girder. |
| Overall height | girder bottom + girder depth + trolley height | Geometry. |
| Overall width | span + 1.20 m (0.60 m overhang each side) | Estimate. |
| End carriage length | clamp(1.8 + 0.04 x span, 2.0, 3.2) m | Estimate. |
| Trolley width | 0.80 + 0.03 x capacity | Estimate. |
| Trolley travel | span minus 1.80 m | Estimate. |
| Approach | 0.90 m | Estimate. |
| Beam deflection (live load) | P x L^3 / (48 x E x I), with P = capacity x 1000 x 9.81 N, E = 200 GPa, and I the box-section second moment of area I = (B x D^3 minus b x d^3) / 12 | Standard Euler-Bernoulli beam theory for a simply supported beam with a central point load. This is the one formula that is textbook theory rather than an estimate. |
| Deflection limit | span / 750 | Commonly used crane-girder deflection limit. Flagged as typical, not a standard. |
| Masses | Girder steel area x span x 7850 kg/m3; end carriage 220 + 8 x span kg each; trolley plus hoist 350 + 55 x capacity kg | Estimates. |
| Max wheel load | (total mass + capacity) x 9.81 / 4 x 1.15, in kN | Estimate, with a 1.15 dynamic factor. |

## The drawing

One SVG (viewBox 0 0 1100 1250), three stacked panels:

- **A) Front elevation:** floor line, runway rails, end carriages, girder,
  trolley at the chosen position, hoist rope, hook block and hook.
  Dimensions: SPAN, OVERALL WIDTH, OVERALL HEIGHT, LIFT HEIGHT,
  GIRDER DEPTH.
- **B) Side elevation:** end carriage length, girder width, trolley width.
  Dimensions: END CARRIAGE LENGTH, OVERALL HEIGHT.
- **C) Plan (top view):** span by end-carriage length, dashed girder
  centreline, trolley square at the chosen position. Dimensions: SPAN,
  END CARRIAGE LENGTH.

Each panel is scaled to fit its box. All dimension text is in metres to
2 decimal places. The deflection result is shown as a PASS/FAIL badge,
with a warning message when it fails.

## Tests

```sh
python3 -m unittest discover -s tests -v
```

18 tests cover validation rejections (span, capacity, trolley position,
duty class, name, non-finite numbers, notes length, wrong types),
derivation for the span 20 / capacity 5 / A4 case (girder depth
20/18 = 1.111 m), the deflection formula against an independent
recomputation, plate-thickness steps, duty-class depth factors, and SVG
output (dimension labels present, valid XML, user text escaped).

## Known limitations

- Single-girder top-running cranes only. No double-girder, underslung or
  gantry variants.
- Deflection is live-load only, for a central point load on a simply
  supported beam. It ignores the girder self-weight, trolley position
  away from mid-span, dynamic and impact loads, wind, seismic loads and
  fatigue.
- Headroom, overhang, masses and wheel loads are estimates and rules of
  thumb. Nothing here is for manufacture; a real crane needs a qualified
  structural engineer and the applicable crane standard.
- No user accounts or authentication. Anyone who can reach the local
  server can see and delete all designs.
- The database is a single SQLite file with no migrations. Deleting
  `data/crane.db` deletes all saved designs.
- The UI is desktop-first. It works on small screens through a stacked
  layout, but it is not tuned for phones.

Hours spent: [to be filled in by Huzaifa after review - do not invent a number]
