# AI Log

## Tools used

- **Muse** (Meta's personal AI agent, running in this workspace): wrote
  the code, tests and documentation files, ran the tests, started the
  server and verified every API endpoint with curl.
- **Python 3.12 standard library documentation**: checked the
  `http.server` ThreadingHTTPServer API, the `sqlite3` module and the
  `unittest` module while writing the server and tests. No third-party
  packages were used anywhere.
- **Headless Chromium** (Playwright's `chrome-headless-shell`): rendered
  the generated SVG to a PNG to check the drawing visually instead of
  trusting the raw markup.

## Key prompts (paraphrased)

1. "Design the crane model for a single-girder top-running EOT crane:
   fix the inputs and ranges, the derived dimensions, and the beam
   deflection check, and label every estimate as an estimate."
2. "Build a Flask-free Python backend using only the standard library:
   ThreadingHTTPServer plus sqlite3, with a JSON API for preview, create,
   list, get, update, delete and SVG download."
3. "Generate a dimensioned SVG drawing server-side with three panels:
   front elevation, side elevation and plan view, with arrowhead
   dimension lines labelled in metres."
4. "Write unit tests covering validation rejections, the span 20 /
   capacity 5 / A4 derivation, the deflection formula and the SVG
   output, then run them and fix failures."
5. "Verify the whole thing end to end: start the server, curl every
   endpoint including error cases, and render the SVG to check it
   visually."

## One time the AI was wrong

The first draft of the SVG looked correct when read as markup, but
rendering it to a PNG in headless Chromium showed three label
collisions: the "HOOK BLOCK" label was drawn inside the hook block and
overlapped the "GIRDER" text; in the side elevation the "TROLLEY
WIDTH" and "GIRDER WIDTH" labels sat on top of each other because the
trolley is only 0.45 m tall at that scale; and in the plan view the
"RUNWAY RAIL" label collided with the rotated "END CARRIAGE LENGTH"
dimension text. I caught this only because I rendered the SVG instead
of trusting the XML parse check, which had passed. The fix was to
reposition the labels: hook block label to the left of the block,
girder width label to the right of the girder, runway rail label to the
left of the plan, the girder label moved to quarter-span so it cannot
sit under the trolley, and the side elevation overall-height dimension
moved further right to clear the labels. A second render confirmed
every label is readable with no overlaps.
