---
name: server-fan-power-supply-and-cover-installation
description: "Guide a technician through Server Fan, Power Supply and Cover Installation and check the work against 7 rules compiled from the official manual (1 critical). Use when planning, performing, or reviewing this procedure."
---

# Server Fan, Power Supply and Cover Installation

Complete Server Fan, Power Supply and Cover Installation exactly as the manual requires.

## Before you start

- Connect a fan's power connector before pressing that fan into its slot _(manual Procedure)_

## Procedure

1. A fan module's power connector plugged in before the fan is pressed into its slot _(manual Procedure)_
2. A fan module pressed fully into one of its slots _(manual Procedure, Requirements)_
3. A power supply pressed into its compartment until the latch clicks _(manual Requirements)_
4. The server cover placed on top of the chassis and the black latch pressed until it locks _(manual Requirements)_

## Rules that must hold

- **CRITICAL** Never press the cover shut without hearing the latch click — `MUST_NOT(cover_forced_without_latch)` _(manual Safety)_
- **MAJOR** All six fans must be installed — `COUNT(fan_installed>=6)` _(manual Requirements)_
- **MAJOR** Both power supplies must be installed — `COUNT(psu_installed>=2)` _(manual Requirements)_
- **MAJOR** Install the fans before installing the power supplies — `BEFORE(fan_installed,psu_installed)` _(manual Requirements)_
- **MAJOR** Install the power supplies before installing the server cover — `BEFORE(psu_installed,cover_installed)` _(manual Requirements)_
- **MAJOR** The server cover must be installed and locked with the black latch — `MUST_HAVE(cover_installed)` _(manual Requirements)_

## Deviations seen in practice

Observed in verification run DEMO-C2:

- The server cover must be installed and locked with the black latch: cover_installed was not observed anywhere in the video; the step is mandatory
- Never press the cover shut without hearing the latch click: prohibited action cover_forced_without_latch observed

## Confirm separately

These rules could not be confirmed from video and need other evidence:

- Install the power supplies before installing the server cover — Video coverage that includes: cover_installed

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
