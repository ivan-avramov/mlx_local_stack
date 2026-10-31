- **Location:** `chain_ops_inventory_current.py.txt:43-58, 94-99`  
  **Severity:** major  
  **Evidence:** confirmed — traced in source  
  **Problem:** Canonicalization is restricted to RECORD paths beginning with `..`. Non-editable local installs commonly contain an in-site-packages `direct_url.json` whose URL embeds the worktree path. Its raw RECORD digest therefore enters the inventory unchanged.  
  **Failure scenario:** Each arm runs `pip install <WT>/src/foo` without `-e`. Both installations are valid, but their `foo.dist-info/direct_url.json` files name different worktrees, so every pair gate fails.  
  **Proposed change:** After verifying the original RECORD digest, canonicalize worktree-root occurrences in every RECORD file’s content, not only outside-site-packages entries, and hash that canonical representation.

- **Location:** `chain_ops_inventory_current.py.txt:54-56, 80-93`  
  **Severity:** major  
  **Evidence:** confirmed — traced in source  
  **Problem:** `actual` caches one digest per path without its algorithm. Consequently, “matches any claimant” fails when claimants use different valid RECORD algorithms.  
  **Failure scenario:** The first claimant records SHA-512 of version A; the second records SHA-256 of version B; disk contains B. The first verification compares SHA-512(B) with both SHA-512(A) and SHA-256(B), then aborts although the second claimant matches exactly.  
  **Proposed change:** Cache actual digests by `(path, algorithm)` and compare each claimant using its declared algorithm. Build `shared.matches` from those algorithm-aware comparisons.

- **Location:** `chain_ops_inventory_current.py.txt:76, 94-97`  
  **Severity:** major  
  **Evidence:** confirmed — traced in source  
  **Problem:** Raw substring replacement canonicalizes paths that merely begin with the worktree name, hiding differences outside the allowed root.  
  **Failure scenario:** OFF contains `/x/stack-p426-off-cache/tool` and ON contains `/x/stack-p426-on-cache/tool`. These are distinct sibling paths, not paths under either worktree, but both become `/x/<WT>-cache/tool`, making the inventories equal.  
  **Proposed change:** Replace a root only when it is the complete path or is followed by a path separator. Use a domain-separated encoding so literal `<WT>` bytes cannot collide with substituted roots.

- **Location:** `chain_ops_inventory_current.py.txt:82`  
  **Severity:** minor  
  **Evidence:** confirmed — traced in source  
  **Problem:** Every outside-site-packages entry is now loaded fully into memory with `read_bytes()`, whereas verification previously streamed files.  
  **Failure scenario:** A valid wheel installs a large executable through its scripts/data area; inventory construction can exhaust memory and abort the run.  
  **Proposed change:** Verify and canonicalize incrementally, retaining an overlap of `max_root_length - 1` bytes so root matches spanning chunks are handled correctly.
