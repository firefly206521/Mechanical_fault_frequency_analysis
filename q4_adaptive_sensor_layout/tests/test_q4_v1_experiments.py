from q4_adaptive_sensor_layout.core import Q4V1Config
from q4_adaptive_sensor_layout.experiments import summarize_validated_layouts


def test_validated_layout_summary_penalizes_false_alarm_excess():
    rows = [
        {
            "layout": "a",
            "regions": "r1",
            "benchmark": "candidate",
            "snr_db": -20.0,
            "pd_source_mean": 0.80,
            "pd_source_min": 0.70,
            "p_fa": 0.20,
        },
        {
            "layout": "b",
            "regions": "r2",
            "benchmark": "candidate",
            "snr_db": -20.0,
            "pd_source_mean": 0.75,
            "pd_source_min": 0.65,
            "p_fa": 0.04,
        },
    ]
    summary = summarize_validated_layouts(rows, Q4V1Config(p_fa=0.05))
    assert summary[0]["layout"] == "b"
    assert summary[0]["validated_role"] == "v1_validated_best"


def test_validated_layout_summary_uses_configured_weights():
    rows = [
        {
            "layout": "balanced",
            "regions": "r1",
            "benchmark": "candidate",
            "snr_db": -20.0,
            "pd_source_mean": 0.70,
            "pd_source_min": 0.70,
            "p_fa": 0.04,
        },
        {
            "layout": "average",
            "regions": "r2",
            "benchmark": "candidate",
            "snr_db": -20.0,
            "pd_source_mean": 0.90,
            "pd_source_min": 0.20,
            "p_fa": 0.04,
        },
    ]
    min_focused = Q4V1Config(validation_weight_pd=0.0, validation_weight_low_snr=0.0, validation_weight_min_pd=1.0)
    mean_focused = Q4V1Config(validation_weight_pd=1.0, validation_weight_low_snr=0.0, validation_weight_min_pd=0.0)
    assert summarize_validated_layouts(rows, min_focused)[0]["layout"] == "balanced"
    assert summarize_validated_layouts(rows, mean_focused)[0]["layout"] == "average"
