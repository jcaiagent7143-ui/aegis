# Cookbook

Runnable, end-to-end examples that ship with the repo. Each one:

- has a real-world goal,
- demonstrates a different generated harness,
- runs in under 30 seconds against any provider (Mock works for exploration).

| # | File | What it shows |
|---|---|---|
| 01 | [`examples/01_web_research.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/examples/01_web_research.py) | Citation verifier generated for an open-ended research goal |
| 02 | [`examples/02_code_refactor.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/examples/02_code_refactor.py) | AST-diff + test-runner harness for a code task |
| 03 | [`examples/03_data_analysis.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/examples/03_data_analysis.py) | Arithmetic re-checker for a CSV question |
| 04 | [`examples/04_citation_verifier.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/examples/04_citation_verifier.py) | Side-by-side comparison: Aegis vs raw provider on URL validity |
| 05 | [`examples/05_custom_provider.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/examples/05_custom_provider.py) | Plug in your own LLM endpoint |
| 06 | [`examples/06_with_langchain_tools.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/examples/06_with_langchain_tools.py) | Use existing LangChain tools as Aegis tools |
| 07 | [`examples/07_local_only_with_ollama.py`](https://github.com/jcaiagent7143-ui/aegis/blob/main/examples/07_local_only_with_ollama.py) | Fully offline, no API keys |

Run any of them with:

```bash
python examples/01_web_research.py
```

Each script prints both the result and the generated harness so you can see what defenses Aegis built for that specific goal.
