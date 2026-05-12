# Assumptions

- The project operates at zone level rather than exact street-level routing.
- One simulation step equals one hour.
- Charging decisions make a vehicle unavailable for that step.
- The Eindhoven zonal load data is used as a proxy for mobility intensity.
- The OD matrix is used to derive relative mobility importance across zones through a deterministic district-to-zone mapping.
- Existing charging points are used when available; otherwise the configured charger count is synthesized deterministically.
- The LLM is restricted to structured planning and never bypasses validation.
