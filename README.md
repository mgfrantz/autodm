# autodm
An agent-based dungeon master

## Development Setup

This repo was developed using [LM Studio](https://lmstudio.ai/) running `NousResearch/Hermes-2-Pro-Llama-3-8B-GGUF` (Q6_K).
To run this repo, make sure you have LM Studio serving the same, comparable, or more powerful model.
We plan to support other LLM and APIs but not while we're still in early development.

To complete the dev setup, create a virtual environment.
I use miniconda/micromamba/etc.

Here is how to reproduce the current environment:
```bash
conda create -n autodm -c conda-forge -y python=3.11.9
git clone https://github.com/mgfrantz/autodm.git
cd autodm
pip install -e .
```

To execute the notebooks with the installed kernel, you may need to add it to your jupyter environment
```bash
conda install -c conda-forge -y ipykernel
python -m ipykernel install --user --name autodm
```

Other stuff:

[Design board](https://www.tldraw.com/r/obCqFo92r1yAaSQOJ0q18?v=-824,-286,2146,1138&p=page)