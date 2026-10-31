1. Location: `benchmark/bench/chain_ops.py`, `loaded_images` lsof collection and hash loop  
Severity: major  
Evidence: confirmed — lsof supplies only a pathname; the later hash reopens that pathname rather than hashing the worker’s open file description.  
Problem: the recorded bytes need not be those read by Metal.  
Concrete failure scenario: the worker opens metallib A, then the path is atomically replaced with B. The worker retains A’s vnode, but the receipt hashes B. Both arms can therefore report B while one used A.  
Proposed change: hash at the worker’s metallib-open/load boundary using the same descriptor, and return that digest to the harness. Path hashing cannot establish the required identity.

2. Location: `benchmark/bench/chain_ops.py`, `lsof -Fn` parsing  
Severity: major  
Evidence: confirmed — the code accepts every matching `n` field while ignoring its associated `f`, access-mode, and type fields. On Darwin, omitting `-X` also allows non-descriptor records such as `cwd`, `txt`, and mapped files.  
Problem: an unrelated or inherited `mlx.metallib` can satisfy the presence gate even though Metal never used it.  
Concrete failure scenario: the launcher leaks a readable descriptor for `/common/mlx/lib/mlx.metallib` into a worker that never initializes Metal. The receipt records and hashes it, falsely proving a load.  
Proposed change: preferably obtain the digest from loader instrumentation. At minimum, use Darwin’s `-X`, request and parse NUL-delimited `f/a/t/n` file sets, require a numeric readable regular-file descriptor, and reject ambiguous multiple candidates.

3. Location: `benchmark/bench/chain_ops.py`, point-in-time lsof sampling  
Severity: major  
Evidence: hypothesis — neither the code nor test establishes A1; they only assume the descriptor remains open.  
Problem: lsof reports current descriptors, not files previously used. Descriptor lifetime is an implementation detail that may vary between Metal/MLX versions—the very versions an A/B harness may compare.  
Concrete failure scenario: one MLX/Metal version closes the descriptor after constructing the library. Its actual metallib is absent at receipt time. If both workers also inherited the same unrelated metallib descriptor, their lists compare equal despite using different bytes.  
Proposed change: record the path and digest synchronously when MLX asks Metal to load the library, rather than inferring historical use from a later descriptor snapshot.
