# Design Decisions

Living document. Each entry should say what was decided AND why, so future
work doesn't accidentally undo a decision that was already reasoned through.
Full discussion history also lives in the project's Google Drive
(PII_EEG_InnerSpeech/Claude/ and /grok/) - this file is the condensed,
code-relevant subset.

## Accuracy assumptions (2026-08-17)

Real, cross-validated experiments on two public imagined-speech EEG datasets
(ds003626 "Thinking Out Loud" and ArEEG) established:
- Best honest within-subject binary (2-class) accuracy for a person's single
  best-performing command pair: roughly 65-78% (high variance across subjects
  and pairs - not a guarantee, an evidence-based range).
- Cross-subject / zero-shot performance is meaningfully weaker (~50-56%).
- Calibration (short per-user fine-tuning) helps some subject/pair
  combinations and not others - not a universal fix.

Full experimental history is in the Drive grok/ folder (Status entries 01-07)
and Claude/ folder (Notes 01-08). Do not assume these numbers will hold on
real ear-EEG hardware - they come from scalp/8-channel lab datasets. Treat
hardware performance as an open question until tested.

**Product implication**: the simulator defaults to ~70% accuracy
(`FakeBrain(accuracy=0.70)`), and the command policy defaults to conservative
confirm-before-commit thresholds, because we should not design as if the
system will be highly reliable out of the box.

## Confirm-before-commit safeguard (2026-08-17)

Given the accuracy ceiling above, no single decoded event (EEG command or
SSVEP target) should instantly execute an action unless confidence is very
high. Default policy: below 0.5 confidence = ignored as noise; 0.5-0.85 =
show the user what was detected and require a brief confirm; above 0.85 =
auto-commit. These thresholds are tunable product decisions, not fixed
constants - revisit once real calibration data exists.

This applies uniformly to both SSVEP selections (e.g. cursor-glide-then-pause
pattern) and EEG command decodes for now. Whether they should eventually be
tuned differently per input type is still an open question.

## No camera / no continuous eye tracking by default (2026-08-17)

Continuous camera-based gaze tracking was ruled out as a default feature due
to battery drain concerns (validated against the user's own daily device
experience and expected typical user tolerance, not just theoretical power
draw numbers). May be revisited later as an *optional* feature once product
adoption/traction justifies the tradeoff. SSVEP (EEG-based, no camera) is the
committed selection/pointing mechanism instead.

## SSVEP detection latency: ~1-2 seconds assumed (2026-08-17)

SSVEP frequency detection realistically needs roughly 1-2 seconds of signal
to classify reliably (published constraint, consistent with our own
accuracy-vs-data findings throughout this project). Faster detection is an
active research area and may improve over time, but should be treated as a
future software-upgrade path, not a launch assumption. Smoothness in
UI-facing scroll/interaction is achieved via software animation between
detection cycles, not by pretending detection itself is faster than it is.

## Offline-first (2026-08-17)

No cloud dependency for core functionality. All inference, calibration, and
command execution must run on-device. Cloud (if ever used) is limited to
optional non-core features like model updates or backup.

## Fallback to SSVEP-only mode for weak-signal users (2026-08-18)

Real experiments showed some subjects never produce a usable EEG command
pair, even after testing every combination (flat ~55-60% across the board,
no standout - see "Subject 2" findings in Drive history). Rather than
silently give such a user an unreliable EEG-command experience, onboarding
now measures the user's best achievable pair and compares it against a
minimum usability threshold (currently 60%, see `core/user_profile.py`).
Users below threshold are placed in SSVEP_FALLBACK mode: discrete actions
(e.g. YES/NO) are triggered via SSVEP selection instead of an EEG command.
This is a deliberate, visible product decision, not a hidden limitation -
the user should be told which mode they're in and why.

## Mental action vs semantic meaning are decoupled (2026-08-18)

A user's best-performing calibrated pair (e.g. "UP vs LEFT") does not
determine what the interface *shows* them. The EEG classifier only detects
"mental action A" vs "mental action B" - which two actions produce the
clearest signal varies per person. The interface can still present this to
the user as YES/NO (or any other binary function) regardless of which
underlying mental actions happen to work best for them. This mapping is a
software/UX layer decision, separate from the underlying classifier.

## SSVEP Target Registry: reserved vs dynamic frequencies (2026-08-19)

Per Grok's priority list (Note 10/11), the SSVEP frequency pool is now
managed centrally by `TargetRegistry` rather than each feature picking its
own frequencies. CONFIRM (yes_target/no_target) and SCROLL
(up/down, optionally fast/slow tiers) get permanently reserved frequencies
that never change during a session; everything else (UI grid, keyboard
letter groups, prediction bar entries) draws only from the remaining
"dynamic" pool. This guarantees confirm and scroll markers - which can be
on-screen simultaneously with other content - never collide with whatever
dynamic targets happen to be showing.

The default frequency pool was expanded from 6 to 10 entries to make room
for these reservations while still leaving a usable dynamic pool
(currently 4 with the default tiered scroll config). If pool size ever
becomes a real hardware constraint, TargetRegistry safely falls back to
single-tier scroll (no fast tier) rather than starving the dynamic pool,
and raises a clear error rather than silently misbehaving if the pool is
too small to support confirm + scroll + at least 2 dynamic targets.

## Why a simulator instead of building against real hardware from day one

No EEG/SSVEP hardware exists yet (hardware acquisition is funding-dependent,
expected early next year per project notes). Building the full software
stack - calibration UX, command policy, future UI - against a simulated input
source lets real product work happen now, and de-risks the eventual hardware
integration to "swap one module," rather than starting software from zero
once hardware arrives.
