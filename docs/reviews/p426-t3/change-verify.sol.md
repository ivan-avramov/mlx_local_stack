P1  
Location: `benchmark/bench/p426_plan.py:169-246`  
Severity: major  
Evidence: confirmed  
Problem: Design-round-2 finding 4 is not resolved. `restore_diff_problems` is not patch-exact: it ignores all changed comment lines in the seeding test, accepts any two added code lines containing `joint_v1` and `registry`, strips trailing comments from registry lines, and accepts any number or placement of `PROVISIONAL P426` notes.  
Concrete failure scenario: ON replaces the real seeding assertion with two tautologies containing those strings and adds an unrelated comment hunk. The check accepts an ON commit beyond §11’s restore. The candidate tests cover extra code, but not this case; the frozen comment-hunk test has so far passed vacuously at the earlier field-name refusal.  
Proposed change: derive the complete expected bytes or exact `-U0` patches for both files from OFF, then require equality—including comments, line placement, hunk count and one exact provisional note.

P2  
Location: `docs/specs/p426-fable-mtp-recert.md:32-45,93,174`  
Severity: major  
Evidence: confirmed  
Problem: Design-round-1 finding 2’s documentation outcome is not resolved. The new S′ paragraph was appended without retiring contradictory active instructions: the plan still declares S the “one serving build,” requires its old worktree and overlay arms, names `<S's fork sha>` and the old M1 path, and says to run eight fork audits rather than S′’s nine.  
Concrete failure scenario: An operator follows the later `Arms` bullet and creates the old overlay-based ON arm; the S′ sequencer refuses `--registry-on`, preventing the reviewed rerun.  
Proposed change: replace or explicitly mark the S-era build/worktree/arms instructions as historical, and update the active M1 and gate instructions to S′, committed arms, labelled paths and nine derived audits.
