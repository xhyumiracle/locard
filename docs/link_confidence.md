# CrossChainLink Confidence Scoring

CrossChainLink.confidence (0..1) for v0 can be implemented using "heuristic weighted scoring + normalization": enumerate candidate pairs (src_op, dst_op), compute feature scores for each candidate, then aggregate into a total score and compress to 0..1.

------------------------------------------------------------
## 0) Prerequisite: Candidate Generation
------------------------------------------------------------
Given src_op (a "send/receive" operation on Chain A), generate candidate dst_op on Chain B:
- Time window: tB ∈ [tA - W_before, tA + W_after] (bridges typically shorter; exchanges can be longer)
- Amount window: Convert amountA to B's denomination at the current exchange rate, then filter with tolerance (±ε or ±max(ε_abs, ε_rel))
- Structure window: If "bridge/exchange address sets" are identified, prioritize candidates from related transactions

------------------------------------------------------------
## 1) Feature Design (each feature outputs 0..1)
------------------------------------------------------------

### F_time: Time Proximity
- dt = |tB - tA|
- F_time = exp(-dt / tau_time)
  - tau_time can be set by Link scenario: small for bridges (e.g., 30~120min), large for exchanges (e.g., 6~48h)

### F_amount: Value Consistency (using price/exchange rate at the time)
- vA = amountA * priceA(tA)   (denominated in USD or stablecoin)
- vB = amountB * priceB(tB)
- rel = |vA - vB| / max(vA, vB)
- F_amount = exp(-rel / tau_amount)
  - tau_amount typically 1%~10% (depends on coin volatility & bridge fees/slippage)

### F_fee_slippage: Fee/Slippage Reasonability (optional but useful)
- expected_loss = fee_bridge + relayer_fee + slippage_band (range)
- loss = (vA - vB) / vA   (if vB <= vA; otherwise set to 0 or handle separately)
- F_fee = 1 if loss ∈ [L_min, L_max] else exp(-dist_to_interval / tau_fee)

### F_rounding: Numeric "Human/System" Patterns (optional)
- Many bridges/exchanges produce "integer/fixed decimal/specific trailing digits after batch splits"
- Rule-based: if amountB's decimal places/trailing digits match high-frequency patterns, add score
- F_rounding ∈ {0, 0.5, 1}

### F_tag: Endpoint Tag Match (bridge/exchange address clusters, known contracts, known hot wallets)
- If src or dst matches "known bridge/exchange entity set" => F_tag=1
- If weak match (e.g., same cluster but uncertain) => F_tag=0.5
- Otherwise 0

### F_meta: Cross-chain Metadata Evidence (strong feature, usually high weight)
- EVM chains: event logs (Bridge contract events, recipient, nonce, chainId)
- UTXO chains: OP_RETURN / memo / specific script patterns
- If directly aligned to same nonce/orderId => F_meta=1 (almost "deterministic link")
- If only weak hints => 0.5
- Otherwise 0

### F_uniqueness: Uniqueness/Ambiguity Penalty (critical)
- In the candidate set, if the "second place" is also very close, confidence decreases
- Let best=score_raw_max, second=score_raw_2nd
- margin = (best - second) / max(best, 1e-9)
- F_unique = clamp(margin / m0, 0, 1)   (m0 e.g., 0.2)
  - Intuition: the more "unique match", the more trustworthy

### F_flow_consistency: Chain Context Consistency (optional, for provenance chains)
- If previous/next hop's scale, rhythm, address cluster type matches current candidate => add score
- E.g., same bridge producing blocks in short time, fixed pattern batch processing

------------------------------------------------------------
## 2) Aggregation: Weighted Sum + Compress to 0..1
------------------------------------------------------------

```
score_raw = w_time*F_time
          + w_amount*F_amount
          + w_fee*F_fee
          + w_round*F_rounding
          + w_tag*F_tag
          + w_meta*F_meta
          + w_unique*F_unique
          + w_flow*F_flow

confidence = sigmoid(a*(score_raw - b))
```
- Empirical values: a=3~8, b = "acceptable threshold" raw score
- v0 simplification: can also directly use `confidence = clamp(score_raw / sum(w), 0, 1)`

### Suggested v0 Weights (to get it running):
- w_meta = 4.0   (with nonce/orderId strong evidence, almost locked)
- w_amount = 2.0
- w_time  = 1.5
- w_unique= 2.0
- w_tag   = 1.0
- w_fee   = 1.0
- w_round = 0.5
- w_flow  = 0.5

------------------------------------------------------------
## 3) Output Strategy (how to use confidence)
------------------------------------------------------------
- For each src_op: keep topK candidates (e.g., K=5), with confidence scores
- If max_conf < theta_low (e.g., 0.35): no edge (indicates "dead end/broken chain/unknown")
- If max_conf >= theta_high (e.g., 0.75) and F_unique is high: auto-select as main chain path
- Otherwise: keep multiple candidates, defer to subsequent context (or user/human) for disambiguation

------------------------------------------------------------
## 4) v0 Most Important Points (Occam's Razor version)
------------------------------------------------------------
Just 4 features can be very effective:
- F_meta (strong if present)
- F_amount (amount consistency at exchange rate)
- F_time (time proximity within window)
- F_uniqueness (ambiguity penalty)

All others are optional, add later.
