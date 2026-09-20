---
name: dgx-h100-front-fan-module-replacement
description: "Guide a technician through DGX H100 Front Fan Module Replacement and check the work against 8 rules compiled from the official manual (2 critical). Use when planning, performing, or reviewing this procedure."
---

# DGX H100 Front Fan Module Replacement

Complete DGX H100 Front Fan Module Replacement exactly as the manual requires.

## Before you start

- Identify the failed fan module through the BMC, nvsm, or its fault LED before removing it _(manual Front Fan Module Replacement Overview)_
- Take the new fan module out of its packaging and be ready to install it before removing the old one _(manual Replacing and Returning the Front Fan Module)_

## Procedure

1. Front bezel removed from the system, exposing the fan modules _(manual Identifying a Failed Fan Module)_
2. Failed fan module identified from BMC sensor data, the nvsm show fans output, or its lit fault LED _(manual Front Fan Module Replacement Overview)_
3. New fan module taken out of its packaging and held ready to install _(manual Replacing and Returning the Front Fan Module)_
4. Release button on the failed fan module pressed to unlock it _(manual Replacing and Returning the Front Fan Module)_
5. Failed fan module pulled fully out of its bay _(manual Front Fan Module Replacement Overview, Identifying a Failed Fan Module, Replacing and Returning the Front Fan Module)_
6. New fan module pushed fully into the empty fan bay _(manual Replacing and Returning the Front Fan Module)_
7. New fan confirmed healthy: amber LED off, or BMC sensors or nvsm show fans checked _(manual Replacing and Returning the Front Fan Module)_
8. Front bezel reinstalled on the system _(manual Replacing and Returning the Front Fan Module)_

## Rules that must hold

- **CRITICAL** Replace the old fan with the new one within 30 seconds to avoid overheating system components — `MAX_INTERVAL(fan_removed->fan_inserted<=30s)` _(manual Replacing and Returning the Front Fan Module)_
- **CRITICAL** Confirm the new fan module is healthy through the BMC, its amber LED, or nvsm show fans — `MUST_HAVE(fan_health_verified)` _(manual Replacing and Returning the Front Fan Module)_
- **MAJOR** Remove the bezel to expose the fan modules before removing a fan — `BEFORE(bezel_removed,fan_removed)` _(manual Identifying a Failed Fan Module)_
- **MAJOR** Unlock the fan module by pressing the release button before pulling it out — `BEFORE(fan_unlocked,fan_removed)` _(manual Replacing and Returning the Front Fan Module)_
- **MAJOR** Check fan health after the new fan module is installed — `AFTER(fan_health_verified,fan_inserted)` _(manual Replacing and Returning the Front Fan Module)_
- **MINOR** Reinstall the bezel when the replacement is complete — `MUST_HAVE(bezel_installed)` _(manual Replacing and Returning the Front Fan Module)_

## Deviations seen in practice

Observed in verification run DEMO-B:

- Confirm the new fan module is healthy through the BMC, its amber LED, or nvsm show fans: fan_health_verified was not observed anywhere in the video; the step is mandatory
- Check fan health after the new fan module is installed: fan_health_verified was not observed anywhere in the video; it must happen after fan_inserted

## When answering

- Cite the manual location for every rule you state.
- If the user describes a step that breaks a rule above, say which rule and what the manual requires.
- Do not approve work as complete until every verification rule is satisfied.

## References

- `references/requirements.json` — compiled rules and event vocabulary
- `references/evidence.md` — manual quotes behind each rule
- `references/verification-report.json` — video verification results
- `references/skill-card.md` — owner, dependencies and risks for this skill
- `evals/evals.json` — eval cases this skill is expected to pass, including negative cases
