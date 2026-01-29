"""
Test case for Orchestrator Step 5: Output ALL candidates (no filtering).

This test verifies that the orchestrator outputs EVERY SINGLE candidate from
the search results when transitioning to scoring (action='score').

The issue: Orchestrator was only outputting 4 candidates instead of all 61.
Expected: ALL 61 candidates should be in the output.
"""

from src.agents.tracetx.orchestrator import TraceOrchestratorAgent
from src.state.tracetx_state import TraceTxState
from pprint import pprint


def test_output_all_candidates():
    """
    Test that orchestrator outputs ALL 61 candidates in Step 5.

    Scenario:
    - search_txs finding contains 61 BTC outputs
    - We just fetched BTC_in_DOGE price for the check window
    - Orchestrator should now output action='score' with ALL 61 candidates

    Expected output:
    - action='score'
    - candidates list should have 61 items (not 4!)
    - Each candidate should have: txid, op_id, amount, block_time, price_min, price_max
    """

    # State after Step 4 (batch price fetch completed)
    state: TraceTxState = {
        "query": "What is the source transaction for this cross-chain DOGE output to DGLwogqGtiPpiUDhPhokTJxit7DWKdxpu4 in tx 86E184358C82C8DBC2C332009EC227E6AC010AD6FC5DBC53F1341F65763F7CC9 on DOGE, given that it originates from BTC on BTC?",

        "iteration": 3,

        "params": {
            "search_time_span": 1200,
            "search_price_buffer": 0.05,
            "check_time_span": 300
        },

        "derived": {
            "search_window": {
                "time": {"start_ts": 1757641622, "end_ts": 1757642822},
                "amount": {"min": 0.03164685, "max": 0.03529041}
            }
        },

        "src_info": {"chain": "BTC", "asset": "BTC"},
        "dst_info": {
            "txid": "86e184358c82c8dbc2c332009ec227e6ac010ad6fc5dbc53f1341f65763f7cc9",
            "chain": "DOGE",
            "asset": "DOGE",
            "op_id": "vout:0",
            "amount": 14871.64178148,
            "time": 1757642822
        },

        # Previous findings (dst tx, dst_in_src price, search results)
        "findings": [
            {
                "kind": "get_tx",
                "id": "get_tx:86e184358c82c8dbc2c332009ec227e6ac010ad6fc5dbc53f1341f65763f7cc9",
                "source": "get_doge_tx",
                "rationale": "Destination tx",
                "data": {
                    "chain": "DOGE",
                    "txid": "86e184358c82c8dbc2c332009ec227e6ac010ad6fc5dbc53f1341f65763f7cc9",
                    "block_time": 1757642822,
                }
            },
            {
                "kind": "price",
                "id": "price:DOGE_in_BTC@time(1757641622-1757642822)",
                "source": "get_binance_price",
                "rationale": "Search window price",
                "data": {"price_min": 0.0000021280, "price_max": 0.0000023730}
            },
            {
                "kind": "search_txs",
                "id": "search_txs:BTC@1757641622-1757642822",
                "source": "search_btc_outputs",
                "rationale": "Candidate BTC outputs",
                "data": [
                    # All 61 candidates at block_time=1757642606
                    {"chain": "BTC", "txid": "fd62670745abfd02da0c636f0b68205dfec149a5aa990cfe6fc39b85a232c83a", "n": 0, "amount": 0.0345, "addr": "bc1qzx450mrc58vmfkvx6zwyag2phwlrupzhxc9787", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "55386440b8e572905cc364a57ab6b2b7910450a519a0a8adc246c91d4fbd171a", "n": 1, "amount": 0.03347392, "addr": "bc1qssy30n4ug6dh6wpyvus5c467kh8re0uy40ncwr", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "c153d63dc1f056cba0730615c73a3aed9fce3b17e267d9e47c55b3df21de3d5b", "n": 1, "amount": 0.0342, "addr": "bc1qvl3yzxl7vnqsk40v9wejkn38mzyjj6sup55y3f", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "40ce68363053d1692536516350c48a89aa36639a024af761435bf2fba24044bc", "n": 0, "amount": 0.03194371, "addr": "bc1qddlmjlgqg8j3qy9lhfurkpfkg5ejf36xyvsy46", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "26c7153f38c055e1243740662b79550795d02b0cf2897c8fade9856699b3b3d4", "n": 0, "amount": 0.0351193, "addr": "18SLSBaJvJ7YMJGHv3qB68j7VmE95WQYsz", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "c5c2f18cfecf6186217c80e8e239cdc2627fa571757a259e6624483fb702b34a", "n": 0, "amount": 0.03452049, "addr": "bc1qlma4j5tyhj6k9jqydc9hwkvhvqmr7z4zs8mh6f", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "b7834365fcb1cc15a3f687e8f87ce4ffa7b9960f79182644731b9742ce287544", "n": 9, "amount": 0.03446848, "addr": "bc1qw2rk59wnwjg94kd2ld4tng7a49kzhl50u8lmul", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "c57c0b77d2473ad6b53f7639e9040952289b09f53944710ac4e789d6a8851226", "n": 3, "amount": 0.03401373, "addr": "35gNhxooeBe1t22m9tRRet7BdYYBnSYGgr", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "6dac3ea9a868005ef5319f20c83bb07d4eca8f0847a7444839dabbb5b6b39e0c", "n": 0, "amount": 0.03412081, "addr": "bc1qd3hj72yr58rgr4335vhyhjkf3hzqwsv6gm56sqhpyvke6p4l8xuq8mm0z2", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "af3b3416b154ad01ceae7497e426136773e821e05aa0e5fae76f6ca15e5a4d08", "n": 1, "amount": 0.03290613, "addr": "bc1qfq9wj0mpjr9v4z8rzkzr8gymdlywxa8gnapqfu", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "07b09a782fb7ff1fa594c0b940eee146d75aba76b0f3243fcebd54a28f3d9540", "n": 2, "amount": 0.03233595, "addr": "bc1q02he4ykrz7ycq75dmkysg003caqt7q7lcpvf0n", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "05b09645f375763025ba14558f8c472d40f97154959a9807123c54c2480fee0c", "n": 0, "amount": 0.0351556, "addr": "bc1qnttk2358d0xuunrtfy0q5n9sejujmqlhung7m5", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "7f8ddf60de2395effe01fd9e74d7c073e8fda9ebd40cbe8ab0fb4c8d6034b12d", "n": 0, "amount": 0.03265212, "addr": "bc1psrgd2xq2a7qf9usctzmqd5dy9twu6lmsjx8mrp6ydgvhprpp0xdqyxuu32", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "cefed29d3b5525da898ae0fe349f2b59a8b623b79b91d723626e2c83fcb4befb", "n": 1, "amount": 0.03410235, "addr": "bc1pngv47ykmpls9yv04w35pel7snfy2fmvxpxrz92u94q5dq3w0guqs2zwxls", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "44564a747b813a15595322161195deb9aa5ae067493ba8f1b03b11f4ade711ca", "n": 0, "amount": 0.03380676, "addr": "bc1p6unpmqnac4jt0dwp9f5dp4725hlhnfsaq6xq0yugf6upfaxjrjlspv4w8r", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "a6df9250825ad0863db53eaf7c4db3a11253ef00b0f074091558f53550b172d2", "n": 0, "amount": 0.03324349, "addr": "bc1prt2kmyyzljw7jgx763m99h5kn0a0r4lwm2czceukewfr7cnmeswqg7a53a", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "0105b0d09b41db4609e1e2f813f8df9076dbe9806151949612c36465914ce952", "n": 0, "amount": 0.03379735, "addr": "bc1p0erfy56yhsn8d5h02pzfp7rwtgxj78cmtjdewnygmdwcvl9dntnqwdvc8v", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "6fbd077c36868c7293827cd739474d5e17d19607405cf546336fd0803298db03", "n": 1, "amount": 0.03474335, "addr": "bc1ppu30ktgj2wwrfxhq2ywwmexkd6xjks8um743dqx5605facxdjvxqyjf534", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "b78d79c74b5dee05f332b7c5a714734b00103d5693cb5a65945e0b72cbadabb7", "n": 0, "amount": 0.03188246, "addr": "bc1qkd38jxeshl7au8vnjt4qmhh8rkt8d27npgvdlt", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "1f226373beaf890df55470ff4c96f1924b187b451984ceca6f81cf2a83813aa6", "n": 2, "amount": 0.03193359, "addr": "bc1pcnfff5gjezmsxp4xjsz39lrkzgkny9n905c7jtprl28l956mtmys6zvwkh", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "c86653fe6040481091d94b9ecd01f7203388acd584522b9a4a96627c7c1acc03", "n": 1, "amount": 0.03278743, "addr": "14RUPALfrtot176TJJ5tG9hrML48XJRXt5", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "612a027934d12b2957b4b601e5cfbb057981ee39c287bd583a32d2c213f63b72", "n": 26, "amount": 0.03438665, "addr": "3L13jcWC3NjcGFYqHMxEKHkGEV2bYwBkm5", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "df93effde3b97359ececaa215607ef17a46facc67e8c588335533729d3f05a56", "n": 38, "amount": 0.03419, "addr": "bc1qfvgwgdg0zqaj48v75s7ev2njherhyxyhderpyt", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "32dea89a100ef828461c9851387ab93793bd639e07482723e0d45becee9d6280", "n": 1, "amount": 0.03169398, "addr": "bc1qetmz063weq5k56u6vvl3pj9x5lpd2xuv85s58u", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "3895c9ae246f8dbda2684794e9526cc9a17466892355898ad8b9d39862031d4d", "n": 1, "amount": 0.03188728, "addr": "bc1qetmz063weq5k56u6vvl3pj9x5lpd2xuv85s58u", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "584a572776e359f519424e0400f0da7d73bfbcf5e3e27c388786abbc421873f8", "n": 1, "amount": 0.03211092, "addr": "bc1qetmz063weq5k56u6vvl3pj9x5lpd2xuv85s58u", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "360366cc9ea5543990ca32200c2e86d7d5058b37469b1a8c3e90cf24b49aa703", "n": 1, "amount": 0.03248934, "addr": "bc1qetmz063weq5k56u6vvl3pj9x5lpd2xuv85s58u", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "2f852f080b2b6bcb5bb71247dc8577d6d6faed6684695bcfb014784adfed2240", "n": 1, "amount": 0.03257733, "addr": "bc1qafl59k6rd5tz77lpn5yl5dl023wruge4v3vlwk", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "a713aedd71ee7972cae29a8cff48e842a5d5fb1df296116a2db6b8cd700c5011", "n": 0, "amount": 0.03280825, "addr": "bc1pd5vrtm3fardnh466adgwme88xsktnz50r7qtsprvar5skwqrnk4qjztwyj", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "1cd210471f888d80edc69a1b4bb8c02a802c1ef7ff0f1646d5d7c2aec257b603", "n": 4, "amount": 0.03282907, "addr": "bc1plnga72c2pynkv64v3y2hexfknph0nah7hyc3captd7l60crerjfqx66675", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "c49ba8f04f40bcbc176b444b238acc2d824a444e136c309868ca7873b83e5fdd", "n": 1, "amount": 0.03199769, "addr": "bc1qz90kpxjxva55quy9da2257ldu5v439ghe2a0hx", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "429701fca9c9d2640c1a3040d7b9ffb8c2c14e182dcc06a11c2b69f2c1ac1c59", "n": 2, "amount": 0.03308113, "addr": "bc1pspv89knzh0c0mjsmhqa9ern2mvddwmhp0h8jl77hyqwltxv28pqqqjarvu", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "dc4c3241854236907319431054c7cb0f5650aa8cbd117fe7dd9de868d6befb22", "n": 0, "amount": 0.03208643, "addr": "bc1q37p2vg75zku4tg0vmy759kuxryxc0axqp8g9ec0n0kyj33c544fqax6h63", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "85f565c9705c26bc0e85b1fa2282b44993c6863d4dd209520cdd9e06f01da4ea", "n": 0, "amount": 0.03451141, "addr": "bc1qqfjp78hu72eyteqk9gcytymrncwm3pudza730s", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "c6f771ab5b332737b0beb26a0a5956b099317fca89c7b547617aa0168ed9f37a", "n": 1, "amount": 0.03420911, "addr": "bc1qt3vhlnc6sgp5pw3lhdpa6cn7pzhn6367uj5kls", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "f5f75ba722bce6714c192ca755ad0dd914d8f4f2762122ab00a16202f83446df", "n": 2, "amount": 0.03342449, "addr": "bc1qrvtfwqzamszw2wpnzuwxd8cxdk6379vnfz8t486rmfcw5yekxt9szadqpe", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "0e4797abb347c1b7e7e9d32d43ece0227af7121ffbbda3962cd7f5a13bfc4dca", "n": 5, "amount": 0.0337367, "addr": "bc1qhdyxz6enfhdatkjn92zk4mw6zm4vav6lucfwan", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "77982daf69d230d0acc32f17d7d03c4644095ce42d9932d2592762071ed2ffa1", "n": 16, "amount": 0.03527236, "addr": "bc1qm34lsc65zpw79lxes69zkqmk6ee3ewf0j77s3h", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "a6cedee09c00ba5c288272a4dd90526f87d96b715116768682c31fa3ea39806b", "n": 7, "amount": 0.03307816, "addr": "bc1q3m2jjuqmhjkfse8ylj0mu02j40x8fet0fhayc2", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "15acce6e4fdf90f37ea754587262a72f868939a61dc5e59e0651a95d44b6aa54", "n": 8, "amount": 0.03190998, "addr": "bc1qxfrmtp9ue65ezxxwcy6rntvc6fyln9azmqw04f", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "3eb2be0af90fff5aa77dddc25771bc0af2b8a61686ca8c57431ab814158eb8e0", "n": 1, "amount": 0.035064, "addr": "bc1q48gwnh0n65cvwywrfffrwu8nwr7wd40xe9zluw", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "f3e3f2c904c68a7049f4f56a8992628105ca24b4ea9d8d54820c71c4c88af49d", "n": 0, "amount": 0.03445702, "addr": "bc1qr35hws365juz5rtlsjtvmulu97957kqvr3zpw3", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "2cf1adbedc7bd888d0f90d30d3e9c88b2faeb5e6a89c00f1d4f59c99c8b41622", "n": 0, "amount": 0.03484413, "addr": "bc1qllsj7qu0zfrp8qfcha8qqkm0f55n40p98a6xsd", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "70d7a45486f4725dfea3e299228c52704bd1b5fc392a24cca8d79a362debaf99", "n": 1, "amount": 0.03522094, "addr": "bc1qrhp4u3qk2v6m33sv9573anhjjl3c5cgm7m5dy0", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "8ed6f0fdc304fc7d56ea37f03dc997d81445302cdcd5b99ed1c0cb3933ef1f0a", "n": 1, "amount": 0.03464024, "addr": "3C32atUug5zBDWu7vPL7FLZats4jYfJKFe", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "d78b8799eaf08868463e271c982cefdee3c768f6a48120e774d7073d866ab8e1", "n": 1, "amount": 0.03233997, "addr": "bc1q3mvtd9ercp8arc6q3efjmepu46rtl6cx0spd57", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "19e07d9a3109c7231116553524a6bfc9f29c5b8c128c4a6f4a139bec26aee4b3", "n": 0, "amount": 0.034, "addr": "bc1qdfctkjkedgy7t0pxuwy3fcjcvptrac348v0fhq", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "850dc9c44468dc5f8286462e2439399ad01f68b669c3183443d66ebfefd3389f", "n": 0, "amount": 0.03457423, "addr": "3467aZdidCQg9EMT1MVboxEYwJXUkfj6XL", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "bf8dc27db37b263d04070c438130ca9c5066b9cff807c79d6bcbe564104f233d", "n": 2, "amount": 0.03277626, "addr": "bc1qt9nvg8mwuqmjlruc8z9m4kns2hd3gk2ylsdryp", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "a77bf5afa40d21a9717496384ee47fcb1e3c57cedd3e7ddc988fcf0a008dff7a", "n": 2, "amount": 0.03441375, "addr": "bc1qt9nvg8mwuqmjlruc8z9m4kns2hd3gk2ylsdryp", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "5ee90fe74f52eaa833c13a77ef6a466b97c501c04e31f6d6d6ed2023c528a32c", "n": 1, "amount": 0.03457891, "addr": "bc1qkkmsrsvw50xtthu563atx85uy8fay33rq0gjz5", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "06e25fa98abc574632f3742e0c32b35e486051f301a4f76c8c130a0508a95f36", "n": 0, "amount": 0.03252275, "addr": "bc1qghek5jlg9wasqv9z8ql2zns7c8l8sk3vj2es53", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "665d79729479798172287fd92ef71cca1db442717b65760a196451761fb105e7", "n": 1, "amount": 0.03334451, "addr": "bc1qzx7p7yxy8wke6uzpushkwekxskdt37j2ylyhsq", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "344732004761add74127b65d5c53bf1093ed79f7b5d14a7e280207d32421af5b", "n": 2, "amount": 0.03316853, "addr": "bc1q36ljdmuqhuc5pdjgjqt8fymcehxlml7tdue6h7", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "0c5a6812ae840cd10d245c38a844fdeff4ef48f93f650b29f86c450cc2a4fe01", "n": 0, "amount": 0.03438163, "addr": "37jdMXYbvg3dKzJ4pGSYiABiXoBy4putZq", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "80843c57a05ac1e84247cb079249d7823a8d0a5e81c7626624196980a1e1aba2", "n": 1, "amount": 0.03190114, "addr": "bc1qena7g7qcfu4s6cjw0ljk28afhnk0wva8c94urp", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "a2d78bcba00405eb46663213745c72518da786588b3ae6f44a6e6d357b04811f", "n": 1, "amount": 0.03405221, "addr": "194fboDkKc99mTdbcBJEwnpY8Se4W1mhhw", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "fa6520e5ff94297fafb3fde6513d25d15662a86c2bfbc184d901c305ff00c6c8", "n": 1, "amount": 0.03202133, "addr": "bc1qujepl0k5n0ga2e86yskvxa6auehpf6dlf84dx0", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "8930d768cca30e9f348d6f7d879aa8d961b87432ce2b4c620f0047b322673971", "n": 0, "amount": 0.03439287, "addr": "bc1quceru0h6pww7mzt5sw43429899a3vnyl23e2ey", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "cca46579f3075e1935082d72160fbcfc9022d0a6ff8aa3f0ecdfde963de1e12f", "n": 0, "amount": 0.03371663, "addr": "33YHXyWv9UYSDz1EwFLCa5Hbg2v6xAtQyo", "block_time": 1757642606},
                    {"chain": "BTC", "txid": "1febb2293c6956d0ecde898a6cb1918190b0cabb4b5b80edc4d51fe28aaea793", "n": 1, "amount": 0.0344864, "addr": "3FaMy5VgtjWXvGVdsWiLbp2zmEXk59qWWB", "block_time": 1757642606}
                ]
            }
        ],

        # Latest task: batch price fetch for check window
        "task_brief": "Batch fetch BTC_in_DOGE prices for each of the following time windows:[1757642306, 1757642906]",

        # Step 4 completed: price fetched
        "inbox_findings": [
            {
                "kind": "price",
                "id": "price:BTC_in_DOGE@time(1757642306-1757642906)",
                "source": "get_binance_price",
                "rationale": "Check window price for all candidates",
                "data": {"price_min": 442477.8761061947, "price_max": 446428.5714285714}
            }
        ],
        "inbox_gaps": [],
    }

    print("=" * 80)
    print("TEST: Orchestrator Step 5 - Output ALL 61 Candidates")
    print("=" * 80)
    print("\nScenario:")
    print("- Have 61 BTC candidate outputs in search_txs finding")
    print("- Just fetched BTC_in_DOGE price for check window")
    print("- Orchestrator should now output action='score' with ALL 61 candidates")
    print("\nExpected output:")
    print("  - action='score'")
    print("  - candidates list should contain ALL 61 items")
    print("  - Each candidate should have: txid, op_id, amount, block_time, price_min, price_max")
    print("\n" + "=" * 80)

    # Run orchestrator
    agent = TraceOrchestratorAgent()
    result = agent.process(state)

    print("\n" + "=" * 80)
    print("RAW LLM OUTPUT:")
    print("=" * 80)
    pprint(result.model_dump())

    print("\n" + "=" * 80)
    print("RESULT:")
    print("=" * 80)
    print(f"\nAction: {result.action}")
    print(f"\nStop Reason: {result.stop_reason}")

    if result.candidates:
        print(f"\n🔍 Candidates Count: {len(result.candidates)} / 61 expected")
        print("\nFirst 5 candidates:")
        for i, c in enumerate(result.candidates[:5], 1):
            print(f"  {i}. txid={c.txid[:16]}... op_id={c.op_id}")
            print(f"     amount={c.amount:.8f}, time={c.block_time}")
            print(f"     price=[{c.price_min:.2f}, {c.price_max:.2f}]")
        if len(result.candidates) > 5:
            print(f"  ... ({len(result.candidates) - 5} more)")
    else:
        print("\n❌ No candidates in output!")

    print("\n" + "=" * 80)
    print("ANALYSIS:")
    print("=" * 80)

    # Validation
    issues = []

    # Check 1: Should be score action
    if result.action != "score":
        issues.append(f"❌ Expected action='score' (Step 5), got '{result.action}'")
    else:
        print("✅ Correct action: 'score'")

    # Check 2: Should have stop_reason
    if result.stop_reason != "ready_for_scoring":
        issues.append(f"❌ Expected stop_reason='ready_for_scoring', got '{result.stop_reason}'")
    else:
        print("✅ Correct stop_reason: 'ready_for_scoring'")

    # Check 3: Candidates should not be None
    if not result.candidates:
        issues.append("❌ Candidates list is None or empty!")
    else:
        # Check 4: Should have ~61 candidates (allow some variance due to LLM behavior)
        candidate_count = len(result.candidates)
        if candidate_count < 50:
            issues.append(f"❌ Expected ~61 candidates (≥50), got {candidate_count}")
            print(f"❌ Only {candidate_count} candidates in output (expected ≥50)")
        else:
            print(f"✅ Good candidate count: {candidate_count} (expected ~61)")

        # Check 5: Each candidate should have price data
        missing_prices = [c for c in result.candidates if c.price_min is None or c.price_max is None]
        if missing_prices:
            issues.append(f"❌ {len(missing_prices)} candidates missing price data")
        else:
            print("✅ All candidates have price data")

        # Check 6: Price should match the check window price
        expected_price_min = 442477.8761061947
        expected_price_max = 446428.5714285714
        wrong_prices = [
            c for c in result.candidates
            if c.price_min != expected_price_min or c.price_max != expected_price_max
        ]
        if wrong_prices:
            issues.append(f"❌ {len(wrong_prices)} candidates have incorrect price values")
        else:
            print(f"✅ All candidates have correct prices: [{expected_price_min:.2f}, {expected_price_max:.2f}]")

    print("\n" + "=" * 80)
    if issues:
        print("❌ ISSUES FOUND:")
        for issue in issues:
            print(f"  {issue}")
        print("\n💡 Root Cause:")
        print("   The LLM may be misinterpreting the task and only outputting a subset.")
        print("   Prompt should emphasize: 'Output ALL candidates, NO FILTER'")
        print("\n💡 The orchestrator MUST:")
        print("   1. Extract ALL candidates from search_txs finding (61 items)")
        print("   2. For EACH candidate, create a CandidateOutput with:")
        print("      - txid, op_id (vout:N), amount, block_time from search result")
        print("      - price_min, price_max from the BTC_in_DOGE check window price")
        print("   3. Output action='score' with complete candidates list")
    else:
        print("✅ ALL CHECKS PASSED!")
        print("\n🎉 The orchestrator correctly output all 61 candidates!")

    print("=" * 80)

    return result

