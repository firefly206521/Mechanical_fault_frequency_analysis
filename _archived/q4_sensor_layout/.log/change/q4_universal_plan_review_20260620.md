# Q4 Universal Sensor Placement Suggestion Review

## Scope

- Reviewed suggestion file: `q4_sensor_layout/.log/suggestion/q4_universal_sensor_placement_plan.md`.
- Current implementation status: Q4 V0 uses six finite candidate sensor positions, a sensitivity/noise scenario matrix, weighted GLRT fusion, and overnight Monte Carlo validation.
- Decision goal: decide whether to adopt the proposed propagation-model and adaptive-grid V1 plan immediately.

## Decision

Partially adopt.

The suggestion is technically stronger than the current V0 model for answering "where should sensors be installed" in a physical continuous space. However, it is not a small improvement to the current Q4 code. It changes the modeling layer from finite candidate selection to a parametric propagation model plus adaptive surface-grid search. That requires new assumptions, new validation, and a new result set. It should not replace the current overnight-tested V0 result at this stage.

## Adopt Now

- Reframe the current result as a finite-candidate robust layout baseline, not a physical global optimum.
- State explicitly that named positions such as `bearing_left`, `gearbox_left`, and `output_shaft` are abstract candidate regions under assumed sensitivity/noise matrices.
- Use the suggestion's propagation-chain language in paper-facing explanation:
  - fault-source excitation
  - structural propagation
  - spatial measurement response
- Add the noncentral-parameter interpretation as theoretical support:

  \[
  \lambda_k(S)=A_k^2 h_{S,k}^{\mathsf H}\Sigma_S^{-1}h_{S,k}.
  \]

  This explains why high sensitivity, low noise, and complementary sensor positions improve detection probability.
- Keep the current overnight results as V0 evidence:
  - `bearing_left+gearbox_left+output_shaft` is the main recommended finite-candidate layout.
  - `bearing_left+bearing_right+gearbox_left` is the close low-SNR/long-window robustness alternative.
- In the Q4 conclusion, report stable regions or candidate-region names rather than overprecise coordinates.

## Do Not Adopt Immediately

- Do not start a new `q4_adaptive_sensor_layout/` implementation before the current Q4 V0 materials are closed.
- Do not replace the overnight Monte Carlo results with unvalidated V1 claims.
- Do not introduce modal parameters, FEM-like geometry, or continuous coordinates unless there is time to run a full new validation.
- Do not claim the current named candidate layout is universal for an unknown machine.
- Do not run dense-grid Monte Carlo directly; if V1 is attempted later, use analytic prescreening and only Monte Carlo-test the final few layouts.

## Suggested Near-Term Edits

- Update Q4 paper-facing report wording to call the current method a "candidate-region robust layout optimization".
- Add one paragraph saying that, in an actual device, the sensitivity matrix can come from either reduced-order structural simulation or calibration tests.
- Add one limitation paragraph:
  - Without geometry and measured transfer paths, the result is a robust strategy under finite candidate regions, not a real-machine coordinate solution.
- Preserve the overnight data as the authoritative V0 validation set.

## Suggested Future V1

If more time is available after the paper-facing V0 closeout, build V1 as a separate module:

- Generate a coarse surface grid or abstract region grid.
- Compute response vectors and noise covariance analytically or from calibration data.
- Prescreen by noncentral-parameter and information-matrix metrics.
- Cluster whitened response vectors to remove redundant locations.
- Use greedy plus local swap search to choose three positions.
- Run Monte Carlo only for the top 5 to 10 candidate layouts.
- Compare V1 against V0, random three-region selection, and maximum-sensitivity selection.

## Bottom Line

The suggestion should be adopted as a theoretical framing and future upgrade path. It should not be adopted as an immediate code rewrite unless the Q4 stage is reopened for a new V1 experiment.
