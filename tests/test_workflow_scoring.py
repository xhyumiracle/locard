"""
Test Score Node (Step 5) - Converting candidates to CrossChainLinks and scoring
"""
from src.state.tracetx_state import TraceTxState
from src.models.core import DstInfo, SrcInfo
from src.node.tracetx.score import score_node
from src.node.tracetx.validate import validate_node


def test_score_step5():
    """
    Test that score node correctly processes candidates with price data.

    Scenario:
    - Have 3 BTC candidate transactions (simplified from 70)
    - Each candidate has price_min/price_max from Step 4
    - Dst tx: DOGE with amount=38.09399457, time=1766579765
    - Should generate CrossChainLinks with confidence scores
    """

    # State after Step 4 (orchestrator outputs candidates for scoring)
    state: TraceTxState = {
        "query": "What is the source transaction for this cross-chain DOGE output...",
        "iteration": 3,
        "params": {
            "search_time_span": 1800,
            "search_price_buffer": 0.1,
            "check_time_span": 600,
            "tau_time": 3600,
            "max_fee_rate": 0.15,
            "max_deviation_rate": 0.2,
            "w_time": 0.4,
            "w_amount": 0.6
        },

        # Source and dst info (as dicts, matching real state after model_dump())
        "src_info": {"chain": "BTC", "asset": "BTC"},
        "dst_info": {
            "txid": "e693536c1e374137bec49f741c97a2a117fe963e098f3fee07a298ffd3f50fcb",
            "chain": "DOGE",
            "asset": "DOGE",
            "op_id": "vout:0",
            "amount": 38.09399457,
            "time": 1766579765
        },


        # Accumulated findings (not used in score node, but part of state)
        "findings": [],
        "inbox_findings": [],
        "inbox_gaps": [],
        "derived": {
            "search_window": {
                "time": {"start_ts": 1766577965, "end_ts": 1766579765},
                "amount": {"min": 0.00005006, "max": 0.00006160}
            }
        }
    }

    # Use real 70 candidates from test_orch_batch_price.py
    # All candidates have same timestamp (1766579584), so they'll share price data
    real_search_results = [
                    {"chain": "BTC", "txid": "fed2bd8d86e1978d3fc9172320880e6b7b7f6776a721bcae66558f705f3d2872", "n": 0, "amount": 5.9e-05, "addr": "bc1q990yet582vs8xgl03gm4vy5asw03e73eexcqv0", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "1e28399b7b10a2c67fd41a7d08e7140e78f1a119983137f6705ad6a6b1cd03ed", "n": 0, "amount": 6e-05, "addr": "bc1qt2s2l85c859vj7fr4eglzwtr7l9xxvfann07kn", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "64b91630b822a56d61ec2fd6327a7b34f8bef7e289822eb5b1c57cc5edccaa29", "n": 0, "amount": 5.346e-05, "addr": "bc1qgxmv67fzgtxgp96ue5q295zevgp6mduf0m582ccycqlg4n64e72scg429d", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "4375cb0fbc2f958b92f52747bee2a3100dc3babc3b0b68db1d25588bb14f4da8", "n": 1, "amount": 5.213e-05, "addr": "bc1qkfpemx7397pm5pmewpf05d2ptnma8my00vjzmm", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "b0a7c7eb05faba2c346c08da46aad309fd1807a6ba1093b10878ae85b79eedf6", "n": 0, "amount": 5.748e-05, "addr": "32sE4ifoBMo49kdsn7LZvnCKNqZPdorzox", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "1226a7d11f50692bf6cb7b36a02735c011cc6fa0d096bb661e64d99b99593d9d", "n": 1, "amount": 5.731e-05, "addr": "1D88zgTXWz8CZBs7fzY2pNNygTjiooQBcT", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "58c1d1817fda7f2f47afbea7c29ad94b9ebe7ae2e87bab3e524e171d4737e75a", "n": 1, "amount": 5.46e-05, "addr": "bc1qxl9fpzfgwlvacem03e8yvpy3966qvhgd8usay8", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "766668856c9c8a257ecd97119105e9c2cac52edbc6b8023e6bce2137f318adf4", "n": 1, "amount": 5.46e-05, "addr": "bc1qwd3dg6hetenspv45a8c3jt89vt4vu4zh9j60ty", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "ac019e519c8f73830c0fb6c95be02daa4e9b531100dd11238b1056448ca91c56", "n": 0, "amount": 5.74e-05, "addr": "bc1qch2ugual8nq36nxw6z997k5pnfn0jh0z9txxqz", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "7e4325cd5641d972249bac0019ae7d14b1895f0c39914ccad1f91ed3fec164e5", "n": 1, "amount": 5.639e-05, "addr": "bc1qe22xnvztp8p4nxwdz2rs74ayjtqc2x0w88xguv", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "712d1a80b5fe4c840938a7d360cf34abf639da1f74c6113ab87d8c55fb5c75b0", "n": 1, "amount": 5.022e-05, "addr": "bc1q74wlpnvufcmwdj2l98mj86wdp9fce4dmuk2q0e", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "8b3f65b07640500accef83a47d9c38fd258876fbb99760de60422db5109a3d93", "n": 1, "amount": 5.976e-05, "addr": "bc1q3qyh55dkxf7al99nzmqjpx4cyza5293ylc2etv", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "7d928fee8d3c1235946ffaf8562915091fcd61b79caae992f7807911bf3a4d80", "n": 1, "amount": 5.432e-05, "addr": "bc1q3asva77spzgv4ufn04dn27y9lavrt3f3d8ucjz", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "434540559510ef26853801fe049ec2ad83cdc1cd99326dde7e8056bd1e3bce77", "n": 1, "amount": 5.967e-05, "addr": "bc1q9p42knl4e5zzx3ck06emkgzx4sz684nl5t56vh", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "7d41da196d0bab7c48d9b17a39df60e10f1e252b5e9e6afe7529c82afb8c3273", "n": 1, "amount": 5.951e-05, "addr": "bc1q8ltluv8e9ughrka58qznt07ssdvtkknr8vcnv5", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "97667c7606ddc57f84f34d6e64b71b8859dfc09fc92bc1efe0c88a492251eb68", "n": 1, "amount": 5.7e-05, "addr": "bc1qe8rv6ejfmclu62wwsm7hfletdj67m03vhpt4sa", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "c297f5fd3459cf34535b094ea8930d2d3279143603ef58fb54b26fb69ddd0a47", "n": 1, "amount": 5.047e-05, "addr": "bc1qe32pnkj477e9yphy65rafazs56ya5w6wsez5hr", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "d1f109f1f2197e7e7dbe5e96a01a8e8d04e2f333ea14c9d8a3b9ea08fefa2920", "n": 0, "amount": 5.732e-05, "addr": "bc1qd90eld8trlq6a30hy6jlxqvqjntgerw80warzk", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "d996d1bbe025f750c1ef64016076e317c952a3fd5f6e3af41199c767e4f76117", "n": 38, "amount": 5.957e-05, "addr": "bc1q4wt3zg7kf0m4ku3x3qu48uuc9hu0umagf485tg", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "f1d16d98758f6aa2e58800777890516de49f3e41158e8956f5997c8d4fefbd07", "n": 0, "amount": 5.737e-05, "addr": "bc1q63p9rrsdwxl74vf8pu4wl8jw4dghpqetrut39h", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "c5b8c6969378fc32ac6e1b642c2782fae46c41d5199f769f4ae709223ca48705", "n": 1, "amount": 5.313e-05, "addr": "bc1qhef0da8wl62neje7v05m0mus2xjr0vj4h0mpky", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "add11ad2f58f25bf242c6317b81e9bb6a8f50a44ac3af4b6711ab51f925f7704", "n": 0, "amount": 5.755e-05, "addr": "bc1q4289tjgfhqu8ezmvs2dyjgnvhy7wjy5qwap2jx", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "138851726acf2ed69be7c29861811dc9ca252278676ee31b5ee960da2b952713", "n": 0, "amount": 5.929e-05, "addr": "bc1qs0dtun0w2ramvrq307whuvqhc00f9yd3pxdupw", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "19fa7bc3a47ab3b1b079f458a18f99a089a800b4e918cab60765f83ded8f4401", "n": 0, "amount": 5.753e-05, "addr": "3Bm5hRHgjXW3yyVo7dYEkVBP3YY1uS6hW6", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "82d03a4fc00f086d0b2ff69d2df7d934ecd8c0b0e460391dfd2405f6a341d8ba", "n": 0, "amount": 5.736e-05, "addr": "159RebJhuUbimk4eUcPz7sniZu752psepi", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "dbbc52f74d6e9e0f8dcc9595e8fe5defb30a0407b8fbf78fd3cab1b96eb0d2c4", "n": 1, "amount": 5.73e-05, "addr": "1JiHjPVqdmyEkxX3GELsCKPthYTyau4MLM", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "417a0536b83ad8f8da4add8c10e532c072ef49aa5233f5749c2ab4e482fef377", "n": 56, "amount": 5.731e-05, "addr": "bc1q3pzek5pmj05lz45xj48a7p5akyqkzj28zhlgkc", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "61f7e11a6f6bee555f46cdcde6f44a06c568b6cbd49f9005e530da48296993af", "n": 55, "amount": 6.106e-05, "addr": "1QKuZGjpm3gDAtzULUo14yjSbnfHnxBNNW", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "61f7e11a6f6bee555f46cdcde6f44a06c568b6cbd49f9005e530da48296993af", "n": 0, "amount": 5.801e-05, "addr": "bc1qx46euxpjudvgnaedkmfwp3kexhmhrpznn6puxr", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "937af1a8e4e2a74f5bdaf1743900ab2ac63c61f01cdf79a9f6b31f3a69d8b5ef", "n": 52, "amount": 5.739e-05, "addr": "17ESKnEKhumJvTRAmA4pyjrUUAiXPU6UE1", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "2813606d2787cebc41810ba85d0c1244fc75d3eb164139f6d52a3c423ecf84b9", "n": 0, "amount": 5.951e-05, "addr": "bc1pgt9j8n375zsekzxheq9nph9cmzwchpnfuunm9nkkn8myjwxtv30s2y7ytx", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "7a69481ff477290e5628825a7bb61a35117d90183cfe270294dbc359db2f80fe", "n": 1, "amount": 5.277e-05, "addr": "bc1q5u509eqtuem4jxd6lmvk98fcv0nqxtat9capj7", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "6c30042b96158293a2ff82c3aba9542b0ac95e903c40acac1c608ed278a51a1f", "n": 1, "amount": 5.014e-05, "addr": "1KdrAgDuYuih5EwNk6ReEaZ5WMELhjRWrY", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "7be270df43db51f62e6b08612397a4cec063ab7e552293a14c1e952a831e8100", "n": 1, "amount": 5.038e-05, "addr": "bc1qjneyeq28f759s4hq4yj74zdlw44fdd6sx88nul", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "6bac6d5ee6d29e34675b442a05c0e58923acc6245190dc3a25f294a07241b364", "n": 1, "amount": 5.927e-05, "addr": "bc1qy4vmrz4760gqrym7gzy38hcnm3w3fnlvy3gkxr", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "3b6e0b0fd25da8ef0b42c0b58351ac32ea0d1c7d0085d88af4ae9c55c7fe3154", "n": 1, "amount": 5.731e-05, "addr": "1AhCeCBKBeSxp2QkLLwZFpBUSaXAHaqLEW", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "7ec05e57816865ce997408986b887ce47d5e10b0705e7781e4413a2eff7054f8", "n": 1, "amount": 6.006e-05, "addr": "bc1qcwt6kyvtfukrvawv859ghmyd4xfqf4ra3wd6rz", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "8581c181b746d44fc47985c1552f1072846f726e09b7c732f8b75ea544e673ca", "n": 0, "amount": 6.088e-05, "addr": "bc1q8at5yxqv39nnmzxtcytgs3u08m7f7kqn7z46l6", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "e7d448b3f8c82bfdca6fd3ed571f827ef65d63654b3acf5f1c14960616f0e96d", "n": 0, "amount": 5.346e-05, "addr": "bc1q3r38et5vxl3m6agv3nyv2g0cm0q43xrpma2v7zgekg6tqklxk4yst7s4zu", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "3590d113b23d5ba4cc845e07495d050ab463b3180fc2969a3b9d516e9d448398", "n": 1, "amount": 5.996e-05, "addr": "bc1ql6mpy5fsx79kzz7gl6c4pvyzwljxplxargetwy", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "8b673718781cc80456b8afa5fe30f649f372d27500ed71daae171f0ad9ee206a", "n": 0, "amount": 5.692e-05, "addr": "bc1qdqqsq6y7csd0cr3ye45h9lv8ydh777j2wehgl6", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "c6a27983826be0a3284fed3267a9b8853c87378fa9c903aedd841741d90f85f4", "n": 0, "amount": 5.163e-05, "addr": "bc1p67gn0lkcpv88jxpfmqsxk06hh2qwpry4lxqlteutcrtqz0ds8haszrjjr4", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "5a638f9a49c3528e1a39e89a74385c1be346311a30c8b1acd6f48f978953d72b", "n": 0, "amount": 5.737e-05, "addr": "bc1q69hw6zqwftyt79u4erskuefrxevsztu2y9edw6", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "8e4886764b97c9265ede46076bae0f548c8b2f47e2bba3fd8d8e737413508c25", "n": 0, "amount": 5.8e-05, "addr": "bc1qupngqpt94yyj66cmzcy98a2hh9w9tqrr5ecp24", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "03161cede92688f870b4c860c0a028d49926c28639e350963ba79dbc370a2304", "n": 1, "amount": 5.252e-05, "addr": "bc1qavxh442h96ultxkpwsxh28xp9fujnnvnar63xl", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "5eaa7a49434b4315d81b5e302fd379f9ae5b99bd6ab214e51103e56625f1473b", "n": 1, "amount": 5.283e-05, "addr": "bc1qslx3s0mls3vnurdu6u8l4tjf6zksr7xrvljxh3", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "5442300a2afbe6390af820e98c4cf2fc7c946b4a6cd488f15822e556e27dee35", "n": 1, "amount": 5.714e-05, "addr": "bc1qezx4p8y9yjvvc4482hfwjpn6uzmmkuq3sx4qfk", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "d15e8cc3d3f844817456e3a4979a8609141ae280f42a03283026df7eddb6d1c4", "n": 1, "amount": 5.469e-05, "addr": "bc1qgqq8v220nswqpvvky3tr4z8pkhtac05fwpzw6k", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "d376aafae79cf8eceddbdc04f3fed3a8b408eb904b03cf2bc9dbd6352093b949", "n": 1, "amount": 6e-05, "addr": "194fSg8qkafeguSGWwCRSxJKj63y6L83En", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "986b7ca48c112808776529b492d4cef8ce901d4010dd0eda0be7026079af974c", "n": 0, "amount": 6.088e-05, "addr": "bc1qmvrszt3tvnpn3g20fkycuj3r6j38s600aryc9p", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "726d358a1842f5aa84a5de3696da2256289b8363d1ec417f80056068fcbba013", "n": 0, "amount": 6.088e-05, "addr": "bc1qmldy0tfk464ma0sfv2drdtsyhlrz5ww4jtpe57", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "218251a954c54999e806e88b130dd73a0ddc169b91ce74fd8713fa9fd19a9ffc", "n": 1, "amount": 5.728e-05, "addr": "bc1q37z6ucrduxphunwrajem68hfsguqtw7clzmv5j", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "4a51620cbe9b23cc7fe263b71c74ff74b254c4d96a35e8be2b9fa035634fc027", "n": 1, "amount": 5.282e-05, "addr": "bc1qnwsuh0a2mqc998vdl042py98ag9wh5f78ea6wc", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "67f9bb775810aca5ca0ca4309ac83e6342f1da14fd0c2b98cb49e22ff6c23426", "n": 0, "amount": 5.062e-05, "addr": "bc1qltq2fyjypyygqh926rfl8ceymqajryreg5l56z", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "a2db00fb9ee820f8ec019839cb129ba88620ff7dc0d7c6cd132f80f7fc6f693a", "n": 0, "amount": 6.088e-05, "addr": "bc1q6tj2w5mv4ttn5fwewqgzn2smu5keh6f9lfh5xt", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "a398e9f78a8fa5037a9c1bf2526b073cea6fc3e1999fd0cbd52edd1587258325", "n": 0, "amount": 6.088e-05, "addr": "bc1qkgvatss5tsh2hpmupk0efrhctx8dagh7qt72ew", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "96ac7b80f30ae711d749243783727f688c5169d168d6aae23effb324beaef51b", "n": 0, "amount": 5.93e-05, "addr": "bc1qqjp3qaj0jp2f2umfchcndnkpfcfvkffs37d3a7", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "c7b442de965939648ea4f864b4efbf3dab7bda624db8f8aa0d2f105f316506ec", "n": 0, "amount": 5.826e-05, "addr": "bc1qdx25gyytfuckw668na8tj7fgukpxl483a2s8d3", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "4d7431a4d77babf722adc175f3cca2758cd428db2f197071abaacf83288d36e9", "n": 0, "amount": 5.116e-05, "addr": "bc1qkszaa6f7a27vrhkhamqcgpdr532mz2k3c9klez", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "9235350bbde63d59fd90b678fa83118e621a9b6e1774141d70e97b4e2c46884d", "n": 0, "amount": 5.886e-05, "addr": "bc1qdndt2l84760f7jlswexk09zjwef5tnwqj6f5cn", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "f7ff8566c4fd1308e40d42670ad70cb4c5b8365ef909864cc198b82b1fded9f4", "n": 0, "amount": 5.5e-05, "addr": "bc1qmz4wl8fdudya3up37w4849telj4r57rfp7kl8z", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "c970f241071b1cf58c3dfe648789b2bcec92174ccbf2b85b792b71deed85abc6", "n": 1, "amount": 6.033e-05, "addr": "3HkNBghJuttgS7YuoBTXi3rZhZMGy1qNkn", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "caa083d36d030af355b135fe020c2118f49a286f76b0de563df92ac944d7049e", "n": 1, "amount": 5.398e-05, "addr": "bc1qhvx7nyc5750rzk5wht6l8xfrh5k0mt7wqgn7fr", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "1d846e327e4e38dc9748b71cbacbd8837a87943ca050a30371fb1958d10205d2", "n": 1, "amount": 6.077e-05, "addr": "bc1q34f6gzeda6l2gdvarzvef9dtdt8xqskyanjv84", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "6900cc21a27720a5632ca90932659dac6195edc0fa00c613a237312fa23b5ad6", "n": 0, "amount": 5.826e-05, "addr": "bc1p8046kjeke6zlpyn3ewzdnmwsmh7ykzj292738fpzvum43twf2raqgax5sn", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "56b600a829ca00520e4411fd05da7f5b3ef47dad0f96554b8b86f616e0b031d3", "n": 0, "amount": 5.826e-05, "addr": "bc1pjgsam6wldm6s4p6w27h24fkua782h2fxrredhsgjhfjmlukanadsu2r2c6", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "5c48613651d9219261d4f97dac02ff577fe562fd510ffea41e04544db68b6ab0", "n": 0, "amount": 5.826e-05, "addr": "bc1p58cq68fffejj93hqqwurpcr3vrasnm4rj9edsmc5zeg0e5l6v4eswmanp8", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "e0789b1cab5a738868f6a88b7b6cd9353a535ed41dd26fd2024a491e69134daf", "n": 0, "amount": 5.826e-05, "addr": "bc1pmkuuzmgj0g9lhkqy9znvqylramnmcc06tfzjav7qv52tx7pcz5wsv08x09", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "16f5a6bf9d23e9b030caeea56fbe0d35959e8925790090bf927fa8a8d5ebb5a9", "n": 0, "amount": 5.826e-05, "addr": "bc1pjgsam6wldm6s4p6w27h24fkua782h2fxrredhsgjhfjmlukanadsu2r2c6", "block_time": 1766579584},
                    {"chain": "BTC", "txid": "ddcf00334c0852c89fd1a13dfc461e620e37a60bbc300e6f0d3077425f423fa6", "n": 0, "amount": 5.826e-05, "addr": "bc1pjgsam6wldm6s4p6w27h24fkua782h2fxrredhsgjhfjmlukanadsu2r2c6", "block_time": 1766579584}
    ]

    # Create a finding with search results
    search_finding = {
        "kind": "search_txs",
        "id": "search_txs:BTC@time(1766577965-1766579765)@amount(0.00005006-0.00006160)",
        "source": "search_btc_outputs",
        "rationale": "Search results for scoring test",
        "data": real_search_results  # The raw transaction data
    }

    # Add price finding for candidates
    price_finding = {
        "kind": "price",
        "id": "price:DOGE_in_BTC@time(1766579284-1766579884)",
        "source": "get_binance_price",
        "rationale": "Price for candidate validation",
        "data": {
            "price_min": 680272.1088435375,
            "price_max": 684931.506849315
        }
    }

    state["findings"].extend([search_finding, price_finding])  # type: ignore
    state["candidates_finding_ids"] = ["search_txs:BTC@time(1766577965-1766579765)@amount(0.00005006-0.00006160)"]

    # Use validate_node to build cclinks (matches real workflow)
    validate_result = validate_node(state)
    state["cclinks"] = validate_result["cclinks"]

    print("=" * 80)
    print("TEST: Score Node Step 5 - Generate CrossChainLinks and Scoring")
    print("=" * 80)
    print("\nScenario:")
    print(f"- Have {len(real_search_results)} BTC candidate transactions (with price data)")
    print("- Dst: DOGE 38.09399457 at time 1766579765")
    print("- Each candidate has price_min/price_max for scoring")
    print("- Using real search results from test_orch_batch_price.py")
    print("\nExpected output:")
    print("  - result['success'] = True")
    print("  - result['data'] is a ScoreTable with candidates sorted by confidence")
    print("  - Each candidate has: f_time, f_amount, confidence scores")
    print("  - best_match should be the highest confidence candidate")
    print("\n" + "=" * 80)

    # Run score node
    try:
        result = score_node(state)

        print("\n" + "=" * 80)
        print("RESULT:")
        print("=" * 80)

        # score_node returns {"result": {"success": True, "data": <score_table>}}
        if isinstance(result, dict) and "result" in result:
            inner_result = result["result"]
            print(f"\nSuccess: {inner_result['success']}")

            if inner_result["success"]:
                score_table = inner_result["data"]
                print(f"\nStatus: {score_table['status']}")
                print(f"Summary: {score_table['summary']}")
                print(f"\nScoring Params:")
                print(f"  tau_time: {score_table['params']['tau_time']}s")
                print(f"  max_fee_rate: {score_table['params']['max_fee_rate']:.2%}")
                print(f"  max_deviation_rate: {score_table['params']['max_deviation_rate']:.2%}")
                print(f"  w_time: {score_table['params']['w_time']}")
                print(f"  w_amount: {score_table['params']['w_amount']}")

                print(f"\nBest Match: {score_table['best_match']}")

                # Find ground truth transaction
                ground_truth_txid = "138851726acf2ed69be7c29861811dc9ca252278676ee31b5ee960da2b952713"
                ground_truth_rank = None
                ground_truth_link = None
                for i, link in enumerate(score_table['candidates'], 1):
                    if link.src_transfer.txid.lower() == ground_truth_txid.lower():
                        ground_truth_rank = i
                        ground_truth_link = link
                        break

                print(f"\nGROUND TRUTH ANALYSIS:")
                print(f"Ground truth TXID: {ground_truth_txid}")
                if ground_truth_rank:
                    print(f"Rank: {ground_truth_rank}/{len(score_table['candidates'])}")
                    print(f"Time diff: {ground_truth_link.time_diff}s")
                    print(f"Fee rate: [{ground_truth_link.fee_rate_min:.2%}, {ground_truth_link.fee_rate_max:.2%}]")
                    print(f"Confidence: F_time={ground_truth_link.f_time:.4f}, F_amount={ground_truth_link.f_amount:.4f}, Final={ground_truth_link.confidence:.4f}")
                    print(f"Excluded: {ground_truth_link.excluded}")
                    if ground_truth_link.excluded:
                        print(f"Exclude reason: {ground_truth_link.exclude_reason}")
                else:
                    print("Ground truth NOT FOUND in candidates!")

                print(f"\nTop 5 Candidates ({len(score_table['candidates'])} total):")
                for i, link in enumerate(score_table['candidates'][:5], 1):
                    print(f"  {i}. {link.src_transfer.chain}:{link.src_transfer.txid[:8]}... → "
                          f"{link.dst_transfer.chain}:{link.dst_transfer.txid[:8]}...")
                    print(f"     Time diff: {link.time_diff}s, Fee rate: [{link.fee_rate_min:.2%}, {link.fee_rate_max:.2%}]")
                    print(f"     Confidence: F_time={link.f_time:.4f}, F_amount={link.f_amount:.4f}, Final={link.confidence:.4f}")
                    print(f"     Excluded: {link.excluded}")
                    if link.excluded:
                        print(f"     Reason: {link.exclude_reason}")

            else:
                print(f"\nFailure reason: {inner_result.get('reason', 'Unknown')}")
        else:
            print(f"\nUnexpected result type: {type(result)}")
            print(f"Result: {result}")

    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 80)

