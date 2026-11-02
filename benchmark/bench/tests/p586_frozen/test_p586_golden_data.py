"""Baseline (a09a5a7e) `reconcile_item` reports of the non-`client_inactivity` cases built by `conftest.invariant_cases()`,
captured by running the baseline code (`dataclasses.asdict(ItemReport)`) before any P586 change. Data only: no tests."""
import json

GOLDEN = json.loads(r"""
{
 "budget_kill_boundary": {
  "case": "kill_boundary",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2, len(request_usage)=2, the evidence states 2",
    "ok": true
   },
   "failed_lines": {
    "detail": "0 unexpected Request failed line(s) (allowed: none for this outcome)",
    "ok": true
   },
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=2 != |C|+|F|=2",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": true
   }
  },
  "ok": true,
  "problems": [],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 8.798781565625177,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 },
 "budget_kill_boundary_count_mismatch": {
  "case": "kill_boundary",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2, len(request_usage)=2, the evidence states 3",
    "ok": false
   },
   "failed_lines": {
    "detail": "0 unexpected Request failed line(s) (allowed: none for this outcome)",
    "ok": true
   },
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=2 != |C|+|F|=2",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": true
   }
  },
  "ok": false,
  "problems": [
   "boundary_count: |C|=2, len(request_usage)=2, the evidence states 3"
  ],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 8.798781565625177,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 },
 "completed": {
  "case": "completed",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2, len(request_usage)=2, the evidence states 2",
    "ok": true
   },
   "failed_lines": {
    "detail": "0 unexpected Request failed line(s) (allowed: none for this outcome)",
    "ok": true
   },
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=2 != |C|+|F|=2",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": true
   }
  },
  "ok": true,
  "problems": [],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 8.798781565625177,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 },
 "completed_token_mismatch": {
  "case": "completed",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2, len(request_usage)=2, the evidence states 2",
    "ok": true
   },
   "failed_lines": {
    "detail": "0 unexpected Request failed line(s) (allowed: none for this outcome)",
    "ok": true
   },
   "pairing": {
    "detail": "positional pairing fails at position 1: tokens differ (|C|=2, request_usage=2)",
    "ok": false
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=2 != |C|+|F|=2",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 2, 'requests_failed': 0, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": true
   }
  },
  "ok": false,
  "problems": [
   "pairing: positional pairing fails at position 1: tokens differ (|C|=2, request_usage=2)"
  ],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 8.798781565625177,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 },
 "completed_with_a_failed_line": {
  "case": "completed",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2, len(request_usage)=2, the evidence states 2",
    "ok": true
   },
   "failed_lines": {
    "detail": "1 unexpected Request failed line(s) (allowed: none for this outcome)",
    "ok": false
   },
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=3 != |C|+|F|=3",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": true
   }
  },
  "ok": false,
  "problems": [
   "failed_lines: 1 unexpected Request failed line(s) (allowed: none for this outcome)"
  ],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": null,
    "decode_tok_s": null,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": null,
    "error": "stream_closed_before_completion",
    "generated_tokens": null,
    "prompt_tokens": null,
    "session": null
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 7.698803750099614,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 },
 "probe_kill_completed_unaccounted": {
  "case": "kill_completed_unaccounted",
  "checks": {
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=3 != |C|+|F|=3",
    "ok": true
   },
   "unaccounted_count": {
    "detail": "request_usage has 2 entries, the evidence states 2",
    "ok": true
   },
   "unaccounted_inflight": {
    "detail": "no in-flight message in the abort manifest",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 3, 'requests_started': 3, 'requests_failed': 0, 'prompt_tokens_total': 12308, 'generated_tokens_total': 77706} != log {'requests_completed': 3, 'requests_started': 3, 'requests_failed': 0, 'prompt_tokens_total': 12308, 'generated_tokens_total': 77706}",
    "ok": true
   }
  },
  "ok": true,
  "problems": [],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 21.3,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 3645.0,
    "error": null,
    "generated_tokens": 77510,
    "prompt_tokens": 5366,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 3486.421403529236,
   "generated_tokens": 77706,
   "prompt_tokens": 12308,
   "proposed": 0,
   "requests": 3
  }
 },
 "probe_kill_failed_without_inflight_evidence": {
  "case": "kill_inflight_failed",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2 != the evidence's completed count 2",
    "ok": true
   },
   "failed_line": {
    "detail": "the single failed line must be the last of the window with error=stream_closed_before_completion and |S|=|C|+1",
    "ok": true
   },
   "inflight_evidence": {
    "detail": "a trailing failed line, but the structured evidence says no request was in flight",
    "ok": false
   },
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=3 != |C|+|F|=3",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": true
   }
  },
  "ok": false,
  "problems": [
   "inflight_evidence: a trailing failed line, but the structured evidence says no request was in flight"
  ],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": null,
    "decode_tok_s": null,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": null,
    "error": "stream_closed_before_completion",
    "generated_tokens": null,
    "prompt_tokens": null,
    "session": null
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 7.698803750099614,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 },
 "probe_kill_inflight_failed": {
  "case": "kill_inflight_failed",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2 != the evidence's completed count 2",
    "ok": true
   },
   "failed_line": {
    "detail": "the single failed line must be the last of the window with error=stream_closed_before_completion and |S|=|C|+1",
    "ok": true
   },
   "inflight_evidence": {
    "detail": "a trailing failed line, but the structured evidence says no request was in flight",
    "ok": true
   },
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=3 != |C|+|F|=3",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": true
   }
  },
  "ok": true,
  "problems": [],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": null,
    "decode_tok_s": null,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": null,
    "error": "stream_closed_before_completion",
    "generated_tokens": null,
    "prompt_tokens": null,
    "session": null
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 7.698803750099614,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 },
 "probe_kill_worker_delta_mismatch": {
  "case": "kill_inflight_failed",
  "checks": {
   "boundary_count": {
    "detail": "|C|=2 != the evidence's completed count 2",
    "ok": true
   },
   "failed_line": {
    "detail": "the single failed line must be the last of the window with error=stream_closed_before_completion and |S|=|C|+1",
    "ok": true
   },
   "inflight_evidence": {
    "detail": "a trailing failed line, but the structured evidence says no request was in flight",
    "ok": true
   },
   "pairing": {
    "detail": "",
    "ok": true
   },
   "serial": {
    "detail": "",
    "ok": true
   },
   "session_backend": {
    "detail": "every completed line must carry session='ses_e69d1f63bffe7ieF7PENCpeugn' backend=cached_session; got [('ses_e69d1f63bffe7ieF7PENCpeugn', 'cached_session')]",
    "ok": true
   },
   "started_terminated": {
    "detail": "|S|=3 != |C|+|F|=3",
    "ok": true
   },
   "worker_deltas": {
    "detail": "worker delta {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 2, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}",
    "ok": false
   }
  },
  "ok": false,
  "problems": [
   "worker_deltas: worker delta {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 2, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196} != log {'requests_completed': 2, 'requests_started': 3, 'requests_failed': 1, 'prompt_tokens_total': 6942, 'generated_tokens_total': 196}"
  ],
  "requests": [
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 9.335,
    "error": null,
    "generated_tokens": 125,
    "prompt_tokens": 2951,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": "cached_session",
    "decode_tok_s": 25.7,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": 5.075,
    "error": null,
    "generated_tokens": 71,
    "prompt_tokens": 3991,
    "session": "ses_e69d1f63bffe7ieF7PENCpeugn"
   },
   {
    "backend": null,
    "decode_tok_s": null,
    "draft_kind": null,
    "draft_n": null,
    "draft_n_accepted": null,
    "draft_rounds": null,
    "elapsed_s": null,
    "error": "stream_closed_before_completion",
    "generated_tokens": null,
    "prompt_tokens": null,
    "session": null
   }
  ],
  "totals": {
   "accepted": 0,
   "decode_s": 7.698803750099614,
   "generated_tokens": 196,
   "prompt_tokens": 6942,
   "proposed": 0,
   "requests": 2
  }
 }
}
""")
