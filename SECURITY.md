# Security

## Reporting a problem

Please report a vulnerability privately, through
[GitHub's private report form](https://github.com/humemai/audit-ready-memory/security/advisories/new)
or by email to info@humem.ai. Do not open a public issue for it. Say what you did, what happened,
and which version you used. Expect a first reply within two weeks.

## Known limits, not vulnerabilities

These are documented behaviour. See [limitations](docs/guide/limitations.md).

- Deleted content stays in the log.
- The log is not signed or hash-chained.
- There is no encryption at rest and no access control inside the library.
