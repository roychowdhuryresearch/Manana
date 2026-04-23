# Multi-Seed Eval Results — OSS-120B, 5 Seeds

Date: 2026-04-22

Eval: CSV holdout (excl. 70 SL train+eval pids) + full PDF (367 patients), all visits.

## Summary Table — Mean across 5 Seeds (same format as textgrad_runs.md)

### Table 1: EM@3 (%) by Cohort and Visit


| Cohort      | Method                       | V1 EM@3 | V2 EM@3 | V3 EM@3 |
| ----------- | ---------------------------- | ------- | ------- | ------- |
| **A (CSV)** | Single-agent                 | 66.0    | 74.4    | 75.6    |
|             | Consilium                    | 79.5    | 88.0    | 91.0    |
|             | TextGrad (mean 5 seeds)      | 73.4    | 79.3    | 78.4    |
|             | Buffer Single (mean 5 seeds) | 73.8    | 83.8    | 84.5    |
|             | Buffer Multi (mean 5 seeds)  | 77.1    | 87.3    | 89.6    |
| **B (PDF)** | Single-agent                 | 65.9    | 70.1    | 71.8    |
|             | Consilium                    | 71.5    | 83.0    | 86.8    |
|             | TextGrad (mean 5 seeds)      | 63.6    | 75.2    | 76.0    |
|             | Buffer Single (mean 5 seeds) | 72.1    | 83.0    | 82.4    |
|             | Buffer Multi (mean 5 seeds)  | 73.4    | 83.0    | 84.3    |


### Table 2: Mono / Poly EM@3 (%) — Mean across 5 Seeds


| Cohort      | Method                       | Mono V1 | Mono V2 | Mono V3 | Poly V1 | Poly V2 | Poly V3 |
| ----------- | ---------------------------- | ------- | ------- | ------- | ------- | ------- | ------- |
| **A (CSV)** | Single-agent                 | 79.2    | 85.0    | 89.7    | 13.4    | 40.5    | 41.8    |
|             | Consilium                    | 92.1    | 95.7    | 97.4    | 29.9    | 63.3    | 75.5    |
|             | TextGrad (mean 5 seeds)      | 87.4    | 88.1    | 87.3    | 21.9    | 50.7    | 57.7    |
|             | Buffer Single (mean 5 seeds) | 87.0    | 92.1    | 93.2    | 25.3    | 57.0    | 64.2    |
|             | Buffer Multi (mean 5 seeds)  | 89.7    | 92.1    | 95.7    | 26.8    | 58.4    | 67.5    |
| **B (PDF)** | Single-agent                 | 76.3    | 80.9    | 82.1    | 41.1    | 50.4    | 54.8    |
|             | Consilium                    | 80.0    | 94.1    | 95.7    | 51.1    | 62.8    | 72.2    |
|             | TextGrad (mean 5 seeds)      | 73.9    | 87.7    | 87.3    | 39.0    | 52.3    | 57.3    |
|             | Buffer Single (mean 5 seeds) | 82.2    | 92.8    | 92.2    | 48.2    | 65.2    | 66.3    |
|             | Buffer Multi (mean 5 seeds)  | 87.4    | 95.0    | 93.1    | 47.2    | 67.4    | 74.8    |


*Single-agent and Consilium rows from textgrad_runs.md for reference.*