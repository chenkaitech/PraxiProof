# Evidence for server-fan-power-supply-and-cover-installation

## R-101 — Connect a fan's power connector before pressing that fan into its slot

Constraint: `PRECONDITION(fan_connected,fan_installed)` — result **PASS**: fan_connected established before fan_installed

- Manual Procedure (`EV-DEMO-MANUAL-B5`, sha256 30088b0e0cb6): 1. Install the six fans one at a time. For each fan, connect the fan connector first, then press the fan in place.
- Video 00:05.0–00:07.0 (`EV-DEMO-C2-O-001`, sha256 83916b55965d): Fan 1 connector plugged in
- Video 00:08.0–00:11.0 (`EV-DEMO-C2-O-002`, sha256 83916b55965d): Fan 1 pressed into its slot

## R-102 — All six fans must be installed

Constraint: `COUNT(fan_installed>=6)` — result **PASS**: fan_installed observed 6 times (≥ 6)

- Manual Requirements (`EV-DEMO-MANUAL-B10`, sha256 30088b0e0cb6): - All six fans must be installed.
- Video 00:08.0–00:11.0 (`EV-DEMO-C2-O-002`, sha256 83916b55965d): Fan 1 pressed into its slot
- Video 00:17.0–00:20.0 (`EV-DEMO-C2-O-004`, sha256 83916b55965d): Fan 2 pressed into its slot
- Video 00:26.0–00:29.0 (`EV-DEMO-C2-O-006`, sha256 83916b55965d): Fan 3 pressed into its slot
- Video 00:35.0–00:38.0 (`EV-DEMO-C2-O-008`, sha256 83916b55965d): Fan 4 pressed into its slot
- Video 00:44.0–00:47.0 (`EV-DEMO-C2-O-010`, sha256 83916b55965d): Fan 5 pressed into its slot
- Video 00:53.0–00:56.0 (`EV-DEMO-C2-O-012`, sha256 83916b55965d): Fan 6 pressed into its slot

## R-103 — Both power supplies must be installed

Constraint: `COUNT(psu_installed>=2)` — result **PASS**: psu_installed observed 2 times (≥ 2)

- Manual Requirements (`EV-DEMO-MANUAL-B11`, sha256 30088b0e0cb6): - Both power supplies must be installed.
- Video 01:02.0–01:08.0 (`EV-DEMO-C2-O-013`, sha256 83916b55965d): First power supply pressed in until the latch clicks
- Video 01:12.0–01:18.0 (`EV-DEMO-C2-O-014`, sha256 83916b55965d): Second power supply pressed in until the latch clicks

## R-104 — Install the fans before installing the power supplies

Constraint: `BEFORE(fan_installed,psu_installed)` — result **PASS**: fan_installed precedes psu_installed

- Manual Requirements (`EV-DEMO-MANUAL-B12`, sha256 30088b0e0cb6): - Install the fans before installing the power supplies.
- Video 00:08.0–00:11.0 (`EV-DEMO-C2-O-002`, sha256 83916b55965d): Fan 1 pressed into its slot
- Video 01:02.0–01:08.0 (`EV-DEMO-C2-O-013`, sha256 83916b55965d): First power supply pressed in until the latch clicks

## R-105 — Install the power supplies before installing the server cover

Constraint: `BEFORE(psu_installed,cover_installed)` — result **INSUFFICIENT_EVIDENCE**: cover_installed was not observed; cannot check psu_installed before cover_installed

- Manual Requirements (`EV-DEMO-MANUAL-B13`, sha256 30088b0e0cb6): - Install the power supplies before installing the server cover.

## R-106 — The server cover must be installed and locked with the black latch

Constraint: `MUST_HAVE(cover_installed)` — result **VIOLATION**: cover_installed was not observed anywhere in the video; the step is mandatory

- Manual Requirements (`EV-DEMO-MANUAL-B14`, sha256 30088b0e0cb6): - The server cover must be installed and locked with the black latch.

## R-107 — Never press the cover shut without hearing the latch click

Constraint: `MUST_NOT(cover_forced_without_latch)` — result **VIOLATION**: prohibited action cover_forced_without_latch observed

- Manual Safety (`EV-DEMO-MANUAL-B16`, sha256 30088b0e0cb6): - Never press the cover shut without hearing the latch click. Forcing the cover down without the latch engaging can crack the latch tab and leaves the cover unsecured.
- Video 01:25.0–01:30.0 (`EV-DEMO-C2-O-015`, sha256 83916b55965d): Technician slams the cover down; no latch click is heard and the cover sits crooked
