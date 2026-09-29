# Security Policy

## Supported versions

PipeFuzz is pre-1.0 software. Security fixes are provided for the current `0.1.x` line only.

| Version | Supported |
| --- | --- |
| 0.1.x | Yes |
| Earlier or unreleased versions | No |

## Reporting a vulnerability

Do not publish exploit details in a public issue. If the repository host provides private vulnerability reporting or security advisories, use that channel. Otherwise, contact the project maintainers privately through the repository hosting platform before disclosing details.

Include:

- affected PipeFuzz and runtime versions;
- operating system and Java version;
- a minimal reproduction that does not contain sensitive production data;
- impact and likely attack conditions;
- any proposed mitigation.

PipeFuzz v0.1 runs locally and intentionally has no telemetry, authentication, network service, or external API integration. Generated and user-provided data remain in the local Spark process unless the tested transformation itself sends data elsewhere.

Invariant, transformation, and Spark failure reports include the minimized generated input records and configured schema names in local terminal output. CI logs or redirected output containing these reports should therefore be handled as project data. PipeFuzz does not sandbox transformation code; a transformation can access any network, files, credentials, or services available to the Python process.
