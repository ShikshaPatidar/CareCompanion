# Run sheet: commands, evidence and screenshot numbers

Run in this order. Screenshot only what you actually run. Blur endpoints, keys and subscription IDs.
Figure numbers refer to Appendix A of `CareCompanion_IBM_Written_Application.docx`; adjust to your copy.

| Step | Command | Capture as evidence |
|---|---|---|
| 1 | `make test` | terminal showing all tests passing |
| 2 | `make eval-offline` | 17/17 deterministic cases |
| 3 | `make check` | first live model reply |
| 4 | `make index` | files indexed and the agent version |
| 5 | `make chat` | (a) policy answer with policy number, (b) booking, (c) duplicate refusal, (d) emergency message |
| 6 | `make discharge` | JSON, summary and "Verification: PASSED" |
| 7 | `make eval-baseline` then `make eval-hardened` then `make compare` | the before/after table (your strongest evidence) |
| 8 | `make eval-injection` | injection results |
| 9 | Foundry portal, Application Insights | a trace showing coordinator, specialist and tool spans (needs `APPLICATIONINSIGHTS_CONNECTION_STRING`) |
| 10 | `head var/audit.jsonl` | audit events with content redacted |
| 11 | optional: `make api` and `make api-test`, then set `APPOINTMENTS_API_URL` | .NET service running and `make chat` booking through it |
| 12 | `make clean-cloud` | cleanup output |

If a live evaluation case fails, look at the reply in `reports/<label>.json` before changing anything:
decide whether the assistant or the expectation is wrong, then record what you changed and why. That
iteration is real evidence for the "testing" section.
