# PII Software

Core software for PII, a thought-and-gaze controlled interface (EEG discrete
commands + SSVEP-based selection). This repo covers the software layer that
can be built and tested *before* real EEG hardware exists, using a simulated
input source in place of the real decoder.

## Structure

- `core/` - Hardware-agnostic logic. `events.py` defines the shared event
  format; `command_policy.py` implements the confirm-before-commit safeguard.
  Nothing here knows or cares whether input came from real EEG or the simulator.
- `simulator/` - `fake_brain.py`: a stand-in input source for development.
  Produces realistic correct/wrong/idle outputs matching our real accuracy
  data (~65-75% for a calibrated best-pair 2-command system), not an
  idealized perfect input.
- `tests/` - Proves the pieces work correctly together.
- `docs/` - Design decisions and rationale, so future sessions (or
  collaborators) don't have to re-derive *why* something was built a certain way.

## Running the tests

```
python3 tests/test_policy_with_simulator.py
```

No dependencies beyond the Python standard library at this stage.

## Design philosophy

When real EEG/SSVEP hardware arrives, only `simulator/fake_brain.py` should
need to be replaced with a real decoder module producing the same
`BrainEvent` objects. Everything built against the simulator - calibration
flow, command policy, future UI - should keep working unchanged. This seam
is the whole point of the simulator existing.

See `docs/design_decisions.md` for the reasoning behind key choices
(confirm-before-commit thresholds, accuracy assumptions, etc.).
