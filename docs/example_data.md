# Example Data
## Cross-chain Data
### DOGE -> BTC
Data source: https://midgard.thorchain.liquify.com/v2/actions?type=swap&asset=BTC.BTC,DOGE.DOGE

```
DOGE in:
- tx: 71B1ED1276B53803272A0E2F0860961F4BE0B49CCF72415210BB2EEAAFF6C3D0
- from: DPLmmixRJVrbwiwKQ6aqfzt39hLvh9RYnM
- amount: 1095
BTC out:
- tx: 749534249453B75EE5F193B8B71629C642B8AD3CF772212D518468615231AE1B
- to: bc1qzjuhrwr50sd7njkf40qa469n38sl25mg9lxdvp
- amount: 89749
```

## Example Request:
"please help me to trace the source of this BTC: in tx 749534249453B75EE5F193B8B71629C642B8AD3CF772212D518468615231AE1B, there's a vout to bc1qzjuhrwr50sd7njkf40qa469n38sl25mg9lxdvp, hint: it may come from doge coin"

## Expected Output:
- Identify the original cross-chain transaction (71B1ED1276B53803272A0E2F0860961F4BE0B49CCF72415210BB2EEAAFF6C3D0) and provide more details and evidence for cross-verification.
