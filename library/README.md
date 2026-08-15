# Curated local library

This directory defines the stable locations expected by profiles. Large binary
models and motion files remain ignored or are distributed separately.

Expected initial contents:

```text
library/
  rigs/soma_humanoid_v1.glb
  animations/humanoid/*.glb
```

All humanoid motion files must target the same bind pose and bone names as the
canonical rig. Keep one action per GLB for predictable import. Motion licensing
must permit redistribution in the game; record provenance alongside each file.
