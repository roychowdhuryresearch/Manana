"""Experiment registry — logs every run with config, description, and results.

Usage:
    from self_learning.registry import Registry

    reg = Registry()
    run_id = reg.start_run(
        script="run_test_comparison.py",
        config={"n_test": 100, "cohort": "csv", "top_k": 5, "weighting": "linear"},
        description="Bayesian ensemble on 100 CSV test cases, no dedup, rank prior 0.85/0.11/0.04",
    )

    # ... run experiment ...

    reg.finish_run(run_id, metrics={"top1": 0.78, "top3": 0.87}, output_dir="path/to/outputs")
"""

import json
import os
from datetime import datetime

_HERE = os.path.dirname(os.path.abspath(__file__))
REGISTRY_PATH = os.path.join(_HERE, "experiment_registry.json")


def _load_registry() -> list[dict]:
    if os.path.exists(REGISTRY_PATH):
        with open(REGISTRY_PATH, encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_registry(entries: list[dict]):
    with open(REGISTRY_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)


class Registry:
    def __init__(self):
        self.entries = _load_registry()

    def start_run(
        self,
        script: str,
        config: dict,
        description: str,
    ) -> str:
        """Register a new run. Returns a run_id."""
        run_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        entry = {
            "run_id": run_id,
            "script": script,
            "config": config,
            "description": description,
            "started": datetime.now().isoformat(),
            "finished": None,
            "status": "running",
            "metrics": None,
            "output_dir": None,
        }

        self.entries.append(entry)
        _save_registry(self.entries)
        return run_id

    def finish_run(
        self,
        run_id: str,
        metrics: dict,
        output_dir: str | None = None,
    ):
        """Mark a run as complete with its results."""
        for entry in self.entries:
            if entry["run_id"] == run_id:
                entry["finished"] = datetime.now().isoformat()
                entry["status"] = "complete"
                entry["metrics"] = metrics
                entry["output_dir"] = output_dir
                break
        _save_registry(self.entries)

    def fail_run(self, run_id: str, error: str):
        """Mark a run as failed."""
        for entry in self.entries:
            if entry["run_id"] == run_id:
                entry["finished"] = datetime.now().isoformat()
                entry["status"] = "failed"
                entry["error"] = error
                break
        _save_registry(self.entries)

    def list_runs(self, script: str | None = None, status: str | None = None) -> list[dict]:
        """List runs, optionally filtered."""
        results = self.entries
        if script:
            results = [e for e in results if e["script"] == script]
        if status:
            results = [e for e in results if e["status"] == status]
        return results

    def get_run(self, run_id: str) -> dict | None:
        for entry in self.entries:
            if entry["run_id"] == run_id:
                return entry
        return None

    def print_summary(self):
        """Print a human-readable summary of all runs."""
        if not self.entries:
            print("No runs registered.")
            return

        print(f"\n{'='*90}")
        print(f"{'Run ID':<18} {'Script':<30} {'Status':<10} {'Key Metric':<15}")
        print(f"{'-'*90}")
        for e in self.entries:
            metric_str = ""
            if e.get("metrics"):
                # Show first metric
                key = list(e["metrics"].keys())[0]
                val = e["metrics"][key]
                metric_str = f"{key}={val}"
            print(f"{e['run_id']:<18} {e['script']:<30} {e['status']:<10} {metric_str:<15}")
            if e.get("description"):
                print(f"  {'':18} {e['description'][:70]}")
        print(f"{'='*90}\n")
