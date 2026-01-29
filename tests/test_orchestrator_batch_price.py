"""
Test case for Orchestrator Step 4: Batch fetch prices for all candidates.

This test verifies that the orchestrator correctly generates a batch price fetch
task brief when given multiple candidate transactions.
"""

from src.agents.tracetx.orchestrator import TraceOrchestratorAgent
from src.state.tracetx_state import TraceTxState
from pprint import pprint


def test_batch_price_fetch():
    """
    Test that orchestrator generates correct batch price fetch task for Step 4.

    Scenario:
    - We have 3 BTC candidate transactions at different timestamps
    - Each needs price check in window [candidate_time - 600, candidate_time + 600]
    - Orchestrator should batch all price fetches into ONE task brief

    Expected output:
    task_brief should be something like:
    "Batch fetch BTC_in_DOGE prices for the following time windows:
     [1766550184, 1766551384], [1766550900, 1766552100], [1766551500, 1766552700]"
    """

    # Simulated state after Step 3 (search completed)
    state: TraceTxState = {
        "query": "What is the source transaction for this cross-chain DOGE output to DKHQbACydj7GfN2Jxgg7nqvcZxegFZkFYe in tx E693536C1E374137BEC49F741C97A2A117FE963E098F3FEE07A298FFD3F50FCB on DOGE, given that it originates from BTC on BTC?",

        "iteration": 2,

        "params": {
            "search_time_span": 1800,
            "search_price_buffer": 0.1,
            "check_time_span": 600  # ±10 minutes for candidate price check
        },

        "derived": {
            "search_window": {
                "time": {"start_ts": 1766577965, "end_ts": 1766579765},
                "amount": {"min": 0.00005006, "max": 0.00006160}
            }
        },

        "findings": [
            {
                "kind": "get_tx",
                "id": "get_tx:e693536c1e374137bec49f741c97a2a117fe963e098f3fee07a298ffd3f50fcb",
                "source": "get_doge_tx",
                "rationale": "Destination tx on DOGE",
                "data": {
                    "chain": "DOGE",
                    "txid": "e693536c1e374137bec49f741c97a2a117fe963e098f3fee07a298ffd3f50fcb",
                    "block_time": 1766579765,
                    "fee": 2.2875,
                    "vin": [{"addr": "DFHQhU7tuQ5CovzYVZdmCYDDjjJ6qsCM7C", "amount": 2847240.81255862}],
                    "vout": [
                        {"n": 0, "addr": "DKHQbACydj7GfN2Jxgg7nqvcZxegFZkFYe", "amount": 38.09399457},
                        {"n": 1, "addr": "DFHQhU7tuQ5CovzYVZdmCYDDjjJ6qsCM7C", "amount": 2847200.43106405}
                    ]
                }
            },
            {
                "kind": "price",
                "id": "price:DOGE_in_BTC@time(1766577965-1766579765)",
                "source": "get_binance_price",
                "rationale": "Price range for search window",
                "data": {"price_min": 0.0000013140, "price_max": 0.0000016170}
            },
        ],

        # Latest task and inbox (from Step 3 search)
        "task_brief": "Search BTC outputs from 1766577965 to 1766579765 with amount 0.00005006 to 0.00006160, direction=out",

        # Step 3 search results are in inbox (not yet merged) - 70 real candidates
        "inbox_findings": [
            {
                "kind": "search_txs",
                "id": "BTC@1766577965-1766579765",
                "source": "search_utxo_outputs_blockchair",
                "rationale": "Candidate BTC transactions in search window",
                "data": [
                    {"chain": "BTC", "txid": "fed2bd8d86e1978d3fc9172320880e6b7b7f6776a721bcae66558f705f3d2872", "n": 0, "amount": 5.9e-05, "addr": "bc1q990yet582vs8xgl03gm4vy5asw03e73eexcqv0", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "1e28399b7b10a2c67fd41a7d08e7140e78f1a119983137f6705ad6a6b1cd03ed", "n": 0, "amount": 6e-05, "addr": "bc1qt2s2l85c859vj7fr4eglzwtr7l9xxvfann07kn", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "64b91630b822a56d61ec2fd6327a7b34f8bef7e289822eb5b1c57cc5edccaa29", "n": 0, "amount": 5.346e-05, "addr": "bc1qgxmv67fzgtxgp96ue5q295zevgp6mduf0m582ccycqlg4n64e72scg429d", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "4375cb0fbc2f958b92f52747bee2a3100dc3babc3b0b68db1d25588bb14f4da8", "n": 1, "amount": 5.213e-05, "addr": "bc1qkfpemx7397pm5pmewpf05d2ptnma8my00vjzmm", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "b0a7c7eb05faba2c346c08da46aad309fd1807a6ba1093b10878ae85b79eedf6", "n": 0, "amount": 5.748e-05, "addr": "32sE4ifoBMo49kdsn7LZvnCKNqZPdorzox", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "1226a7d11f50692bf6cb7b36a02735c011cc6fa0d096bb661e64d99b99593d9d", "n": 1, "amount": 5.731e-05, "addr": "1D88zgTXWz8CZBs7fzY2pNNygTjiooQBcT", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "58c1d1817fda7f2f47afbea7c29ad94b9ebe7ae2e87bab3e524e171d4737e75a", "n": 1, "amount": 5.46e-05, "addr": "bc1qxl9fpzfgwlvacem03e8yvpy3966qvhgd8usay8", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "766668856c9c8a257ecd97119105e9c2cac52edbc6b8023e6bce2137f318adf4", "n": 1, "amount": 5.46e-05, "addr": "bc1qwd3dg6hetenspv45a8c3jt89vt4vu4zh9j60ty", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "ac019e519c8f73830c0fb6c95be02daa4e9b531100dd11238b1056448ca91c56", "n": 0, "amount": 5.74e-05, "addr": "bc1qch2ugual8nq36nxw6z997k5pnfn0jh0z9txxqz", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "7e4325cd5641d972249bac0019ae7d14b1895f0c39914ccad1f91ed3fec164e5", "n": 1, "amount": 5.639e-05, "addr": "bc1qe22xnvztp8p4nxwdz2rs74ayjtqc2x0w88xguv", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "712d1a80b5fe4c840938a7d360cf34abf639da1f74c6113ab87d8c55fb5c75b0", "n": 1, "amount": 5.022e-05, "addr": "bc1q74wlpnvufcmwdj2l98mj86wdp9fce4dmuk2q0e", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "8b3f65b07640500accef83a47d9c38fd258876fbb99760de60422db5109a3d93", "n": 1, "amount": 5.976e-05, "addr": "bc1q3qyh55dkxf7al99nzmqjpx4cyza5293ylc2etv", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "7d928fee8d3c1235946ffaf8562915091fcd61b79caae992f7807911bf3a4d80", "n": 1, "amount": 5.432e-05, "addr": "bc1q3asva77spzgv4ufn04dn27y9lavrt3f3d8ucjz", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "434540559510ef26853801fe049ec2ad83cdc1cd99326dde7e8056bd1e3bce77", "n": 1, "amount": 5.967e-05, "addr": "bc1q9p42knl4e5zzx3ck06emkgzx4sz684nl5t56vh", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "7d41da196d0bab7c48d9b17a39df60e10f1e252b5e9e6afe7529c82afb8c3273", "n": 1, "amount": 5.951e-05, "addr": "bc1q8ltluv8e9ughrka58qznt07ssdvtkknr8vcnv5", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "97667c7606ddc57f84f34d6e64b71b8859dfc09fc92bc1efe0c88a492251eb68", "n": 1, "amount": 5.7e-05, "addr": "bc1qe8rv6ejfmclu62wwsm7hfletdj67m03vhpt4sa", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "c297f5fd3459cf34535b094ea8930d2d3279143603ef58fb54b26fb69ddd0a47", "n": 1, "amount": 5.047e-05, "addr": "bc1qe32pnkj477e9yphy65rafazs56ya5w6wsez5hr", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "d1f109f1f2197e7e7dbe5e96a01a8e8d04e2f333ea14c9d8a3b9ea08fefa2920", "n": 0, "amount": 5.732e-05, "addr": "bc1qd90eld8trlq6a30hy6jlxqvqjntgerw80warzk", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "d996d1bbe025f750c1ef64016076e317c952a3fd5f6e3af41199c767e4f76117", "n": 38, "amount": 5.957e-05, "addr": "bc1q4wt3zg7kf0m4ku3x3qu48uuc9hu0umagf485tg", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "f1d16d98758f6aa2e58800777890516de49f3e41158e8956f5997c8d4fefbd07", "n": 0, "amount": 5.737e-05, "addr": "bc1q63p9rrsdwxl74vf8pu4wl8jw4dghpqetrut39h", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "c5b8c6969378fc32ac6e1b642c2782fae46c41d5199f769f4ae709223ca48705", "n": 1, "amount": 5.313e-05, "addr": "bc1qhef0da8wl62neje7v05m0mus2xjr0vj4h0mpky", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "add11ad2f58f25bf242c6317b81e9bb6a8f50a44ac3af4b6711ab51f925f7704", "n": 0, "amount": 5.755e-05, "addr": "bc1q4289tjgfhqu8ezmvs2dyjgnvhy7wjy5qwap2jx", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "138851726acf2ed69be7c29861811dc9ca252278676ee31b5ee960da2b952713", "n": 0, "amount": 5.929e-05, "addr": "bc1qs0dtun0w2ramvrq307whuvqhc00f9yd3pxdupw", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "19fa7bc3a47ab3b1b079f458a18f99a089a800b4e918cab60765f83ded8f4401", "n": 0, "amount": 5.753e-05, "addr": "3Bm5hRHgjXW3yyVo7dYEkVBP3YY1uS6hW6", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "82d03a4fc00f086d0b2ff69d2df7d934ecd8c0b0e460391dfd2405f6a341d8ba", "n": 0, "amount": 5.736e-05, "addr": "159RebJhuUbimk4eUcPz7sniZu752psepi", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "dbbc52f74d6e9e0f8dcc9595e8fe5defb30a0407b8fbf78fd3cab1b96eb0d2c4", "n": 1, "amount": 5.73e-05, "addr": "1JiHjPVqdmyEkxX3GELsCKPthYTyau4MLM", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "417a0536b83ad8f8da4add8c10e532c072ef49aa5233f5749c2ab4e482fef377", "n": 56, "amount": 5.731e-05, "addr": "bc1q3pzek5pmj05lz45xj48a7p5akyqkzj28zhlgkc", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "61f7e11a6f6bee555f46cdcde6f44a06c568b6cbd49f9005e530da48296993af", "n": 55, "amount": 6.106e-05, "addr": "1QKuZGjpm3gDAtzULUo14yjSbnfHnxBNNW", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "61f7e11a6f6bee555f46cdcde6f44a06c568b6cbd49f9005e530da48296993af", "n": 0, "amount": 5.801e-05, "addr": "bc1qx46euxpjudvgnaedkmfwp3kexhmhrpznn6puxr", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "937af1a8e4e2a74f5bdaf1743900ab2ac63c61f01cdf79a9f6b31f3a69d8b5ef", "n": 52, "amount": 5.739e-05, "addr": "17ESKnEKhumJvTRAmA4pyjrUUAiXPU6UE1", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "2813606d2787cebc41810ba85d0c1244fc75d3eb164139f6d52a3c423ecf84b9", "n": 0, "amount": 5.951e-05, "addr": "bc1pgt9j8n375zsekzxheq9nph9cmzwchpnfuunm9nkkn8myjwxtv30s2y7ytx", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "7a69481ff477290e5628825a7bb61a35117d90183cfe270294dbc359db2f80fe", "n": 1, "amount": 5.277e-05, "addr": "bc1q5u509eqtuem4jxd6lmvk98fcv0nqxtat9capj7", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "6c30042b96158293a2ff82c3aba9542b0ac95e903c40acac1c608ed278a51a1f", "n": 1, "amount": 5.014e-05, "addr": "1KdrAgDuYuih5EwNk6ReEaZ5WMELhjRWrY", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "7be270df43db51f62e6b08612397a4cec063ab7e552293a14c1e952a831e8100", "n": 1, "amount": 5.038e-05, "addr": "bc1qjneyeq28f759s4hq4yj74zdlw44fdd6sx88nul", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "6bac6d5ee6d29e34675b442a05c0e58923acc6245190dc3a25f294a07241b364", "n": 1, "amount": 5.927e-05, "addr": "bc1qy4vmrz4760gqrym7gzy38hcnm3w3fnlvy3gkxr", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "3b6e0b0fd25da8ef0b42c0b58351ac32ea0d1c7d0085d88af4ae9c55c7fe3154", "n": 1, "amount": 5.731e-05, "addr": "1AhCeCBKBeSxp2QkLLwZFpBUSaXAHaqLEW", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "7ec05e57816865ce997408986b887ce47d5e10b0705e7781e4413a2eff7054f8", "n": 1, "amount": 6.006e-05, "addr": "bc1qcwt6kyvtfukrvawv859ghmyd4xfqf4ra3wd6rz", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "8581c181b746d44fc47985c1552f1072846f726e09b7c732f8b75ea544e673ca", "n": 0, "amount": 6.088e-05, "addr": "bc1q8at5yxqv39nnmzxtcytgs3u08m7f7kqn7z46l6", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "e7d448b3f8c82bfdca6fd3ed571f827ef65d63654b3acf5f1c14960616f0e96d", "n": 0, "amount": 5.346e-05, "addr": "bc1q3r38et5vxl3m6agv3nyv2g0cm0q43xrpma2v7zgekg6tqklxk4yst7s4zu", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "3590d113b23d5ba4cc845e07495d050ab463b3180fc2969a3b9d516e9d448398", "n": 1, "amount": 5.996e-05, "addr": "bc1ql6mpy5fsx79kzz7gl6c4pvyzwljxplxargetwy", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "8b673718781cc80456b8afa5fe30f649f372d27500ed71daae171f0ad9ee206a", "n": 0, "amount": 5.692e-05, "addr": "bc1qdqqsq6y7csd0cr3ye45h9lv8ydh777j2wehgl6", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "c6a27983826be0a3284fed3267a9b8853c87378fa9c903aedd841741d90f85f4", "n": 0, "amount": 5.163e-05, "addr": "bc1p67gn0lkcpv88jxpfmqsxk06hh2qwpry4lxqlteutcrtqz0ds8haszrjjr4", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "5a638f9a49c3528e1a39e89a74385c1be346311a30c8b1acd6f48f978953d72b", "n": 0, "amount": 5.737e-05, "addr": "bc1q69hw6zqwftyt79u4erskuefrxevsztu2y9edw6", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "8e4886764b97c9265ede46076bae0f548c8b2f47e2bba3fd8d8e737413508c25", "n": 0, "amount": 5.8e-05, "addr": "bc1qupngqpt94yyj66cmzcy98a2hh9w9tqrr5ecp24", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "03161cede92688f870b4c860c0a028d49926c28639e350963ba79dbc370a2304", "n": 1, "amount": 5.252e-05, "addr": "bc1qavxh442h96ultxkpwsxh28xp9fujnnvnar63xl", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "5eaa7a49434b4315d81b5e302fd379f9ae5b99bd6ab214e51103e56625f1473b", "n": 1, "amount": 5.283e-05, "addr": "bc1qslx3s0mls3vnurdu6u8l4tjf6zksr7xrvljxh3", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "5442300a2afbe6390af820e98c4cf2fc7c946b4a6cd488f15822e556e27dee35", "n": 1, "amount": 5.714e-05, "addr": "bc1qezx4p8y9yjvvc4482hfwjpn6uzmmkuq3sx4qfk", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "d15e8cc3d3f844817456e3a4979a8609141ae280f42a03283026df7eddb6d1c4", "n": 1, "amount": 5.469e-05, "addr": "bc1qgqq8v220nswqpvvky3tr4z8pkhtac05fwpzw6k", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "d376aafae79cf8eceddbdc04f3fed3a8b408eb904b03cf2bc9dbd6352093b949", "n": 1, "amount": 6e-05, "addr": "194fSg8qkafeguSGWwCRSxJKj63y6L83En", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "986b7ca48c112808776529b492d4cef8ce901d4010dd0eda0be7026079af974c", "n": 0, "amount": 6.088e-05, "addr": "bc1qmvrszt3tvnpn3g20fkycuj3r6j38s600aryc9p", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "726d358a1842f5aa84a5de3696da2256289b8363d1ec417f80056068fcbba013", "n": 0, "amount": 6.088e-05, "addr": "bc1qmldy0tfk464ma0sfv2drdtsyhlrz5ww4jtpe57", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "218251a954c54999e806e88b130dd73a0ddc169b91ce74fd8713fa9fd19a9ffc", "n": 1, "amount": 5.728e-05, "addr": "bc1q37z6ucrduxphunwrajem68hfsguqtw7clzmv5j", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "4a51620cbe9b23cc7fe263b71c74ff74b254c4d96a35e8be2b9fa035634fc027", "n": 1, "amount": 5.282e-05, "addr": "bc1qnwsuh0a2mqc998vdl042py98ag9wh5f78ea6wc", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "67f9bb775810aca5ca0ca4309ac83e6342f1da14fd0c2b98cb49e22ff6c23426", "n": 0, "amount": 5.062e-05, "addr": "bc1qltq2fyjypyygqh926rfl8ceymqajryreg5l56z", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "a2db00fb9ee820f8ec019839cb129ba88620ff7dc0d7c6cd132f80f7fc6f693a", "n": 0, "amount": 6.088e-05, "addr": "bc1q6tj2w5mv4ttn5fwewqgzn2smu5keh6f9lfh5xt", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "a398e9f78a8fa5037a9c1bf2526b073cea6fc3e1999fd0cbd52edd1587258325", "n": 0, "amount": 6.088e-05, "addr": "bc1qkgvatss5tsh2hpmupk0efrhctx8dagh7qt72ew", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "96ac7b80f30ae711d749243783727f688c5169d168d6aae23effb324beaef51b", "n": 0, "amount": 5.93e-05, "addr": "bc1qqjp3qaj0jp2f2umfchcndnkpfcfvkffs37d3a7", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "c7b442de965939648ea4f864b4efbf3dab7bda624db8f8aa0d2f105f316506ec", "n": 0, "amount": 5.826e-05, "addr": "bc1qdx25gyytfuckw668na8tj7fgukpxl483a2s8d3", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "4d7431a4d77babf722adc175f3cca2758cd428db2f197071abaacf83288d36e9", "n": 0, "amount": 5.116e-05, "addr": "bc1qkszaa6f7a27vrhkhamqcgpdr532mz2k3c9klez", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "9235350bbde63d59fd90b678fa83118e621a9b6e1774141d70e97b4e2c46884d", "n": 0, "amount": 5.886e-05, "addr": "bc1qdndt2l84760f7jlswexk09zjwef5tnwqj6f5cn", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "f7ff8566c4fd1308e40d42670ad70cb4c5b8365ef909864cc198b82b1fded9f4", "n": 0, "amount": 5.5e-05, "addr": "bc1qmz4wl8fdudya3up37w4849telj4r57rfp7kl8z", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "c970f241071b1cf58c3dfe648789b2bcec92174ccbf2b85b792b71deed85abc6", "n": 1, "amount": 6.033e-05, "addr": "3HkNBghJuttgS7YuoBTXi3rZhZMGy1qNkn", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "caa083d36d030af355b135fe020c2118f49a286f76b0de563df92ac944d7049e", "n": 1, "amount": 5.398e-05, "addr": "bc1qhvx7nyc5750rzk5wht6l8xfrh5k0mt7wqgn7fr", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "1d846e327e4e38dc9748b71cbacbd8837a87943ca050a30371fb1958d10205d2", "n": 1, "amount": 6.077e-05, "addr": "bc1q34f6gzeda6l2gdvarzvef9dtdt8xqskyanjv84", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "6900cc21a27720a5632ca90932659dac6195edc0fa00c613a237312fa23b5ad6", "n": 0, "amount": 5.826e-05, "addr": "bc1p8046kjeke6zlpyn3ewzdnmwsmh7ykzj292738fpzvum43twf2raqgax5sn", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "56b600a829ca00520e4411fd05da7f5b3ef47dad0f96554b8b86f616e0b031d3", "n": 0, "amount": 5.826e-05, "addr": "bc1pjgsam6wldm6s4p6w27h24fkua782h2fxrredhsgjhfjmlukanadsu2r2c6", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "5c48613651d9219261d4f97dac02ff577fe562fd510ffea41e04544db68b6ab0", "n": 0, "amount": 5.826e-05, "addr": "bc1p58cq68fffejj93hqqwurpcr3vrasnm4rj9edsmc5zeg0e5l6v4eswmanp8", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "e0789b1cab5a738868f6a88b7b6cd9353a535ed41dd26fd2024a491e69134daf", "n": 0, "amount": 5.826e-05, "addr": "bc1pmkuuzmgj0g9lhkqy9znvqylramnmcc06tfzjav7qv52tx7pcz5wsv08x09", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "16f5a6bf9d23e9b030caeea56fbe0d35959e8925790090bf927fa8a8d5ebb5a9", "n": 0, "amount": 5.826e-05, "addr": "bc1pjgsam6wldm6s4p6w27h24fkua782h2fxrredhsgjhfjmlukanadsu2r2c6", "block_time": 1766550784},
                    {"chain": "BTC", "txid": "ddcf00334c0852c89fd1a13dfc461e620e37a60bbc300e6f0d3077425f423fa6", "n": 0, "amount": 5.826e-05, "addr": "bc1pjgsam6wldm6s4p6w27h24fkua782h2fxrredhsgjhfjmlukanadsu2r2c6", "block_time": 1766550784}
                ]
            }
        ],
        "inbox_gaps": [],
    }

    print("=" * 80)
    print("TEST: Orchestrator Step 4 - Batch Price Fetch (70 candidates)")
    print("=" * 80)
    print("\nScenario:")
    print("- Have 70 BTC candidate transactions (all at timestamp 1766550784)")
    print("- check_time_span = 600 seconds (±10 minutes)")
    print("\nExpected output:")
    print("  - action='fetch'")
    print("  - task_brief contains 'batch' and 'BTC_in_DOGE'")
    print("  - Should deduplicate same timestamps → only 1 unique time window")
    print("  - Time window should be: [1766550184, 1766551384] (1766550784 ± 600)")
    print("  - candidates=None (not populated in Step 4)")
    print("\n" + "=" * 80)

    # Run orchestrator
    agent = TraceOrchestratorAgent()
    result = agent.process(state)

    print("\n" + "=" * 80)
    print("RAW LLM OUTPUT:")
    print("=" * 80)
    from pprint import pprint
    pprint(result.model_dump())

    print("\n" + "=" * 80)
    print("RESULT:")
    print("=" * 80)
    print(f"\nAction: {result.action}")
    print(f"\nTask Brief:\n  {result.task_brief}")

    if result.candidates:
        print(f"\nCandidates ({len(result.candidates)}):")
        for i, c in enumerate(result.candidates, 1):
            print(f"  {i}. txid={c.txid[:16]}...")
            print(f"     op_id={c.op_id}, amount={c.amount:.8f}, time={c.block_time}")
            print(f"     price=[{c.price_min:.10f}, {c.price_max:.10f}]")

    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)

    # Validation
    issues = []

    # Check 1: Should be fetch action (not score yet)
    if result.action != "fetch":
        issues.append(f"❌ Expected action='fetch' (Step 4), got '{result.action}'")
    else:
        print("✅ Correct action: 'fetch' (Step 4 - batch price fetch)")

    # Check 2: Task brief should not be None
    if not result.task_brief:
        issues.append("❌ Task brief is None or empty!")
    else:
        # Check 3: Task brief should contain "Batch" or "batch"
        if "batch" not in result.task_brief.lower():
            issues.append("❌ Task brief doesn't contain 'batch' - not batching price requests!")
        else:
            print("✅ Task brief contains 'batch' keyword")

        # Check 4: Should contain "BTC_in_DOGE" (SOURCE_in_DESTINATION for scoring)
        if "BTC_in_DOGE" not in result.task_brief:
            issues.append("❌ Task brief should contain 'BTC_in_DOGE' (SOURCE_in_DESTINATION for scoring)")
        else:
            print("✅ Correct price direction: BTC_in_DOGE (SOURCE_in_DESTINATION)")

        # Check 5: Should have 3 time windows (one per candidate)
        # Count comma-separated pairs or bracket pairs
        time_window_count = result.task_brief.count('[')
        if time_window_count != 3:
            issues.append(f"❌ Expected 3 time windows, found {time_window_count}")
        else:
            print(f"✅ Correct number of time windows: {time_window_count}")

    # Check 6: Candidates should NOT have prices yet (those will be filled after Step 4)
    if result.candidates:
        has_prices = any(c.price_min is not None for c in result.candidates)
        if has_prices:
            issues.append("❌ Candidates should NOT have prices yet (Step 4 hasn't executed)")
        else:
            print("✅ Candidates don't have prices yet (correct for Step 4 input)")

    print("\n" + "=" * 80)
    if issues:
        print("ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
        print("\n💡 Hint: The orchestrator should:")
        print("   1. Extract all candidate timestamps from search_txs finding")
        print("   2. Calculate [candidate_time - 600, candidate_time + 600] for each")
        print("   3. Batch all into ONE task brief like prompt example:")
        print("      'Batch fetch COIN1/COIN2 prices for each of the following time windows:")
        print("       [start_ts_1, end_ts_1], [start_ts_2, end_ts_2], ...'")
    else:
        print("✅ ALL CHECKS PASSED!")

    print("=" * 80)

    return result

