---
name: roadmap
description: Write the satmesh roadmap in plain words for the owner, covering all planned, held and awaiting work. Use when the user runs /roadmap or asks for the roadmap, remaining work, or what is left.
---

# Roadmap

Reader: the owner, who does not know plan codes (E1, E2, F5b, M-A, R1) or internal names.
Output goes in chat; no file unless asked.

## Sources

Read, in this order, only what is needed:

1. `agent-docs/status.md`: workstreams, "Held or awaiting the owner", what is running.
2. `TODO.md`: Next, Later, Last, Needs you.
3. `agent-docs/decisions.md` top rows: recent owner decisions, so settled points are not re-raised.
4. `agent-docs/plan-codes.md`: translate any code met in the sources into the plain thing it is.
5. The memory notes the status names (for example gazebo-last, real-photos-ready, pixtransform-paused).

## Content

Cover everything the owner has discussed as planned, held, deferred or awaiting a decision:

- Group by goal the owner would recognise (buildings and trees, imagery, position accuracy,
  pipeline polish, proving it works, Gazebo and Cesium), not by workstream code.
- Per group: where it stands, what the options are, what is held and why, and what needs the
  owner's decision.
- Final groups: housekeeping waiting on the owner (push, scratch cleanup, old stores, licence
  questions, unseen files), and what is not checked.
- Include the owner's decisions already made as done; leave out settled forks.
- Close with one recommended next decision.

## Style

- First line: the one-sentence state of the project and what is left.
- Plain words: describe what a method does ("a network trained on England lidar to predict
  building heights") instead of naming it by code. Name a method only when the owner uses the
  name, and then say what it does.
- Short bullets under short headings; no tables of codes; no file paths unless the owner needs
  to open the file.
- Facts from the sources only. A source that is stale or contradicts another is flagged in the
  answer.
