# Evidence for dgx-h100-front-fan-module-replacement

## R-001 — Identify the failed fan module through the BMC, nvsm, or its fault LED before removing it

Constraint: `PRECONDITION(failed_fan_identified,fan_removed)` — result **PASS**: failed_fan_identified established before fan_removed

- Manual Front Fan Module Replacement Overview (`EV-DEMO-MANUAL-B3`, sha256 fc77b4c28c29): Identify failed front fan module through BMC or with the fan module LED and submit a service ticket
- Video 00:15.0–00:18.0 (`EV-DEMO-B-O-002`, sha256 1e7bb937f3ae): Technician points at the fan module whose amber fault LED is lit
- Video 00:38.0–00:43.0 (`EV-DEMO-B-O-005`, sha256 1e7bb937f3ae): Failed fan module slid out of the bay

## R-002 — Take the new fan module out of its packaging and be ready to install it before removing the old one

Constraint: `PRECONDITION(new_fan_unpacked,fan_removed)` — result **PASS**: new_fan_unpacked established before fan_removed

- Manual Replacing and Returning the Front Fan Module (`EV-DEMO-MANUAL-B28`, sha256 fc77b4c28c29): Remove the new fan module from its packaging and be ready to install it. Important Replace the old fan with the new one within 30 seconds to avoid overheating of the system components.
- Video 00:20.0–00:28.0 (`EV-DEMO-B-O-003`, sha256 1e7bb937f3ae): Technician lifts the new fan module out of its box
- Video 00:38.0–00:43.0 (`EV-DEMO-B-O-005`, sha256 1e7bb937f3ae): Failed fan module slid out of the bay

## R-003 — Replace the old fan with the new one within 30 seconds to avoid overheating system components

Constraint: `MAX_INTERVAL(fan_removed->fan_inserted<=30s)` — result **PASS**: fan_removed → fan_inserted took 12.0s, within 30s

- Manual Replacing and Returning the Front Fan Module (`EV-DEMO-MANUAL-B28`, sha256 fc77b4c28c29): Remove the new fan module from its packaging and be ready to install it. Important Replace the old fan with the new one within 30 seconds to avoid overheating of the system components.
- Video 00:38.0–00:43.0 (`EV-DEMO-B-O-005`, sha256 1e7bb937f3ae): Failed fan module slid out of the bay
- Video 00:50.0–00:55.0 (`EV-DEMO-B-O-006`, sha256 1e7bb937f3ae): New fan module pushed into the bay until it latches

## R-004 — Remove the bezel to expose the fan modules before removing a fan

Constraint: `BEFORE(bezel_removed,fan_removed)` — result **PASS**: bezel_removed precedes fan_removed

- Manual Identifying a Failed Fan Module (`EV-DEMO-MANUAL-B15`, sha256 fc77b4c28c29): Removing and Attaching the Bezel to expose the fan modules. After you remove the bezel, the system looks like the following figure.
- Video 00:05.0–00:12.0 (`EV-DEMO-B-O-001`, sha256 1e7bb937f3ae): Front bezel pulled off the chassis
- Video 00:38.0–00:43.0 (`EV-DEMO-B-O-005`, sha256 1e7bb937f3ae): Failed fan module slid out of the bay

## R-005 — Unlock the fan module by pressing the release button before pulling it out

Constraint: `BEFORE(fan_unlocked,fan_removed)` — result **PASS**: fan_unlocked precedes fan_removed

- Manual Replacing and Returning the Front Fan Module (`EV-DEMO-MANUAL-B30`, sha256 fc77b4c28c29): Unlock the fan module by pressing the release button, as shown in the following figure.
- Video 00:36.0–00:38.0 (`EV-DEMO-B-O-004`, sha256 1e7bb937f3ae): Release button on the fan module pressed
- Video 00:38.0–00:43.0 (`EV-DEMO-B-O-005`, sha256 1e7bb937f3ae): Failed fan module slid out of the bay

## R-006 — Confirm the new fan module is healthy through the BMC, its amber LED, or nvsm show fans

Constraint: `MUST_HAVE(fan_health_verified)` — result **VIOLATION**: fan_health_verified was not observed anywhere in the video; the step is mandatory

- Manual Replacing and Returning the Front Fan Module (`EV-DEMO-MANUAL-B32`, sha256 fc77b4c28c29): Confirm that the fan module is healthy working properly by performing the following actions: Using the BMC web user interface Verifying that the amber LED on the fan module is extinguished Running the sudo nvsm show fans command Install the bezel as described in the bezel section

## R-007 — Check fan health after the new fan module is installed

Constraint: `AFTER(fan_health_verified,fan_inserted)` — result **VIOLATION**: fan_health_verified was not observed anywhere in the video; it must happen after fan_inserted

- Manual Replacing and Returning the Front Fan Module (`EV-DEMO-MANUAL-B32`, sha256 fc77b4c28c29): Confirm that the fan module is healthy working properly by performing the following actions: Using the BMC web user interface Verifying that the amber LED on the fan module is extinguished Running the sudo nvsm show fans command Install the bezel as described in the bezel section

## R-008 — Reinstall the bezel when the replacement is complete

Constraint: `MUST_HAVE(bezel_installed)` — result **PASS**: bezel_installed observed

- Manual Replacing and Returning the Front Fan Module (`EV-DEMO-MANUAL-B32`, sha256 fc77b4c28c29): Confirm that the fan module is healthy working properly by performing the following actions: Using the BMC web user interface Verifying that the amber LED on the fan module is extinguished Running the sudo nvsm show fans command Install the bezel as described in the bezel section
- Video 01:20.0–01:30.0 (`EV-DEMO-B-O-007`, sha256 1e7bb937f3ae): Front bezel clipped back on right after the fan is seated
