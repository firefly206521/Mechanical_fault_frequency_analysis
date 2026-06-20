# Q4 V1 Adaptive Sensor Layout

This package implements Q4 V1. It is independent from Q4 V0 in `q4_sensor_layout/`.

V1 builds a parameterized structural example, generates dimensionless candidate surface points, prescreens them by whitened response strength and redundancy, searches three-sensor layouts, and validates selected layouts with GLRT Monte Carlo.

The V1 objective uses a fused GLRT detection proxy: sensor responses are weighted by inverse noise variance before scoring the weakest and average fault-source detection strength. This keeps the analytic search target aligned with the Monte Carlo detector used for validation.

Run smoke:

```powershell
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile smoke
```

Run medium:

```powershell
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium
```

Run a robustness diagnostic with response perturbation and correlated sensor noise:

```powershell
python -m q4_adaptive_sensor_layout.run_q4_v1 --profile medium --output-dir q4_sensor_layout_v1_results_robustness_medium --response-gain-jitter 0.15 --response-phase-jitter 0.20 --noise-correlation 0.30
```

Default output directory:

```text
q4_sensor_layout_v1_results/
|- README.md
|- paper/
|  |- q4_v1_adaptive_report.md
|  |- q4_v1_selected_regions.csv
|  |- q4_v1_validated_layouts.csv
|  |- q4_v1_mesh_convergence.csv
|  |- q4_v1_robust_detection.csv
|  |- q4_v1_pd_snr_curve.png
|  `- q4_v1_layout_heatmap.png
`- raw/
   |- q4_v1_candidate_points.csv
   |- q4_v1_prescreen_scores.csv
   |- q4_v1_layout_trials.csv
   `- q4_v1_runtime.txt
```

All V1 output files use the `q4_v1_` prefix. Coordinates are dimensionless model coordinates, not real-machine installation coordinates.
