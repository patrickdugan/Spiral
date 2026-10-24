"""Runtime shims: the in-runtime half of the control plane. Each one turns a
runtime's native tool call into a proposal with provenance and enforces the
control module's answer before the runtime dispatches the call."""
