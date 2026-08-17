# SkipGo completion-time histogram report

## Filter counts

| Metric | Count |
|---|---:|
| `input_rows` | `25406` |
| `kept_rows` | `24926` |
| `drop_status_timeout` | `288` |
| `drop_status_not_found` | `192` |

## Overall summary

| Metric | Value |
|---|---:|
| `count` | `24926.000` |
| `min` | `1.668` |
| `p50` | `15.506` |
| `p90` | `61.854` |
| `p95` | `109.921` |
| `p99` | `298.112` |
| `max` | `1072329.160` |
| `mean` | `1048.663` |
| `median` | `15.506` |

## Dataset summary

| Dataset | Count | Min | P50 | P90 | P95 | P99 | Max | Mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `osmosis_osmosis-1_latest_1000000_c50000` | 24926 | 1.668 | 15.506 | 61.854 | 109.921 | 298.112 | 1072329.160 | 1048.663 |

## Top route summary

| Rank | Dataset | Route key | Count | Mean | P50 | P90 | P95 | Max |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-21113|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 25 | 360093.229 | 458326.657 | 745968.057 | 752043.257 | 846846.657 |
| 2 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-362|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 9 | 269496.957 | 198446.035 | 475047.156 | 481678.723 | 488310.289 |
| 3 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-232|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 13 | 107695.816 | 110.901 | 491487.808 | 544729.408 | 552566.608 |
| 4 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-1634|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 4 | 28739.079 | 90.927 | 80326.357 | 97518.929 | 114711.500 |
| 5 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-6787|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 3 | 15325.354 | 7.317 | 36772.674 | 41368.343 | 45964.013 |
| 6 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-38946|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 515 | 14126.186 | 96.123 | 198.522 | 220.146 | 1072329.160 |
| 7 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-184|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 40 | 12080.539 | 16.929 | 12087.458 | 126760.615 | 127015.165 |
| 8 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-108|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 16 | 12000.560 | 24.906 | 38809.724 | 62205.377 | 109177.587 |
| 9 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-6787|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 202 | 10310.057 | 13.137 | 55504.418 | 77785.568 | 113851.718 |
| 10 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-75016|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 15 | 6576.217 | 52.108 | 31708.282 | 37565.261 | 37636.661 |
| 11 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-73755|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 11 | 3551.202 | 15.474 | 135.079 | 19444.596 | 38754.112 |
| 12 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-106313|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 149 | 2664.790 | 14.244 | 85.660 | 19894.631 | 63648.046 |
| 13 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-73|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 17 | 2046.898 | 13.753 | 21.083 | 6931.959 | 34571.271 |
| 14 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-144|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 51 | 1511.070 | 13.392 | 17.747 | 75.192 | 76139.078 |
| 15 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-1|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 993 | 270.798 | 25.670 | 48.928 | 60.708 | 57109.718 |
| 16 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-522|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 36 | 236.276 | 233.428 | 578.971 | 613.387 | 652.495 |
| 17 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-750|entry_point->ibc_transfer_adapter` | 1106 | 182.474 | 72.027 | 183.865 | 257.059 | 25220.410 |
| 18 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-188|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 22 | 125.597 | 131.144 | 216.018 | 224.294 | 232.009 |
| 19 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-2186|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 9 | 112.438 | 102.972 | 202.670 | 240.096 | 277.522 |
| 20 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-76971|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 94 | 91.360 | 28.157 | 38.986 | 44.410 | 5911.198 |
| 21 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-143|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 185 | 82.186 | 24.095 | 106.311 | 407.774 | 1661.666 |
| 22 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-106313|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 3 | 77.039 | 16.581 | 162.862 | 181.147 | 199.432 |
| 23 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-326|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 357 | 75.501 | 11.299 | 46.288 | 205.890 | 6032.236 |
| 24 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-782|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 74 | 71.770 | 46.330 | 166.169 | 217.469 | 258.741 |
| 25 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-750|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 3729 | 65.134 | 24.756 | 99.833 | 129.149 | 36453.007 |
| 26 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-72|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 12 | 59.072 | 51.828 | 76.783 | 116.544 | 162.745 |
| 27 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-106275|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 3 | 50.013 | 43.775 | 73.603 | 77.331 | 81.060 |
| 28 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-72|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 2329 | 47.573 | 36.471 | 62.956 | 91.242 | 687.128 |
| 29 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-78488|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 30 | 44.435 | 40.724 | 54.203 | 54.819 | 155.304 |
| 30 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-750|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 15 | 43.683 | 22.234 | 80.598 | 149.979 | 263.119 |
| 31 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-259|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 17 | 38.195 | 16.576 | 40.216 | 116.726 | 328.259 |
| 32 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-42|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 281 | 32.283 | 23.650 | 41.126 | 82.066 | 344.041 |
| 33 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-22172|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 14 | 32.141 | 15.976 | 62.004 | 112.004 | 179.906 |
| 34 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-6994|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 1011 | 31.284 | 21.319 | 53.381 | 89.199 | 298.420 |
| 35 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-1429|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 31 | 30.411 | 14.214 | 17.503 | 132.438 | 300.507 |
| 36 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-104311|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 3 | 28.426 | 25.653 | 36.039 | 37.337 | 38.635 |
| 37 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-4|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 180 | 27.701 | 22.205 | 45.140 | 53.274 | 212.373 |
| 38 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-0|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 6 | 27.292 | 25.295 | 41.262 | 41.949 | 42.636 |
| 39 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-146|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 70 | 27.205 | 20.012 | 40.105 | 46.339 | 277.154 |
| 40 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-8|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 29 | 26.336 | 21.952 | 37.794 | 48.047 | 58.100 |
| 41 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-89321|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 130 | 23.935 | 12.844 | 20.399 | 115.138 | 276.952 |
| 42 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-1|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 8 | 23.174 | 25.045 | 30.325 | 30.878 | 31.430 |
| 43 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-101635|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 284 | 21.496 | 20.666 | 26.857 | 27.880 | 121.903 |
| 44 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-251|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 1387 | 20.727 | 16.544 | 23.032 | 28.329 | 516.911 |
| 45 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-42|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 3 | 19.278 | 13.634 | 27.219 | 28.917 | 30.615 |
| 46 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-6994|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 3 | 19.148 | 18.779 | 20.887 | 21.151 | 21.415 |
| 47 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-340|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 225 | 18.966 | 15.571 | 19.357 | 22.797 | 170.065 |
| 48 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-1575|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 9 | 17.168 | 15.947 | 21.669 | 22.131 | 22.593 |
| 49 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-340|ibc_transfer_adapter->entry_point->poolmanager_swap_adapter` | 4 | 17.154 | 17.377 | 18.923 | 19.243 | 19.563 |
| 50 | `osmosis_osmosis-1_latest_1000000_c50000` | `channel-222|entry_point->poolmanager_swap_adapter->ibc_transfer_adapter` | 116 | 16.700 | 12.541 | 16.250 | 17.494 | 217.658 |

## Plot files

- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/completion_seconds_histogram_overall.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/completion_seconds_histogram_overall_logy.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/completion_seconds_histogram_overall_clipped_p99.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/dataset_histograms/osmosis_osmosis-1_latest_1000000_c50000.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_mean_completion_seconds_top_routes.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/01_osmosis_osmosis-1_latest_1000000_c50000_channel-21113_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/02_osmosis_osmosis-1_latest_1000000_c50000_channel-362_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/03_osmosis_osmosis-1_latest_1000000_c50000_channel-232_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/04_osmosis_osmosis-1_latest_1000000_c50000_channel-1634_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/05_osmosis_osmosis-1_latest_1000000_c50000_channel-6787_ibc_transfer_adapter-_entry_point-_poolmanager_swap_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/06_osmosis_osmosis-1_latest_1000000_c50000_channel-38946_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/07_osmosis_osmosis-1_latest_1000000_c50000_channel-184_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/08_osmosis_osmosis-1_latest_1000000_c50000_channel-108_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/09_osmosis_osmosis-1_latest_1000000_c50000_channel-6787_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/10_osmosis_osmosis-1_latest_1000000_c50000_channel-75016_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/11_osmosis_osmosis-1_latest_1000000_c50000_channel-73755_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/12_osmosis_osmosis-1_latest_1000000_c50000_channel-106313_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/13_osmosis_osmosis-1_latest_1000000_c50000_channel-73_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/14_osmosis_osmosis-1_latest_1000000_c50000_channel-144_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/15_osmosis_osmosis-1_latest_1000000_c50000_channel-1_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/16_osmosis_osmosis-1_latest_1000000_c50000_channel-522_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/17_osmosis_osmosis-1_latest_1000000_c50000_channel-750_entry_point-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/18_osmosis_osmosis-1_latest_1000000_c50000_channel-188_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/19_osmosis_osmosis-1_latest_1000000_c50000_channel-2186_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/20_osmosis_osmosis-1_latest_1000000_c50000_channel-76971_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/21_osmosis_osmosis-1_latest_1000000_c50000_channel-143_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/22_osmosis_osmosis-1_latest_1000000_c50000_channel-106313_ibc_transfer_adapter-_entry_point-_poolmanager_swap_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/23_osmosis_osmosis-1_latest_1000000_c50000_channel-326_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/24_osmosis_osmosis-1_latest_1000000_c50000_channel-782_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/25_osmosis_osmosis-1_latest_1000000_c50000_channel-750_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/26_osmosis_osmosis-1_latest_1000000_c50000_channel-72_ibc_transfer_adapter-_entry_point-_poolmanager_swap_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/27_osmosis_osmosis-1_latest_1000000_c50000_channel-106275_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/28_osmosis_osmosis-1_latest_1000000_c50000_channel-72_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/29_osmosis_osmosis-1_latest_1000000_c50000_channel-78488_entry_point-_poolmanager_swap_adapter-_ibc_transfer_adapter.png`
- `skipgo_paper_data/figures/osmosis_1000k_completion_time_histograms/route_histograms/30_osmosis_osmosis-1_latest_1000000_c50000_channel-750_ibc_transfer_adapter-_entry_point-_poolmanager_swap_adapter.png`