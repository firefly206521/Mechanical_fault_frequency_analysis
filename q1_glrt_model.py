"""Compatibility wrapper for the Q1 GLRT workflow.

Implementation is split under ``q1_glrt/``:
- ``core.py``: numerical computation and simulation
- ``outputs.py``: CSV, Markdown, and figure generation
- ``cli.py``: command-line orchestration
"""

from q1_glrt.cli import main
from q1_glrt.core import (  # re-exported for older notebooks/scripts
    GLRT_PARAMETERS,
    analyze_preprocessing_and_noise,
    build_parameter_table,
    fft_peak_detect_signal,
    glrt_detect_signal,
    recovered_signal,
    run_fft_glrt_simulation,
    run_glrt_q1,
    run_segment_validation,
    synthetic_signal,
)
from q1_glrt.outputs import (
    configure_plot_fonts,
    plot_fft_baseline,
    plot_frequency_error_snr,
    plot_glrt_statistic,
    plot_noise_analysis,
    plot_pd_snr,
    plot_recovered_signal,
    plot_segment_validation,
    write_all_outputs,
    write_csv_outputs,
    write_report,
)

write_parameter_table = build_parameter_table

__all__ = [
    "GLRT_PARAMETERS",
    "analyze_preprocessing_and_noise",
    "build_parameter_table",
    "configure_plot_fonts",
    "fft_peak_detect_signal",
    "glrt_detect_signal",
    "main",
    "plot_fft_baseline",
    "plot_frequency_error_snr",
    "plot_glrt_statistic",
    "plot_noise_analysis",
    "plot_pd_snr",
    "plot_recovered_signal",
    "plot_segment_validation",
    "recovered_signal",
    "run_fft_glrt_simulation",
    "run_glrt_q1",
    "run_segment_validation",
    "synthetic_signal",
    "write_all_outputs",
    "write_csv_outputs",
    "write_parameter_table",
    "write_report",
]


if __name__ == "__main__":
    main()
