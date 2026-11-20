# Addendum — technical notes

## Local model options (subagent hardware assessment, 2026-11-20)
- Hardware: RTX 3060 Laptop 6 GB VRAM, i7-11800H, 14 GiB RAM (~7.7 GiB free), 53 GB free disk. Ollama and llama.cpp not installed; Python via miniconda.
- **Decision: the project uses only `qwen3:4b-instruct-2507-q4_K_M`** for every role (assistant and codegen). The notes below are the original pre-decision assessment.
- Primary candidate: `qwen3:4b` (~2.5-2.8 GB Q4). Tool calling, thinking can be disabled, JSON schema via Ollama `format`. Speed estimate 40-70 tok/s (unverified).
- Alt: `qwen2.5-coder:7b` (~4.7 GB) for Playwright code generation (Phase 2); tool-calling support unconfirmed. Others: phi4-mini, llama3.2:3b (weaker at code); qwen3:8b is tight on 6 GB.
- Fallback: free-tier Groq / Google AI Studio (verify "no paid API" rules and rate limits), or qwen3:1.7b.
- Caveats: cap context at 4-8k (KV cache overflows 6 GB), disable thinking for latency, pre-filter element JSON, validate JSON and retry, close heavy apps for 7B+. Speeds come from secondary blogs; benchmark on this machine.
