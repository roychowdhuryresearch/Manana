#!/bin/bash
cd /home/shreyas/NLP/consilium

# Run the experiment
uv run python self_learning/run_loop.py --batch-size 10 2>&1 | tee self_learning/outputs/latest_run.log

# Stage and push results
git add self_learning/outputs/ self_learning/sampler.py self_learning/run_loop.py self_learning/prompts/ notes/
git commit -m "Self-learning stratified run: $(tail -5 self_learning/outputs/latest_run.log | head -1)

Co-Authored-By: Claude Opus 4.6 (1M context) <noreply@anthropic.com>"
git push origin cons_v2
