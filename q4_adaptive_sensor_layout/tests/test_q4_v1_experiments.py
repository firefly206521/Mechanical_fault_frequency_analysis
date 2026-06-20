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
    summary = summarize_validated_layouts(rows, target_p_fa=0.05)
    assert summary[0]["layout"] == "b"
    assert summary[0]["validated_role"] == "v1_validated_best"
