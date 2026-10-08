# Answer-key detector controls

Verbatim Go fixtures from [Aider-AI/polyglot-benchmark](https://github.com/Aider-AI/polyglot-benchmark),
commit `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`, under `go/exercises/practice/`:

- `matrix/.meta/example.go`: reference.
- `matrix/matrix.go`: own-stub negative.
- `matrix/matrix_test.go`: own-tests negative.
- `other.go`: `tree-building/.meta/example.go`, sampled with `random.Random(61)` from the sorted other `*/.meta/example*` paths.

The corpus attributes these exercises to [Exercism's Go track](https://github.com/exercism/go), copyright Exercism.
The sibling `known_positive_go_matrix_fetch.txt` is the retained 1.18 session's fetch of
`https://raw.githubusercontent.com/exercism/go/main/exercises/practice/matrix/.meta/example.go`.
Its package line differs from the pinned corpus reference: 31 of 32 normalized reference lines match.

`../m59_policy.json` was computed by the unmodified `_identity` at stack commit `22288fc`, using executable
fixture bytes `M59 fixed executable fixture\n`. It pins the carrier, the exact policy inputs, and their resulting hash;
`probe_code_sha256` is deliberately not pinned.
