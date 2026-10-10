# exp_013 actual formal training

Model session61076 and device observer23594 both exited0. A fresh base/new adapter trained150 records with18 pip-cache family holdouts,38 steps,664.44s total. Training loss1.82690208; held-out NLL step0=2.29601979, step19=2.03074789, step38=1.93470323. Only holdout NLL selected checkpoint38; the24 test cases were not used for selection. Final adapter/config files exactly match selected checkpoint SHA and sizes in adapter-manifest.json. Adapter storage is BF16 with64 tensors; no merge/GGUF export was performed.

All38 gradient observations were finite/nonzero; only1,572,864 LoRA parameters were optimized. Frozen723 base parameters and quantization state had0 training-period changes;64 LoRA parameters changed. Preparation dtype changes are separated from optimizer updates using staged raw/float32 numerical hashes and strict post-preparation freeze baseline. This correctness gate passed and enabled014/015.

Loading allocated peak8163.07MiB/reserved8230MiB exceeded the7168MiB overall target, while loaded allocated3173.89MiB and actual training allocated peak3814.54MiB. This is evidence of execution on the specific Windows8GB+32GB machine, not proof of ample margin or portability to every8GB machine. Device telemetry is sparse total memory rather than exact per-process allocation.

NLL improvement does not establish more reliable/natural file explanations. Matched NF4+RAG evaluation014/015 is required for the implemented adapter effect. Missing fla/causal-conv fast path, broken FlashAttention2 fallback to Xformers and num_items_in_batch/accumulation warning remain environment limits. CPU/disk background load and isolated compiler time were not controlled/measured separately.
