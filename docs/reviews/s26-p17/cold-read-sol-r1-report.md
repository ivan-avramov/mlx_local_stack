P1 — major — `benchmark/bench/p426_panel.py:1876`

The rule does not prove the family token is topical; it accepts a token occurring only in one answer. Scenario: KV mode X correctly mentions “NVIDIA,” while mode n16 omits it or gives a worse answer. The entire discordant pair is excluded, conditioning the panel sample on arm output and potentially biasing the paired preference. Restrict the exception to prompt-originated tokens or otherwise pre-treatment metadata. The test only injects the token into both arms (`test_s26_p17_panel_family_token.py:28-36`), so it misses this case.

P2 — minor — `benchmark/bench/p426_panel.py:1882-1887`

Filtering `inputs` before validating optional `--prompts`/`--images` can make a valid existing export command refuse. Scenario: `--prompts` contains all 40 A2 benchmark prompts; nine excluded IDs are now absent from `inputs`, so validation reports “not an item this member judges.” Validate supplied carriers before filtering, or tolerate correctly hashed excluded entries.

No identity leak reaches packets: remaining fully rendered packets are still checked at `p426_panel.py:1387-1389`. For A2, exclusion examines the exact prompt and answer bodies shown, though not the generic packet wrapper. Frozen ingestion and completeness remain internally consistent because they use the filtered manifest and planned-item counts.
