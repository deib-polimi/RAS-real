# GPPPO Guardrail — Piano dettagliato di miglioramento

**Data**: 2026-05-10 | **Versione**: v3.3 (CONSENSUS post codex round 5)
**Branch target**: `guardrail`
**Obiettivo strategico**: GP-based guardrail con (a) safety contract dimostrabile, (b) evidenza empirica robusta vs PPO solo sotto concept drift, (c) novelty difendibile rispetto a Goodall-Belardinelli 2025/26, Strawn-Ayanian 2023, AAAI 2025.

---

## Changelog v3.1 → v3.2 (codex round 4 integration)

| Issue round 4 | Resolution v3.2 |
|---------------|-----------------|
| #1 §4.1 H1_primary.test "m=2 Bonferroni" conflicts §4.7 "m=6 Holm" | §4.1 yaml ora delega esplicitamente a §4.7 come single source of truth (rimossa duplicazione test specs) |
| #2 Power sim uses Wilcoxon for vs_1b but §4.7 says TOST | §4.7 pseudocode aggiornato: `sample_paired_equivalence` + `tost_pvalue` per vs_1b; criterion includes `h1_vs_1b_pass` |
| #3 §4.8 ✓/≈/✗ shorthand undefined | §4.8: legenda esplicita mappa ogni shorthand a test specifico in §4.7 (vs_1::DOM, vs_1b::SUP/NI/INF, etc) |

---

## Changelog v3 → v3.1 (codex round 3 integration)

| Issue round 3 | Resolution v3.1 |
|---------------|-----------------|
| #1 m=4 vs m=6 inconsistency between §4.1 and §4.7 | §4.1 yaml updated to m=6 with explicit test list |
| #2 Sliding windows in F0.4 are actually disjoint blocks | §F0.4 test code rewritten with TRUE sliding (stride=10) |
| #3 D1 logic conflict §4.1 vs §4.8 | §4.1 yaml ora delega a §4.8 come single source of truth |
| #4 "TOST vs 1b" undefined | §4.7 ora define explicit non-inferiority TOST per H1_vs_1b (margine ±0.03 viol, ±5% cost) |
| #5 Power simulation single-test approximation, not joint | §4.7 pseudocode riscritto: simula tutti i 6 test + Holm + joint H1 acceptance |
| #6 Phase 1.5 omits Cond 1b → fairness regression risk | §6.0: 7 conditions (Cond 1b aggiunto), 35 runs |
| #7 §7 risk row "TimeSeriesSplit too conservative" mitigation inverted | §7: mitigation reformulated logically consistent |

---

## Changelog v2 → v3 (codex round 2 integration)

| Issue round 2 | Resolution v3 |
|---------------|---------------|
| #2 Power analysis: `pingouin.power_corr` ≠ paired Wilcoxon | §4.7 ora usa **Monte Carlo simulation-based power** (10k reps, paired Wilcoxon under r_rb=0.5 effect, Holm-corrected). |
| #4 Non-degradation acceptance debole (200 tick, +0.02 tol) | §F0.4: 1000 tick, +0.005 tol, +sliding 100-tick window check on ≥80% windows. Caveat in safety contract. |
| #8 D1 non require beating Cond 1b (PPO-online) | §4.8 D1 logic riformulata: explicit branch su (vs 1) AND (vs 1b). Outcome "matches online learning" come outcome distinto. |
| #9 Novelty gate ambiguo | §0.5: regola UNICA formale via `docs/novelty-axes.yaml` lookup-table; STOP se ANY paper ha ≥4-of-6 axes match. |
| #10 stale "80 runs" reference | §4.1 pre-reg aggiornato a 130 runs totali. |
| #4.6 Pareto dominance ≠ Wilcoxon individuali | §4.7: definito **joint Pareto dominance test** con Holm m=2 dentro H1 + strict-strict requirement. |
| **NEW** H3 paired n=20 = 40 runs, non 20 | §4.5 run count corretto: H1/H2=90, H3=40, totale **130 runs**. |
| **NEW** Phase 1.5 manca Cond 1 per H1 | §6.0: aggiunto Cond 1 (PPO-solo); 6 cond × 5 seed = **30 runs**. |
| **NEW** ACI sign-inverted | §F2.7: rifrasato con formula Gibbs-Candès 2021 standard `α_{t+1} = α_t + γ(α* − 1{miss})`; prediction set tramite `q̂_{1-α_t}`. |
| **NEW** Convergence `var<5%·mean` ill-posed (mean negativa) | §4.4: thresholds **assoluti** (`var<0.005` AND `|Δmean|<0.01`); reward bounded in [-2,0]. |
| **NEW** Compute Phase 3 inconsistente | §6.1: 240×15.5min = 62h sequenziali, **~16h on 4 worker**, ~$30 AWS. |
| **NEW** SoCC Apr '26 nel passato | §8: aggiornata venue list a target realistici 2026 H2 / 2027. |
| **Residual** monotonicity weak vs §6.4 | §F0.4 + §6.4: claim ricalibrato a "non-degradation con caveat empirically-validated monotonicity". |
| **Residual** baseline tuning budget vago | §6.2: budget parity esplicita (4h human + 50 Optuna trials + 4h compute). |

---

## Changelog v1 → v2 (codex round 1 integration)

| # Codex | Obiezione | Risoluzione v2 |
|---------|-----------|----------------|
| 1 | Definizione "GPPPO-full" ambigua (GPC vs GPR) | §4.3: GPPPO-full := condizione #3 (risk_violation/GPC). #4 è ablation separata. |
| 2 | n=10 sample size senza power analysis | §4.7: power analysis esplicita; n alzato a **n=15** per H1/H2; n=20 per H3 TOST. Margine TOST allargato a ±0.05. |
| 3 | F0.6 deve precedere F0.2 (causal labels prima di distrust) | §3 riordinato: F0.6 → F0.1 → F0.4 → F0.3 → F0.2 → F0.5. |
| 4 | Non-degradation: arithmetic ≠ system-level | §F0.4: aggiunto smoke test che misura final_cores ≥ ppo_cores AND viol_rate(final) ≤ viol_rate(ppo) su 200 tick stationary. Caveat monotonicity documentato. |
| 5 | Cliff's δ è unpaired; tests sono paired | §4.7: sostituito con **rank-biserial correlation matched-pairs**; soglia \|r_rb\| ≥ 0.45. Multiplicity Holm su m=3 (H1, H2, H3). |
| 6 | F0.3 e F2.1 acceptance tautologici | §F0.3: sostituito con **scenario-based** (controller in loop, regime stationary, conta VETO%). §F2.1: testbed integrato su workload simulato OOD reale, non toy. |
| 7 | Pre-reg manca commit/config hash | §4.1: introdotto `docs/preregistration-phase1.md` con commit SHA, config SHAs, mu_calib.json hash, locked prima di prima run. |
| 8 | PPO frozen vs GP adattivo = baseline unfair | §4.4: aggiunta condizione **#1b PPO online (train=true)** con identico budget; doppio confronto. Inoltre §6.2 aggiunge "tuning-budget parity" per baselines SOTA. |
| 9 | Novelty overlap come soft mitigation, non hard gate | Nuovo §0.5 "Novelty Gate" come PHASE -1, hard-stop se overlap ≥80% sul 2-of-3 axes. |
| 10 | §11 ambiguous-p contraddice §4.1 no-peeking | §4.1 incorpora la regola: "p∈[0.05,0.10] OR effect∈[0.30,0.45] = inconclusive, trigger Phase 1.5"; pre-committed. |
| extra | F0.5 bytewise equality flaky | §F0.5: ε-equality su trajectory numeric (np.allclose rtol=1e-6). |
| extra | F2.5 K-fold su dati time-correlated = leakage | §F2.5: **TimeSeriesSplit** (sklearn) con expanding window. |
| extra | F2.7 CP marginal coverage viola exchangeability sotto drift | §F2.7: Gibbs-Candès **adaptive coverage** (long-run rate ≈ 1-α), non marginal. |
| extra | F2.2 Mahalanobis senza singular cov handling | §F2.2: Tikhonov regularization + condition-number fallback a diagonal. |
| extra | F2.6 mode-immutable contraddice "test cambia mode" | §F2.6: test diventa "raise on setter post-init"; clear-on-mode-change resta solo come safety net storico. |
| extra | §4.6 viol_rate vincibile via overprovisioning | §4.6: H1 ridefinita come **Pareto dominance** su (cost, viol_rate); arm Oracle dà upper-bound. |
| extra | F2.5 calibrazione tau_p, sigma_max non documentata | §3.5: nuovo "Hyperparameter governance" — split dev (workload pilot) vs eval (Phase 1 workload), tuning solo su dev. |

---

## 0. Executive summary

**6 bug critici** in `gpppo_controller.py` (B1-B6) invalidano i risultati attuali; **6 problemi architetturali** (A1-A6) limitano novelty; **3 paper recenti** rischiano scoop. Piano in 5 fasi, con un "Phase -1 Novelty Gate" come hard-stop e due decision-gate (D1, D2) successivi.

- **Phase -1 (1-2 giorni)**: novelty matrix vs SOTA. Hard-stop se overlap > soglia.
- **Phase 0 (5-6 giorni)**: bug fixes B1-B6 con TDD strict, **ordine di dipendenza causal-first**.
- **Phase 1 (5-6 giorni)**: ablation pre-registrata, 130 runs totali (90 drift workload H1/H2 + 40 no-drift paired H3). Decision-gate D1.
- **Phase 2 (2-3 settimane, condizionale)**: architectural upgrade A1-A6 + CP wrap. Decision-gate D2.
- **Phase 3 (2-3 settimane)**: campagna sperimentale finale + paper writing, con replay di trace produttive.

Investimento totale: **7-9 settimane** se Phase 2 va eseguita; **3-4 settimane** se D1 dice "floor only".

---

## 0.5. Phase -1 — Novelty Gate (hard-stop)

**Modalità**: 1-2 giorni di lavoro full-time, prima di toccare codice.

**Output obbligatorio**: `docs/novelty-matrix.md` + `docs/novelty-axes.yaml` (lookup-table).

Per ridurre soggettività (codex obj. #9), il novelty assessment usa una lookup-table committed pre-evaluation. `docs/novelty-axes.yaml` definisce formalmente:

```yaml
axes:
  - id: domain
    canonical_values: [robotics, autonomous_driving, navigation, cloud_autoscaling, queueing_system, generic_RL]
    equivalence_groups:  # which values count as "match" for our work
      - [cloud_autoscaling, queueing_system]
  - id: rl_algo
    canonical_values: [PPO, SAC, TD3, DQN, A2C, model_based, generic]
    equivalence_groups:
      - [PPO, SAC, TD3, DQN, A2C, generic]  # any model-free RL counts
  - id: shield_mechanism
    canonical_values: [GP_classifier_decision_tree, GP_regressor, probabilistic_shield, predictive_safety_filter, CBF, Lagrangian, none]
    equivalence_groups:
      - [GP_classifier_decision_tree]  # only exact match
  - id: uncertainty_source
    canonical_values: [predictive_entropy, BALD, latent_variance, conformal, ensemble, dropout, known_dynamics, none]
    equivalence_groups:
      - [predictive_entropy, BALD, latent_variance]
  - id: drift_handling
    canonical_values: [adaptive_retrain, online_GP, ensemble, none, static]
    equivalence_groups:
      - [adaptive_retrain, online_GP]
  - id: floor_mechanism
    canonical_values: [M_M_c, G_G_c, Erlang_C, learned_lower_bound, none]
    equivalence_groups:
      - [M_M_c, G_G_c, Erlang_C]  # any queueing-theoretic floor
threshold_strict: 4    # ≥4 axes equivalence-match → STOP
ours:
  domain: cloud_autoscaling
  rl_algo: PPO
  shield_mechanism: GP_classifier_decision_tree
  uncertainty_source: BALD  # post-Phase-2 (current: predictive_entropy)
  drift_handling: adaptive_retrain
  floor_mechanism: M_M_c
```

**Tabella esempio**:

| Lavoro | Domain | RL algo | Shield mech | Uncertainty | Drift | Floor | Match score |
|--------|--------|---------|------------|-------------|-------|-------|-------------|
| GPPPO (this) | cloud_autoscaling | PPO | GP_classifier_decision_tree | BALD | adaptive_retrain | M_M_c | (self) |
| Goodall-Belardinelli '25 | TBD | TBD | TBD | TBD | TBD | TBD | TBD/6 |
| ... | | | | | | | |

**Hard-stop rule (UNICA, codex obj. #9)**: STOP se EXISTS un lavoro con `match_score ≥ 4` (cioè 4-of-6 axes equivalence-match secondo `docs/novelty-axes.yaml`).

Se uno score = 3, è warning yellow (paper deve discutere differenze esplicite). Score ≤ 2: green.

**Tasks**:
1. Scaricare paper di Goodall-Belardinelli 2025/26 (arxiv search). Leggerlo cover-to-cover.
2. Idem per Belardinelli-Goodall-Court AAAI 2025.
3. Idem per Huang-Wei-Kou 2025/26.
4. Compilare la tabella sopra. Se cell mancante non è chiara → contatto autori.
5. Decision: GO / STOP / PIVOT.

**Acceptance**: matrix committed, decision documentata in `docs/novelty-matrix.md`.

---

## 1. Sintesi dei findings (input al piano)

[invariata da v1 — vedi sezioni 1.1, 1.2, 1.3 originali]

### 1.1 Bug critici (Phase 0)

| ID | Bug | File:line approx | Severità |
|----|-----|------------------|----------|
| B1 | `is_gp_trusted=False` mai settato in `_control_risk_violation`; distrust è dead code | `gpppo_controller.py:827-917` | CRITICAL |
| B2 | VETO threshold `(risk_p + κ·σ) > τ` con κ=2, τ=0.20 → veto always-on per σ=H(p)>0.1 | `gpppo_controller.py:716, 121-122` | CRITICAL |
| B3 | μ̂ silent fallback a 1.0; λ̂ silent fallback a 0.0 → "physics-informed floor" su numeri inventati | `gpppo_controller.py:838-839` | CRITICAL |
| B4 | COMPOSE branch con comp negativo + floor degenerato → `final < ppo_cores` (non-degradation falso) | `gpppo_controller.py:739` | CRITICAL |
| B5 | Causal mismatch: `gp_input` da prev_* (t-1) accoppiato a target da this-tick (t) | `gpppo_controller.py:847-852, 990-1014` | HIGH |
| B6 | `reset()` non azzera `_distrust_remaining`, `_veto_dwell_remaining`, `_gp_residual_z2`, ecc. | `gpppo_controller.py:1184-1208` | CRITICAL |

### 1.2 Problemi architetturali (Phase 2)

| ID | Problema |
|----|----------|
| A1 | PPO co-trained con guardrail → checkpoint contaminato |
| A2 | σ = H(p) Bernoulli entropy è OOD-blind |
| A3 | Brier in-sample come trust gate trivializzato |
| A4 | Mode-mismatch buffer poisoning |
| A5 | Drift detector solo in legacy mode |
| A6 | M/M/c assume Poisson+exp; G/G/c sarebbe più onesto |

### 1.3 Threats letteratura (vedi §0.5 per gate formale)

[invariata]

---

## 2. Decision tree strategico

```
Phase -1 (Novelty Gate) — sempre, hard-stop
        │ GO
        ▼
Phase 0 (bug fixes, causal-first order) — sempre
        │
        ▼
Phase 1 (ablation pre-registrata) — sempre
        │
   ┌────┼─────────────────────────┐
   ▼    ▼                         ▼
GP+Floor    GP wins                 Nothing wins
Pareto-     vs Floor (D1=Phase2)    (D1=Pivot D)
dominates   │
PPO         ▼
(D1=Phase2  Phase 2 (architectural upgrade)
 marginal,  │
 watch H2)  ▼
            Phase 1.5 (mini re-ablation post-Phase-2)  ◄── D2 gate
            │
            ▼
            Phase 3 (paper campaign, multi-workload + traces)
```

---

## 3. Phase 0 — Critical Bug Fixes (riordinate causal-first)

**Ordine**: F0.6 (causal pairing) → F0.1 (fail-fast μ/λ) → F0.4 (non-degradation invariant) → F0.3 (VETO rebalance) → F0.2 (distrust hook) → F0.5 (reset completeness).

**Razionale ordering** (codex obj. #3): F0.6 deve precedere F0.2 perché distrust valuta accuratezza del GP; con label causalmente sbagliate, distrust è invalido. F0.5 ultimo perché aggiunge campi che le altre task introducono.

**Modalità**: TDD strict, branch dedicato `guardrail-phase0-fixes` da `guardrail`. Skill `/tdd-cycle`.

### 3.5 — Hyperparameter governance (NUOVO)

Per i nuovi knob (`tau_p`, `sigma_max`, `gp_violation_threshold*5`, PH thresholds, `mu_estimate`):
- **Dev split**: workload `StationaryGen(lam=18)` per 600 tick, 3 seed → tuning grid manuale, scelta finale documentata in `docs/hyperparameter-tuning.md`.
- **Eval split**: workload Phase 1 (cyclic, λ=22, drift step) — **mai usato** per tuning.
- **Snapshot freeze**: hash dei valori scelti pre-Phase-1, documentato in `docs/preregistration-phase1.md`.

---

### F0.6 — Causal pairing fix (PRIMA, B5)

**Hypothesis**: il buffer GP impara una mappa non-causale `(s_{t-1}, a_{t-1}) → label(rt_t)`. Il pending-buffer pattern (già esistente per `sla_shortfall`) va esteso.

**Empirical pre-investigation** (codex obj. F0.6 latency model): prima del fix, misurare la latenza causal del sistema. Smoke run con `apply_cores_step` deterministico (es. cores 4 → 8 a t=20, 8 → 4 a t=50) e log RT al tick. Stimare lag fra cambio di cores e settle di RT (95% impulse response). Atteso: 1-3 tick (period=1s, plant time-constant ~1-2s). Se lag > 1, usare `causal_lag` knob = lag stimato.

**Failing test** (`tests/test_gpppo_buffer_causality.py::test_buffer_pairs_input_with_subsequent_observation`):
```python
def test_buffer_pairs_input_with_subsequent_observation():
    """X_t paired with label observed at t+causal_lag."""
    ctrl = GPPPOController(... causal_lag=1)
    monitoring_seq = [(rt=0.05, users=10), (rt=0.06, users=12),
                       (rt=0.07, users=15), (rt=0.20, users=20),
                       (rt=0.18, users=22)]  # rt_3 > sla
    inject_monitoring_sequence(ctrl, monitoring_seq)
    for t in range(5):
        ctrl.control(t)
    last_input, last_label = ctrl.gp_data_buffer[-1]
    expected_input = build_input_at_tick(3)  # state captured at t=3
    expected_label = int(monitoring_seq[3+1].rt > ctrl.sla)  # observed at t=4
    assert np.allclose(last_input, expected_input, rtol=1e-6)
    assert last_label == expected_label
```

**Fix**:
- Pre-investigation: misurare `causal_lag` come sopra. Default 1 tick. Documentare.
- Estendere `_gp_pending` a `risk_violation`. A tick t: push `(X_t, applied_cores_t, t)`. A tick t': leggere `RT_{t'}`; per ogni entry pendente con `t' - t == causal_lag`, committa `(X_t, label = int(RT_{t'} > sla))` e rimuovi.
- Modificare `_build_risk_input` per usare current-tick state.

**Acceptance**:
- Test verde.
- Smoke run mostra pending-buffer commits con esattamente `causal_lag` ritardo.
- Pre-investigation report con misura del settle time.

**Tempo**: 1.5 giorni (più investigation).

---

### F0.1 — Fail-fast su μ̂/λ̂ unset (B3)

**Hypothesis**: tutti i 14 config locali in `experiments/exp-local-*` sono privi di `mu_estimate`. **Verifica obbligatoria pre-fix**: grep dei 14 file e produrre tabella binary "mu_estimate set / not set". Se hypothesis falsa, riconsiderare priorità.

**Failing test**: come v1.

**Fix**: come v1.

**Acceptance** (codex obj. F0.1 non-falsifying):
- Unit test verde.
- **Behavioural verification**: smoke run paper-canonical config, log `c_baseline` ad ogni tick; post-run script asserisce `c_baseline_t == ceil(throughput_t / (mu_estimate · rho_target))` ± 1 (per ceil) per ≥3 tick contigui (correctness path, non solo presence).
- Audit dei 14 config documentato in `docs/config-audit.md`.

**Tempo**: 0.5 giorni.

---

### F0.4 — COMPOSE non-degradation invariant (B4)

**Hypothesis**: con μ̂ phantom (B3) c_baseline degenera; in COMPOSE comp<0 violazione di non-degradation.

**Caveat monotonicity** (codex obj. #4): la safety claim `final_cores ≥ ppo_cores ⇒ viol_rate ≤ viol_rate(ppo)` assume **monotonicità del plant**: più cores → meno violations a parità di λ. Per M/M/c questo è teoricamente vero (Erlang C decrescente in c). Per sistemi reali con memory thrashing / cold cache / lock contention, monotonicità può rompere localmente. **Documentazione**: caveat in `docs/safety-contract.md` con rilevazione empirica (vedi acceptance system-level).

**Contract restatement (v3, codex round 2)**: la claim del paper è ricalibrata a:
> *"Non-degradation guarantee at controller-action level (`final_cores ≥ ppo_cores` always); system-level non-degradation (viol_rate, cost) holds under monotonicity assumption empirically validated on dev split. Counter-examples (e.g., extreme contention regimes) are explicit limitations."*

**Failing test arithmetic**: come v1, parametric.

**Failing test system-level (TIGHTENED v3, codex round 2)** (`tests/test_gpppo_invariants.py::test_non_degradation_smoke`):
```python
def test_non_degradation_smoke():
    """Run 1000 ticks of stationary regime; assert system-level non-degradation
    BOTH on means AND on sliding windows (≥80% must satisfy)."""
    ctrl_ppo = PPOController(... train=False, deterministic_eval=True)
    ctrl_gp = GPPPOController(... train=False, gp_target_mode="risk_violation",
                                mu_estimate=10.0)
    ppo_trace = run_smoke(ctrl_ppo, n_ticks=1000, seed=42)
    gp_trace = run_smoke(ctrl_gp, n_ticks=1000, seed=42)
    # Mean-level (tight tolerance)
    assert np.mean(gp_trace.cores) >= np.mean(ppo_trace.cores) - 1e-6
    assert np.mean(gp_trace.viol_rate) <= np.mean(ppo_trace.viol_rate) + 0.005
    # Window-level: TRUE sliding 100-tick windows (stride=10), ≥80% must show non-degradation
    # (codex round 3 obj. #2: precedent v3 used disjoint blocks, not sliding)
    window_size, stride = 100, 10
    windows = [(s, s+window_size) for s in range(0, 1000-window_size+1, stride)]
    n_pass = 0
    for s, e in windows:
        if np.mean(gp_trace.viol_rate[s:e]) <= np.mean(ppo_trace.viol_rate[s:e]) + 0.01:
            n_pass += 1
    assert n_pass / len(windows) >= 0.80, f"only {n_pass}/{len(windows)} sliding windows pass"
```

**Fix**: come v1, lessicografica `final = max(c_baseline, ppo_cores, ppo_cores + max(0, comp))`.

**Acceptance**:
- Arithmetic property test verde (Hypothesis library).
- System-level smoke test verde con tighter tolerance (1000 ticks, +0.005 mean, 80% windows).
- Monotonicity caveat in `docs/safety-contract.md` con explicit counter-example regime documentato.

**Tempo**: 1.5 giorni (era 0.5; smoke test 1000 tick aggiunge tempo).

---

### F0.3 — VETO threshold rebalance (B2)

**Hypothesis**: VETO scatta per qualsiasi p con H(p)>0.1 sotto formula attuale.

**Failing test (NUOVO scenario-based, codex obj. #6)** (`tests/test_gpppo_veto_balance.py::test_veto_pct_in_stationary_regime`):
```python
def test_veto_pct_in_stationary_regime():
    """Run controller for 200 ticks in stationary λ=18 (benign).
    Mock GPC to return p~Beta(1,9) (10% positive class as in benign).
    Assert VETO branch fires < 30% of ticks."""
    ctrl = GPPPOController(... gp_target_mode="risk_violation",
                            mu_estimate=10.0, tau_p=0.5, sigma_max=0.85)
    mock_gpc_with_beta(ctrl, alpha=1, beta=9, seed=42)
    branch_log = []
    for t in range(200):
        ctrl.control(t)
        branch_log.append(ctrl._last_branch)
    veto_pct = branch_log.count("VETO") / len(branch_log)
    assert veto_pct < 0.30, f"VETO too frequent: {veto_pct:.2%}"

def test_veto_pct_in_stress_regime():
    """Symmetric: high-risk regime → VETO ≥ 70%."""
    ctrl = GPPPOController(...)
    mock_gpc_with_beta(ctrl, alpha=9, beta=1, seed=42)  # 90% positive
    # ... assert veto_pct >= 0.70
```

**Fix**: come v1, decoupled gates. Default `tau_p=0.5, sigma_max=0.85` da §3.5 hyperparameter governance.

**Acceptance**:
- Scenario test verde su benign + stress.
- Smoke run con risk_violation mode mostra branch distribution mai >80% concentrata.

**Tempo**: 1 giorno.

---

### F0.2 — Distrust hook per risk_violation (B1) [DOPO F0.6, F0.4, F0.3]

**Razionale ordering**: F0.2 valuta correttezza GP via Brier; serve buffer pairing corretto (F0.6) e formula VETO sensata (F0.3) prima.

**Hypothesis**: in risk_violation, GP permanentemente trusted.

**Failing test**: come v1, sintetico (mock GPC per p=0.1, y=1).

**Failing test 2 (NUOVO, codex obj. #6)** (`tests/test_gpppo_distrust_imbalance.py::test_no_false_distrust_under_class_imbalance`):
```python
def test_no_false_distrust_under_class_imbalance():
    """Class imbalance 95% y=0: GP correctly predicts p≈0.05.
    Brier ≈ 0.045 (low). Should NOT distrust."""
    ctrl = GPPPOController(... gp_target_mode="risk_violation",
                            gp_violation_threshold=0.05)
    inject_class_imbalance_scenario(ctrl, p_predicted=0.05, y_true_rate=0.05)
    for t in range(100):
        ctrl.control(t)
    assert ctrl.is_gp_trusted == True
```

**Fix**: come v1.

**Acceptance**:
- Adversarial test verde.
- Imbalance test verde (no false distrust).
- Delayed-feedback test (causal_lag=2): distrust still works.

**Tempo**: 1.5 giorni.

---

### F0.5 — `reset()` completeness (B6) [LAST]

**Razionale ordering**: aggiunge cleanup per i nuovi campi introdotti da F0.6, F0.2.

**Hypothesis**: cross-experiment state leakage.

**Failing test (codex obj. F0.5)** — softer: numeric ε-equality, not bytewise:
```python
def test_reset_restores_init_state():
    ctrl = GPPPOController(... master_seed=42)
    state_init = capture_numeric_state(ctrl)  # numpy arrays + scalars only
    for t in range(100):
        ctrl.control(t)
    ctrl.reset()
    state_after = capture_numeric_state(ctrl)
    for k in state_init:
        if isinstance(state_init[k], np.ndarray):
            assert np.allclose(state_init[k], state_after[k], rtol=1e-6, atol=1e-9), f"key {k}"
        else:
            assert state_init[k] == state_after[k], f"key {k}"

def test_reset_two_runs_produce_equivalent_traces():
    """Two runs with identical seed produce trajectories within ε on numeric outputs."""
    ctrl = GPPPOController(... master_seed=42)
    trace1 = run_smoke(ctrl, n=100)
    ctrl.reset()
    trace2 = run_smoke(ctrl, n=100)
    assert np.allclose(trace1.cores, trace2.cores, rtol=1e-6)
    assert np.allclose(trace1.rt, trace2.rt, rtol=1e-6)
```

**Fix**: come v1, helper `_full_gp_state_reset()` con esplicita lista di TUTTI gli attributi.

**Acceptance**:
- Test verde.
- Documentato in commento un comando per regenerare la lista (introspection).

**Tempo**: 1 giorno.

---

### Phase 0 — riepilogo

- **Effort totale**: ~6.5 giorni di lavoro, distribuito su 7 wall-clock.
- **Ordine**: F0.6 → F0.1 → F0.4 → F0.3 → F0.2 → F0.5.
- **Decision-gate D0**: tutti i test verdi + smoke run paper-canonical + audit config + commit hash freeze → procedere a Phase 1.

---

## 4. Phase 1 — Decisive Ablation Experiment

### 4.1 Pre-registration document — `docs/preregistration-phase1.md` (NUOVA struttura)

**Da congelare prima del primo run** (codex obj. #7, #10):

```yaml
# docs/preregistration-phase1.md (committed pre-run)
phase: 1
date_locked: 2026-MM-DD
git_commit_sha: abc123...
config_shas:
  cond_1_ppo_solo: <sha>
  cond_1b_ppo_online: <sha>
  cond_2_ppo_floor: <sha>
  cond_3_gpppo_full: <sha>
  cond_4_gpppo_gpr: <sha>
  cond_5_oracle: <sha>
  cond_6_random_floor: <sha>
  cond_7_ppo_pi: <sha>
mu_calib_sha: <sha of mu_calib.json>
ppo_checkpoint_sha: <sha of ppocontroller-clean.pt>

hypotheses:
  H1_primary:
    statement: "GPPPO-full Pareto-dominates PPO-solo (Cond 1) on (cost_total, viol_rate_post_drift)
                with non-empty dominated region (n=15 seeds), AND is non-inferior to PPO-online (Cond 1b)
                via TOST."
    test: "Defined entirely in §4.7 (joint Pareto dominance test vs Cond 1 + non-inferiority TOST vs Cond 1b).
           This YAML defers to §4.7 as single source of truth for test definitions."
    effect_size: "Defined entirely in §4.7."
  H2_secondary:
    statement: "GPPPO-full beats PPO+Floor (Cond 2) on viol_rate_post_drift."
    test: "Defined in §4.7 (paired Wilcoxon Holm-corrected). Reference: §4.7."
    interpretation: "If H2 fails: novelty is in the floor, not the GP."
  H3_sanity:
    statement: "In no-drift workload, GPPPO-full ≈ PPO-solo on viol_rate
                (TOST equivalence margin ±0.05, n=20 paired seeds, 40 runs total)."
    test: "Defined in §4.7."

multiplicity_correction: "Holm-Bonferroni on m=6 tests: {H1_viol_vs_1, H1_cost_vs_1, H1_viol_vs_1b, H1_cost_vs_1b, H2, H3}. See §4.7 for full list."

ambiguity_rule:
  condition: "If raw p ∈ [0.05, 0.10] OR |r_rb| ∈ [0.30, 0.45] for H1."
  action: "Decision := 'inconclusive'; trigger Phase 1.5 with adversarial workload
           (μ → 0.5·μ₀, severe drift). No re-analysis on Phase 1 data."

stop_rule: "One run = one observation. Re-run only on infrastructure failure
            (logged in errors.log with crash type)."

no_peeking: "Statistical analysis script frozen and run only after all 130 runs
             completed. Hash of script committed pre-launch."

decision_gate_D1: "Defined entirely in §4.8 (this YAML defers to §4.8 as single source of truth). Pre-reg locks the §4.8 table by referenced commit SHA above."
```

### 4.2 Workload setup [v1 invariato salvo durata]

- Generator: `SinGen(mod=20, shift=22, period=180)` (cyclic diurnal)
- Drift: `noise_type="step"`, `noise_start=300, noise_end=600, noise_scale_drift=0.7`
- Total: 900s, period=1, SLA=0.08s
- **Seeds H1/H2**: pre-registered list di 15 = `[42, 43, ..., 56]`
- **Seeds H3**: pre-registered list di 20 = `[57, 58, ..., 76]` (TOST richiede n maggiore). H3 paired (PPO vs GPPPO-full) → 20 seed × 2 controller = **40 runs in no-drift workload** (codex round 2 obj.)
- μ_estimate calibrato e congelato

### 4.3 Conditions (8) — definizione GPPPO-full unambigua (codex obj. #1)

| # | Nome | Descrizione | Seeds |
|---|------|-------------|-------|
| 1 | PPO-solo (frozen) | PPO `train=false`, no guardrail | 15 |
| **1b** | **PPO-solo (online)** | **PPO `train=true`, identico training budget di GPPPO. Confronto fairness baseline frozen vs adaptive.** | **15** |
| 2 | PPO+Floor | PPO frozen + M/M/c floor (no GP, no PI) | 15 |
| **3** | **GPPPO-full := risk_violation/GPC** | **risk_violation post-Phase-0; questa È GPPPO-full per D1.** | **15** |
| 4 | GPPPO-GPR | signed_shortfall post-Phase-0 (ablation separata, NON GPPPO-full) | 15 |
| 5 | Oracle | post-hoc optimal cores (offline LP) | 5 |
| 6 | PPO+RandomFloor | random K∈[min,max] (sanity) | 5 |
| 7 | PPO+aux-PI-only | PPO + CT PI controller, no GP no floor | 5 |

**Totale runs (v3, codex round 2 fix)**:
- Drift workload H1/H2: 15 × 5 (cond 1, 1b, 2, 3, 4) + 5 × 3 (cond 5, 6, 7) = 75 + 15 = **90 runs**.
- No-drift workload H3 (paired): 20 × 2 (PPO + GPPPO-full) = **40 runs**.
- **Totale: 130 runs**.

**Razionale 1b**: codex obj. #8 — PPO frozen vs GP adattivo è confound. Cond 1b dà la baseline "PPO che impara mentre il guardrail impara" per fairness. Se 1b > 1, PPO frozen è lower-bound; report H1 sia vs 1 (frozen) sia vs 1b (online).

### 4.4 PPO checkpoint pre-training — protocollo formale

**Hypothesis A**: 100k tick di pretraining su `StationaryGen(lam=22)` produce policy convergente.

**Convergence criterion (v3, codex round 2 fix on ill-posed mean-relative threshold)**:

Reward è bounded in [-2, 0] (≤0 by construction: `-|asym_pen_lat|`). Mean-relative threshold non valido con mean ≤ 0. Uso **soglie assolute**:
- Train per 50k, 100k, 150k tick → 3 checkpoint saved.
- Convergence criterion (entrambe le condizioni):
  - `var(rolling_1k_reward) < 0.005` (assoluto, su raw reward)
  - `|mean(reward[last_1k]) - mean(reward[prev_1k])| < 0.01` (mean stationarity)
  - Per 3 finestre 1k consecutive (cioè 3k tick di stable behavior).
- Se 100k non converge: usa 150k. Se 150k non converge: extend a 200k.
- **Checkpoint selection**: tra i convergent, scegli quello con minimo `viol_rate` su validation 5k-tick window held-out (`StationaryGen(lam=22)`, seeds 100-104). Hash + congelato.
- Documentato in `docs/ppo-pretraining-protocol.md`.

**Cond 1b training**: stesso pre-training, MA `train=True` durante eval con identico budget di gradient updates al GP retraining.

### 4.5 Compute budget

- Per run: 900s + ~30s setup/teardown = 15.5 min/run.
- **130 runs × 15.5 min = 33.6h sequenziali; ~8.4h su 4 worker AWS paralleli.**
- Cost AWS (c5.2xlarge × 4 worker × 8.4h): ~$17.

### 4.6 Metrics (per condition × seed)

**Joint primary** (codex obj. #4 sull'overprovisioning trick):
- `viol_rate_post_drift` AND `cost_total` come Pareto pair. H1 = Pareto dominance.

**Secondary**:
- `recovery_time_B`, `recovery_time_C` (KaplanMeier-censored a 590s e 900s rispettivamente, codex obj. censoring policy)
- `p99_rt`, `cores_std`, `branch_distribution_VETO/COMPOSE/CLAMP/NONE_pct`

**Data integrity** (codex obj.): pre-aggregation, ogni log file deve passare `verify_log_schema(file, version=2026-05-10)`; missing/corrupt files trigger re-run flag.

### 4.7 Statistical analysis (v3, codex round 2 fixes)

- **Effect size**: rank-biserial correlation matched-pairs (`r_rb`) per Wilcoxon paired. Soglia |r_rb| ≥ 0.45.

- **H1 (Pareto dominance test, joint, v3 codex round 3 fix)**:
  Definizione operativa: `GPPPO-full Pareto-dominates X` iff
  (a) `H1_viol_vs_X`: paired Wilcoxon su `viol_rate_post_drift`, Holm-corrected p<0.05 (across all m=6), |r_rb|≥0.45, AND median diff in favor of GPPPO.
  (b) `H1_cost_vs_X`: idem su `cost_total`, Holm-corrected p<0.05, |r_rb|≥0.45, AND median diff in favor of GPPPO OR ≤0 (no degradation).
  (c) `strict`: at least one of (a), (b) shows strict improvement (median diff strictly favorable, raw p<0.025).

  **Two H1 tests**: H1_vs_Cond1 (frozen) AND H1_vs_Cond1b (online).
  - H1_vs_Cond1 dominance: standard Pareto come sopra (4 tests dentro: viol/cost × Holm-pass/strict).
  - H1_vs_Cond1b: **non-inferiority TOST** invece di dominance (codex round 3 obj. #3): margine ±0.03 su viol_rate, ±5% su cost. Outcome:
    - "GPPPO non-inferior to online PPO" se TOST passes su entrambi.
    - "GPPPO inferior to online PPO" se TOST fails su almeno uno.
    - "GPPPO superior to online PPO" se Wilcoxon paired strict-favorable AND TOST passes.

- **H2**: paired Wilcoxon GPPPO-full vs PPO+Floor su `viol_rate_post_drift`. p<0.05, |r_rb|≥0.45.

- **H3**: TOST con margine ±0.05 su `viol_rate_no_drift`. n=20 paired, 40 runs totali.

- **Multiplicity globale**: Holm-Bonferroni su tutti i tests inferential = {H1_viol_vs_1, H1_cost_vs_1, H1_viol_vs_1b, H1_cost_vs_1b, H2, H3}, m=6.

- **Power analysis (v3 round 3 fix: joint-logic-aware, codex obj. #4)**: Monte Carlo che simula la **logica decisionale completa**, non un single-test approximation:
  ```python
  # Pseudocode aligned with §4.8 D1 joint logic:
  m_holm = 6
  power_count = 0
  for trial in range(10000):
      # Simulate ALL six tests under expected effect structure
      diffs_viol_vs_1 = sample_paired(n=15, target_r_rb=0.5, seed=6*trial)
      diffs_cost_vs_1 = sample_paired(n=15, target_r_rb=0.45, seed=6*trial+1)  # cost effect smaller
      # vs Cond 1b: TOST non-inferiority (margins ±0.03 viol, ±5% cost) — codex round 4 fix
      diffs_viol_vs_1b = sample_paired_equivalence(n=15, margin=0.03, seed=6*trial+2)
      diffs_cost_vs_1b = sample_paired_equivalence(n=15, margin_pct=0.05, seed=6*trial+3)
      # H2 vs Cond 2 (PPO+Floor): expected medium effect
      diffs_H2 = sample_paired(n=15, target_r_rb=0.40, seed=6*trial+4)
      # H3 TOST: expected ≈ 0 effect (equivalence)
      diffs_H3 = sample_paired_equivalence(n=20, margin=0.05, seed=6*trial+5)

      # Tests aligned to §4.7 definitions:
      ps_super = [wilcoxon(d).pvalue for d in [diffs_viol_vs_1, diffs_cost_vs_1, diffs_H2]]
      ps_tost = [tost_pvalue(diffs_viol_vs_1b, margin=0.03),
                  tost_pvalue(diffs_cost_vs_1b, margin_pct=0.05),
                  tost_pvalue(diffs_H3, margin=0.05)]
      ps = ps_super + ps_tost
      r_rbs = [rank_biserial(d) for d in [diffs_viol_vs_1, diffs_cost_vs_1, diffs_H2]]
      ps_holm = holm_correct(ps, m=m_holm)

      # Joint H1 vs Cond 1 (Pareto dominance): both endpoints + strict
      h1_vs_1_pass = (ps_holm[0]<0.05 and abs(r_rbs[0])>=0.45) and \
                      (ps_holm[1]<0.05 and abs(r_rbs[1])>=0.45) and \
                      (ps[0]<0.025 or ps[1]<0.025)  # strict on raw

      # H1 vs Cond 1b (non-inferiority TOST on both endpoints)
      h1_vs_1b_pass = (ps_holm[3]<0.05) and (ps_holm[4]<0.05)  # TOST viol AND TOST cost

      # H2: superiority vs Floor
      h2_pass = ps_holm[2]<0.05 and abs(r_rbs[2])>=0.45
      # H3: equivalence in no-drift
      h3_pass = ps_holm[5]<0.05  # TOST equivalence

      # JOINT power criterion (most stringent — aligns to D1 §4.8 "go_phase2"):
      power_count += int(h1_vs_1_pass and h1_vs_1b_pass and h2_pass and h3_pass)
  power_estimate = power_count / 10000
  # Required: power_estimate >= 0.80 for the joint outcome (most stringent).
  ```
  Documentato in `docs/power-analysis.md` con script di riproduzione + plot per varying r_rb. Se power < 0.80 → aumentare n e ri-eseguire.

- **Bootstrap CI 95%** (10k resample) on paired differences.

- **Reporting**: medie ± std, statistic, p (raw + Holm-corrected), r_rb, bootstrap CI. Niente p-hacking (script frozen pre-launch, hash committed).

### 4.8 Decision-gate D1 (v3.1 codex round 4 fix: outcome shorthand mapped to §4.7 tests)

**Outcome legend (mapped 1:1 to tests in §4.7)**:
- `vs_1::DOM` = Pareto-dominance vs Cond 1 PASSES (both Holm-corrected p<0.05 + |r_rb|≥0.45 + strict, see §4.7).
- `vs_1::FAIL` = same test FAILS.
- `vs_1::COST_FAIL` = viol_rate test passes but cost test fails (overprovisioning case).
- `vs_1b::SUP` = superior vs Cond 1b (Wilcoxon paired strict-favorable [Holm-corrected within m=6] AND TOST passes). The Wilcoxon for the SUP outcome IS multiplicity-controlled (Holm m=6, same family as the other tests in §4.7).
- `vs_1b::NI` = non-inferior vs Cond 1b (TOST passes, no strict superiority).
- `vs_1b::INF` = inferior vs Cond 1b (TOST fails on at least one endpoint).
- `H2::PASS / H2::FAIL` = §4.7 H2 test outcome.
- `H3::PASS / H3::FAIL` = §4.7 H3 TOST outcome.
- `inconclusive` = ambiguity rule fired (raw p∈[0.05,0.10] OR |r_rb|∈[0.30,0.45]).

| vs Cond 1 | vs Cond 1b | H2 | H3 | Interpretazione | Next |
|-----------|------------|-----|-----|------------------|------|
| `vs_1::DOM` | `vs_1b::SUP` | `H2::PASS` | `H3::PASS` | GP aggiunge valore anche vs PPO online | **Phase 2** (strongest) |
| `vs_1::DOM` | `vs_1b::NI` | `H2::PASS` | `H3::PASS` | GP matches online learning + no shielding tax | **Phase 2** (claim ricalibrata: "matches online learning") |
| `vs_1::DOM` | `vs_1b::INF` | — | — | Online PPO ≥ guardrail; frozen baseline unfair | **Pivot to online-PPO-first thesis** |
| `vs_1::DOM` | any | `H2::FAIL` | — | Floor è la novità (non GP) | **Pivot floor-only paper** |
| `vs_1::COST_FAIL` | any | — | — | Vince via overprovisioning | **Pivot Pareto narrative (weaker)** |
| `vs_1::FAIL` AND PPO ≈ Oracle | — | — | — | Workload troppo benigno | **Phase 1.5 adversarial** |
| `vs_1::FAIL` (other) | — | — | — | GP non beats frozen PPO | **Pivot characterization study** |
| `inconclusive` | — | — | — | Pre-reg ambiguity rule fired | **Phase 1.5** |
| `vs_1::FAIL` AND nothing ≈ Oracle | — | — | — | Nessuno abbastanza | **Stop, ripensare** |

### 4.9 Risk mitigation

- Confound period: tutti i config con `period: 1` (verificato pre-launch grep).
- Confound seed: lista esatta (15+20).
- **Confound noise**: per ridurre brittleness (codex obj.) — `noise_seed` paired con `seed` (i.e., seed[i] dà sia controller seed sia noise seed) ma 15 distinti, non 1 fissato.
- Confound checkpoint: hash MD5 logged.
- Confound locustfile: diff byte-level pre-run.

**Tempo Phase 1**: 6 giorni (1.5 setup + pre-train + Phase -1 reading; 1 run; 2.5 analysis; 1 buffer).

---

## 5. Phase 2 — Architectural Upgrade (D1=Phase-2-go) [aggiornata]

### F2.1 — σ proxy upgrade (BALD o latent variance) [A2]

[v1 invariato]

**Acceptance migliorato (codex obj. #6, F2.1 toy)**: oltre al synthetic test (X∈[0,30] vs X=200), un **integrato test in-loop**: addestra GPPPO su workload A (cyclic), eval su workload B (stress) — assert σ_proxy in workload B > 90th-percentile σ_proxy(workload A) per ≥80% dei tick OOD. (Più realistic OOD signal.)

### F2.2 — Mahalanobis OOD gate (codex obj. singular cov)

- Computa `Σ_buf` con Tikhonov: `Σ_reg = Σ + λ·I` con `λ = 1e-6 · trace(Σ)/d`.
- Se `cond(Σ_reg) > 1e8` → fallback a `Σ_diag = diag(σ²₁, ..., σ²_d)` (ARD-like).
- Cache invalidation: ricomputa Σ ad ogni retraining del GP.
- **Acceptance**: synthetic OOD test verde + collinearity-singular test (X con feature 1 = feature 2 + ε) → fallback diagonal.

### F2.3 — Online μ̂ via Little's Law

[v1 invariato + codex obj.]

**Instrumentation validation**: `busy_fraction_t` ottenuto da Docker stats `cpu_usage / cores_allocated`. Validato pre-Phase-2: workload sintetico con μ noto → assert `μ̂_online → μ_true` entro 60s, error < 10% (vedi acceptance v1). **Aggiunto sanity**: bias check su 5 workload con μ_true ≠ 1, verifica che `mean(μ̂_online) - μ_true` sia centered con CI 95% che include 0.

### F2.4 — Page-Hinkley triple drift detector

[v1 invariato]

**Acceptance migliorato**: false-fire rate <1% su **5000 tick** (era 1000) per CI più stretti.

### F2.5 — Brier on holdout (codex obj. K-fold leakage)

**Fix v2**: usa `sklearn.model_selection.TimeSeriesSplit` con n_splits=5, expanding window. Per ogni split, fit on `[0:k]`, evaluate on `[k:k+step]`. CV-Brier = mean dei 5 split.

**Acceptance**: synthetic test con random labels → cv_brier > 0.20 sempre (era 0.15, reso più stringente). In-sample Brier resta 0 — gap visibile.

### F2.6 — Buffer clear on mode change (codex obj. consistency)

**Fix v2**: `gp_target_mode` immutabile post-init.
- `__init__` cattura mode in `self._gp_target_mode_locked = mode`.
- Property getter ritorna locked value.
- Property setter raise `ImmutableModeError` con messaggio chiaro.
- **Acceptance test (riformulato)**: tentativo di setter post-init → ImmutableModeError. Se serve test multi-mode, costruire 2 controller diversi (NOT change mode of one).

### F2.7 — Conformal Prediction wrap (Gibbs-Candès adaptive, v3 sign-corrected)

**Fix v3 (codex round 2 obj. on sign-inversion)**: implementa Gibbs-Candès 2021 ACI con la formula CORRETTA del paper:

- Mantieni un **target level** `α_t` (non quantile q diretto). Inizio: `α_0 = α* (e.g. 0.10)`.
- Update: `α_{t+1} = α_t + γ · (α* - err_t)` dove `err_t = 1{y_t ∉ C_t(α_t)}` e γ ≈ 0.005.
- Prediction set: `C_t(α_t) = {y : nonconformity_score(x_t, y) ≤ q̂_{1-α_t}(score_history)}`.
- Sign correctness: on miss (`err_t=1`), `α_{t+1} > α_t` → `q̂_{1-α_t}` shift toward higher quantile → **wider prediction set** at next step → recovery toward target coverage.

**Reference implementation**: portare il codice di Gibbs & Candès 2021 §3 esattamente come pubblicato; non hand-roll.

**Acceptance**: long-run miss rate `mean(err_{1..T}) → α*` ± 2% su T=5000 tick con drift. Marginal coverage NON applicabile sotto drift (exchangeability rotta); only long-run guarantee è valid claim.

### Phase 2 — riepilogo

[invariato, 2-3 settimane]

---

## 6. Phase 3 — Paper Campaign

### 6.0 — Phase 1.5: mini re-ablation post-Phase-2 (D2 gate, v3 round 3 fix)

Prima della campagna full Phase 3, una mini-Phase-1 ridotta:
- **7 condition (v3 round 3, codex obj. #5: aggiunta Cond 1b per ri-validare fairness vs PPO online)**:
  - Cond 1 (PPO-solo, frozen)
  - **Cond 1b (PPO-solo, online)** — necessario per re-checkare fairness post-Phase-2
  - Cond 2 (PPO+Floor)
  - Cond 3-v1 (GPPPO-full pre-Phase-2)
  - Cond 3-v2 (GPPPO-full post-Phase-2)
  - Cond 4-v2 (GPPPO-GPR post-Phase-2)
  - Cond 5 (Oracle)
- × 5 seed (subset di seeds Phase 1: `[42, 43, 44, 45, 46]`) = **35 runs**.
- Su stesso workload Phase 1 (cyclic + drift step).
- **Acceptance D2**:
  - GPPPO-v2 ≥ GPPPO-v1 entro tolleranza (no regressione su `viol_rate_post_drift` con `r_rb` < 0.30 in favor di v1).
  - H1_vs_Cond1 riconfermata.
  - H1_vs_Cond1b (non-inferiority TOST) riconfermata.
  - H2 riconfermata.
- Se regressione (cond 3-v2 perde da cond 3-v1) OR H1_vs_Cond1b fails post-Phase-2 → rollback Phase 2 changes; Phase 3 usa GPPPO-v1.

### 6.1 Multi-workload sweep (final, v3 compute fix)

[v1, ma più conservativo]:
- 4 workload × 3 drift severities × 4 controllers × 5 seed = 240 run.
- **Compute (v3 fix codex round 2)**: 240 × 15.5 min = 62h sequenziali, **~16h on 4 worker AWS paralleli**, ~$30 AWS.
- **Aggiunto** (codex obj. external validity): Phase 3.5 con production trace replay (Microsoft Azure 2017 traces, Reiss 2011 Borg 2011) — 1 workload × 3 controller × 5 seed = 15 run extra. Required for systems venue.
  - Compute extra: 15 × 15.5 min = ~4h on 4 worker, ~$2.
- **Totale Phase 3 + 3.5 compute**: ~20h on 4 worker, ~$32 AWS.

### 6.2 SOTA baselines (tuning-budget parity, v3 explicit operationalization)

**Tuning budget parity policy (codex round 2 residual)**:
Ogni baseline (incluso GPPPO-full) ha **identico budget**:
- (a) **Human-hours**: 4h hyperparameter search.
- (b) **Optuna trials**: 50 trial.
- (c) **Compute hours**: 4h su Phase 0 hardware (c5.2xlarge single worker).
Tutto documentato in `docs/baseline-tuning-budgets.md` con timestamp delle sessioni di tuning.
Tuning su workload pilot `StationaryGen(lam=18)`, **MAI** su Phase-1 workload (no leakage).

- AWARE-style (Qiu '23): 1 sett impl + parity tuning.
- Lagrangian-PPO: 3 giorni + parity tuning.
- PPO + CP-PSF (Strawn 2023 simplified): 3 giorni + parity tuning.
- GPPPO-full: parity tuning (re-tune anche il nostro per fairness contro baselines).

### 6.3 Sensitivity analysis

[invariato]

### 6.4 Paper writing

[invariato salvo]:
- Tesi: *"GPPPO: a calibrated GP risk-classifier guards an RL autoscaler against concept drift, **with formal non-degradation under measured monotonicity assumptions**, demonstrably Pareto-dominant under measured workload diversity."*
- Limitations explicit: monotonicity assumption (caveat F0.4); calibrated μ̂ (workload-specific); 5-feature input schema (system-instantiable, not system-agnostic).

**Tempo Phase 3**: 3 settimane (era 2; +1 per Phase 3.5 traces).

---

## 7. Risks & Mitigations [aggiornata]

| Rischio | P | Impatto | Mitigation |
|---------|---|---------|------------|
| Phase -1 novelty gate STOP | 20% | HIGH | Chosen domain reframing (cloud-specific); negative result is also publishable |
| D1=H1 fallisce | 25% | HIGH | Phase 1.5 con workload adversarial; pivot a characterization |
| D1=H2 fallisce | 35% | MED-HIGH | Pivot floor-only paper; più piccolo ma onesto |
| D2 fallisce (Phase 2 regression) | 15% | MED | Rollback Phase 2 changes; freeze v1 for Phase 3 |
| Goodall-Belardinelli scoop | 20% | HIGH | Phase -1 hard gate; differenziare su domain + meccanismo |
| Monotonicity assumption falsa empiricamente | 20% | HIGH | F0.4 system-level test la verifica; se viola, paper limitations + extra ablation |
| Production trace replay non riproducibile | 15% | MED | Use anonymized public traces (no proprietary deps) |
| TimeSeriesSplit Brier troppo conservativo (cv_brier sempre alto, blocca re-trust) | 20% | LOW | Tarare threshold sul dev split; se cv_brier sempre >0.20 even with good model → relax soglia o switch a block-bootstrap CV |

---

## 8. Open Questions per Emilio (decisione)

1. **Deadline paper + venue (v3, post-codex round 2)**: target realistici da maggio 2026:
   - **SoCC '26** (deadline tipico Jul-Aug '26) — feasible.
   - **NSDI '27** (deadline ~Sept '26) — feasible.
   - **EuroSys '27** (deadline ~Oct '26) — feasible se Phase 3 finisce entro Sept.
   - **USENIX ATC '27** (deadline ~Jan '27) — comoda.
   - SoCC '26 e NSDI '27 sono i target più aggressivi; ATC '27 il più rilassato.
2. **Goodall-Belardinelli letto?** — bloccante per Phase -1.
3. **AWS budget cap**: $X (Phase 1=$17, Phase 1.5=$5, Phase 3+3.5=$32, baselines tuning=~$10, total ~$65 + buffer 50%).
4. **F0.4 fix**: confermo lessicografica safety (perde bidirectional but provable)?
5. **Phase 2 F2.7 CP**: in scope per v1 o future work?
6. **`tests/` directory**: pre-esistente o creazione ex novo? pytest configurato?
7. **Phase 1.5 trigger criteria** (workload adversarial): μ→0.5μ₀ (extreme), λ→2λ₀ burst, o entrambi?
8. **NEW v3**: PPO-online (Cond 1b) — accetti il setup "PPO con `train=true` durante eval, identico training budget"? Aggiunge complessità ma chiude il fairness gap.
9. **NEW v3**: monotonicity caveat in safety contract — accettabile come limitation o serve verifica forte (e.g. 5+ workload non-monotone)?

---

## 9. Acceptance criteria summary [aggiornata]

### Phase -1 done when:
- [ ] Novelty matrix in `docs/novelty-matrix.md`, decisione GO/STOP committed.
- [ ] 4 paper SOTA letti, riassunti annotati.

### Phase 0 done when:
- [ ] Tutti 6 unit test verdi (B1-B6) + scenario tests F0.3, F0.4 system-level.
- [ ] Property-based test non-degradation invariant verde.
- [ ] Smoke run paper-canonical config completes.
- [ ] Branch `guardrail-phase0-fixes` mergiato.
- [ ] Audit `docs/config-audit.md` per `mu_estimate`.
- [ ] Causal latency pre-investigation in `docs/causal-latency.md`.
- [ ] Hyperparameter governance in `docs/hyperparameter-tuning.md`.

### Phase 1 done when:
- [ ] **130 runs completati** (90 drift workload + 40 no-drift H3 paired).
- [ ] Pre-registration `docs/preregistration-phase1.md` hash matched.
- [ ] Statistical analysis report `docs/phase1-results.md`.
- [ ] `docs/power-analysis.md` documenta MC simulation-based power n=15/20.
- [ ] D1 deciso e documentato (con branch su Cond 1b fairness).

### Phase 2 done when (conditional):
- [ ] 6 task F2.1-F2.6 con TDD scaffolding.
- [ ] Synthetic OOD test green per F2.1, F2.2.
- [ ] Online μ̂ instrumentation validated.
- [ ] PH detector latency benchmark on 5000 tick.
- [ ] TimeSeriesSplit cv_brier validation.
- [ ] (Optional F2.7) Adaptive coverage validated.

### Phase 1.5 (D2 gate) done when:
- [ ] **35 runs completati** (7 cond × 5 seed; Cond 1 + Cond 1b incluse per H1 + fairness re-validation).
- [ ] GPPPO-v2 ≥ GPPPO-v1 confermato OR rollback executed.
- [ ] H1_vs_Cond1, H1_vs_Cond1b, H2 riconfermate post-Phase-2.

### Phase 3 done when:
- [ ] 240 + 15 (traces) runs completati.
- [ ] 3 baseline SOTA con tuning-parity benchmarkati.
- [ ] Paper draft v1 con figure + limitations.
- [ ] Codex/internal review draft.

---

## 10. Timeline aggregata [aggiornata]

```
Week 1:  Phase -1 (Novelty Gate) + Phase 0 start (F0.6 causal pre-investigation)
Week 2:  Phase 0 continued (F0.1, F0.4, F0.3, F0.2, F0.5)
Week 3:  Phase 0 buffer + Phase 1 setup (preregistration, ppo_pretrain)
Week 4:  Phase 1 runs + analysis + D1 decision
Week 5:  D1=Phase2 → start F2.1, F2.3, F2.5 (TimeSeriesSplit)
Week 6:  Phase 2 continued (F2.2 Mahalanobis, F2.4 PH, F2.6 immutable mode)
Week 7:  (Optional F2.7 CP) + Phase 1.5 (D2 gate)
Week 8:  Phase 3 setup + multi-workload sweep
Week 9:  Phase 3.5 (traces) + baseline implementation + tuning
Week 10: Paper draft writing
Week 11: Codex review + iteration + submission
```

**Critical path**: Phase -1 → Phase 0 → Phase 1 → D1 → Phase 2 → D2 → Phase 3.

---

## 11. Self-critique [aggiornata]

- **Monotonicity assumption** (F0.4): system-level smoke test la verifica empiricamente, ma non è un theorem completo. Honest discussion in paper limitations.
- **5-feature input schema** rimane cablata anche post-F2.3. "system-instantiable, not system-agnostic" è la formulazione difendibile.
- **Phase 1 testa workload limitato**; Phase 3 + 3.5 (traces) mitiga.
- **Phase 1.5 ambiguity rule** è pre-committed in §4.1 — risolve il conflitto codex obj. #10.
- **Power analysis** assume effect size atteso 0.5; se vero effect è <0.3, n=15 non basta. Honest in §4.7.
- **TimeSeriesSplit cv_brier 0.20** è proxy ragionevole ma non gold-standard; alternative come block bootstrap potrebbero essere migliori — future work.

---

**End of plan v2.** Round 2 codex review → integration → ... finché consenso.
