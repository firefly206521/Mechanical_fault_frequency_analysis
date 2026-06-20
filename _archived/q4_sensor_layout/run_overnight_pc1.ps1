$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
python -m q4_sensor_layout.run_q4_overnight --profile pc1 --root-output q4_sensor_layout_results_overnight

