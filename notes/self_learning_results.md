## Stratified Training (trained on 50 patients stratified, eval on 20)

### Table 1: Overall EM@3 and Jaccard


| Cohort      | Method                 | V1 EM@3  | V1 Jac   | V2 EM@3  | V2 Jac   | V3 EM@3  | V3 Jac   |
| ----------- | ---------------------- | -------- | -------- | -------- | -------- | -------- | -------- |
| **A (CSV)** | Single-agent           | 66.0     | .752     | 74.4     | .837     | 75.6     | .855     |
|             | Consilium              | **79.5** | **.864** | **88.0** | **.945** | **91.0** | **.935** |
|             | Self-learning (single) | 73.4     | .828     | 82.0     | .895     | 82.0     | .898     |
|             | Self-learning (multi)  | 71.8     | .800     | 83.5     | .898     | 85.9     | .921     |
| **B (PDF)** | Single-agent           | 65.9     | .769     | 70.1     | .826     | 71.8     | .830     |
|             | Consilium              | **71.5** | **.818** | **83.0** | **.903** | **86.8** | **.934** |
|             | Self-learning (single) | 72.0     | .822     | 81.9     | .900     | 81.7     | .885     |
|             | Self-learning (multi)  | 76.2     | .849     | 85.9     | .930     | 88.3     | .937     |


---

### Table 2: Monotherapy vs Polytherapy EM@3


| Cohort      | Method                 | Mono V1  | Mono V2  | Mono V3  | Poly V1  | Poly V2  | Poly V3  |
| ----------- | ---------------------- | -------- | -------- | -------- | -------- | -------- | -------- |
| **A (CSV)** | Single-agent           | 79.2     | 85.0     | 89.7     | 13.4     | 40.5     | 41.8     |
|             | Consilium              | **92.1** | **95.7** | **97.4** | 29.9     | **63.3** | **75.5** |
|             | Self-learning (single) | 86.7     | 91.8     | 91.6     | 24.5     | 50.0     | 59.7     |
|             | Self-learning (multi)  | 84.1     | 92.3     | 93.9     | 26.4     | 55.0     | 67.5     |
| **B (PDF)** | Single-agent           | 76.3     | 80.9     | 82.1     | 41.1     | 50.4     | 54.8     |
|             | Consilium              | 80.0     | **94.1** | **95.7** | **51.1** | 62.8     | **72.2** |
|             | Self-learning (single) | 87.4     | 91.8     | 90.8     | 35.1     | 63.8     | 66.7     |
|             | Self-learning (multi)  | 90.5     | 97.0     | 96.1     | 42.3     | 65.6     | 75.4     |


---

## Doctor Feedback Training (trained on 20 doctor-reviewed patients, eval on 20)

### Table 3: Overall EM@3 and Jaccard


| Cohort      | Method                 | V1 EM@3  | V1 Jac   | V2 EM@3  | V2 Jac   | V3 EM@3  | V3 Jac   |
| ----------- | ---------------------- | -------- | -------- | -------- | -------- | -------- | -------- |
| **A (CSV)** | Single-agent           | 66.0     | .752     | 74.4     | .837     | 75.6     | .855     |
|             | Consilium              | **79.5** | **.864** | **88.0** | **.945** | **91.0** | **.935** |
|             | Self-learning (single) | 67.1     | .782     | 79.3     | .883     | 76.5     | .866     |
|             | Self-learning (multi)  | 51.3     | .648     | 57.2     | .730     | 63.3     | .774     |
| **B (PDF)** | Single-agent           | 65.9     | .769     | 70.1     | .826     | 71.8     | .830     |
|             | Consilium              | **71.5** | **.818** | **83.0** | **.903** | **86.8** | **.934** |
|             | Self-learning (single) | 65.9     | .789     | 73.7     | .856     | 74.2     | .842     |
|             | Self-learning (multi)  | 59.5     | .720     | 59.9     | .763     | 63.9     | .763     |


Single: `loop_20260413_1804` r2 | Multi: `loop_20260413_1445` r1

### Table 4: Monotherapy vs Polytherapy EM@3


| Cohort      | Method                 | Mono V1  | Mono V2  | Mono V3  | Poly V1  | Poly V2  | Poly V3  |
| ----------- | ---------------------- | -------- | -------- | -------- | -------- | -------- | -------- |
| **A (CSV)** | Single-agent           | 79.2     | 85.0     | 89.7     | 13.4     | 40.5     | 41.8     |
|             | Consilium              | **92.1** | **95.7** | **97.4** | 29.9     | **63.3** | **75.5** |
|             | Self-learning (single) | 75.9     | 82.9     | 84.0     | 34.3     | 67.9     | 59.2     |
|             | Self-learning (multi)  | 59.4     | 63.4     | 72.6     | 20.9     | 38.0     | 41.8     |
| **B (PDF)** | Single-agent           | 76.3     | 80.9     | 82.1     | 41.1     | 50.4     | 54.8     |
|             | Consilium              | 80.0     | **94.1** | **95.7** | **51.1** | 62.8     | **72.2** |
|             | Self-learning (single) | 76.6     | 81.5     | 82.6     | 40.2     | 59.4     | 60.3     |
|             | Self-learning (multi)  | 72.3     | 67.5     | 72.0     | 28.9     | 46.1     | 50.4     |


