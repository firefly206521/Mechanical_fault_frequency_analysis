from dataclasses import replace

import numpy as np
import pytest

from q4_adaptive_sensor_layout.core import (
    Q4V1Config,
    evaluate_layout,
    exhaustive_layouts,
    generate_candidate_points,
    generate_noise,
    greedy_layout,
    prescreen_points,
    response_similarity,
)


def test_generate_candidate_points_returns_correct_count_and_ids():
    points = generate_candidate_points(12, seed=123)
    assert len(points) == 12
    assert points[0].point_id == "v1_p000"
    assert points[-1].point_id == "v1_p011"


def test_prescreen_respects_limits():
    cfg = Q4V1Config(prescreen_min=5, prescreen_max=8)
    points = generate_candidate_points(24, seed=123)
    selected, rows = prescreen_points(points, cfg)
    assert 5 <= len(selected) <= 8
    assert len(rows) == len(points)
    assert all(points[index].installable for index in selected)


def test_prescreen_raises_when_too_few_installable_points():
    cfg = Q4V1Config(prescreen_min=5, prescreen_max=8)
    points = [replace(point, installable=False) for point in generate_candidate_points(12, seed=123)]
    with pytest.raises(ValueError, match="at least three installable"):
        prescreen_points(points, cfg)


def test_exhaustive_finds_layout_at_least_as_good_as_greedy():
    cfg = Q4V1Config(prescreen_min=6, prescreen_max=8)
    points = generate_candidate_points(24, seed=321)
    selected, _ = prescreen_points(points, cfg)
    greedy = greedy_layout(points, selected, cfg=cfg)
    exhaustive = exhaustive_layouts(points, selected, top_n=1, cfg=cfg)[0]
    assert exhaustive.objective >= greedy.objective - 1e-12


def test_layout_objective_uses_fusion_detection_proxy():
    cfg = Q4V1Config(prescreen_min=6, prescreen_max=8)
    points = generate_candidate_points(24, seed=321)
    selected, _ = prescreen_points(points, cfg)
    evaluation = evaluate_layout(points, selected[:3], cfg=cfg)
    assert evaluation.detection_min_lambda > 0.0
    assert evaluation.detection_mean_lambda > 0.0
    assert evaluation.objective < 10.0 * evaluation.mean_lambda


def test_response_similarity_zero_vectors_are_not_forced_redundant():
    a = np.zeros(4, dtype=complex)
    b = np.zeros(4, dtype=complex)
    assert response_similarity(a, b) == 0.0


def test_generate_noise_supports_correlated_sensor_noise():
    rng = np.random.default_rng(123)
    noise = generate_noise(np.asarray([1.0, 2.0, 3.0]), 2000, rng, correlation=0.5)
    assert noise.shape == (3, 2000)
    corr = np.corrcoef(noise)[0, 1]
    assert corr > 0.25


def test_generate_noise_rejects_invalid_correlation():
    rng = np.random.default_rng(123)
    with pytest.raises(ValueError, match="noise correlation"):
        generate_noise(np.asarray([1.0, 2.0]), 10, rng, correlation=1.0)
