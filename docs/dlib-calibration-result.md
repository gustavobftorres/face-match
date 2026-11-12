# Frozen public Dlib calibration result

The production Dlib adapter completed the predeclared public LFW View 1
calibration on 12 November 2026, using all 2,200 `pairsDevTrain` pairs: 1,100 mated
and 1,100 nonmated. It reused the verified local public acquisition, without
new downloads or private-media inference. The objective, source code,
preprocessing and acquisition rules remained frozen after inference began.
See [the calibration protocol](dlib-calibration.md).

The frozen decision is **negative-distance score > -0.5567551387797269**, exactly
equivalent to **raw distance < 0.5567551387797269**. Equality rejects. This is a
negative Euclidean distance threshold, not a cosine threshold. Selection
maximized completed-pair empirical TPR subject to empirical FPR ≤ 0.001, with
higher, stricter score thresholds winning TPR ties. Both classes exceeded the
predeclared minimum of 500 completed scores.

| Pair class | Total | Completed scores | Scan no-face | Reference acquisition errors |
| --- | ---: | ---: | ---: | ---: |
| Mated | 1,100 | 1,090 | 8 | 2 |
| Nonmated | 1,100 | 1,089 | 5 | 6 |

All eight reported errors were empty reference acquisitions. Production's
encoder catches internal exceptions and returns an empty encoding list; its
outputs cannot distinguish an ordinary detection failure from a swallowed
internal exception. Failures supplied no fabricated score, were excluded from
threshold fitting, and did not accept in end-to-end evaluation.

The following comparison reinterprets the **same stored scores**, without
repeating inference or modifying acquisition. The baseline is production's
strict `score > -0.6`, equivalent to `distance < 0.6`.

| Decision threshold | TP | FP | Completed-pair TPR | Completed-pair FPR | End-to-end TPR | End-to-end FPR |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Production distance < 0.6 | 1,062 | 9 | 97.4312% | 0.826446% | 96.5455% | 0.818182% |
| Frozen distance < 0.5567551387797269 | 1,020 | 1 | 93.5780% | 0.0918274% | 92.7273% | 0.0909091% |

Completed-pair rates use 1,090 mated and 1,089 nonmated scores. End-to-end rates
use all 1,100 pairs in each class. The stricter calibrated threshold reduces
false positives from nine to one and accepted mated pairs from 1,062 to 1,020.
It has 80 end-to-end mated misses: 70 completed-score rejections, eight scan
no-face results and two reference acquisition errors. Production's configured
threshold was not changed by this experiment.

## Frozen configuration and provenance

Each pair retained its original direction. Dlib used the first reference
encoding, even if several faces were detected, and the maximum negative
distance across all scan encodings. No image was swapped. The source contained
3,443 individually hashed full 250×250 LFW images. Production preprocessing
performed EXIF transpose and RGB conversion, with a 1,000-pixel LANCZOS thumbnail
bound. The native defaults were HOG detection with one upsample, small five-point
landmarks, ResNet descriptors and one jitter. The compiled HOG detector is
covered by the Dlib binary hash. The API also loads 68-point landmark and CNN
detector weights at import; neither was used by these defaults.

The protocol was written at `2026-11-12T16:23:44.123481+00:00`, before the first
encoding. Runtime was Python 3.13.14 on macOS 26.6.2 arm64, face-recognition
1.3.0, face-recognition-models 0.3.0, Dlib 20.0.1, NumPy 2.5.4 and Pillow 12.3.0.

| Frozen artifact | SHA256 |
| --- | --- |
| Original `lfw.tgz` | `055f7d9c632d7370e6fb4afc7468d40f970c34a80d4c6f50ffec63f5a8d536c0` |
| `pairsDevTrain.txt` | `1d454dada7dfeca0e7eab6f65dc4e97a6312d44cf142207be28d688be92aabfa` |
| Image SHA256 manifest | `d275b321d48a1ca48b58bad9b1da0d9ededcc5536b663f8e42e1b180bd49e811` |
| Frozen `protocol.json` | `29bdfa12195749771953ed58a0b09c8ddc2a5e10682049c5035c86904f67b62b` |
| `threshold-result.json` receipt | `5851aaeef6b698260b3e63a91473f47209fc46a889119becc4c4a58bb7fe3f3d` |
| `scores.jsonl` | `62ff9a10fbfa33e4a8d27efbd76002df437a7a57fbf82ac06d96aa8a3860ebed` |
| `decisions.json` | `4bc08534d996b9ff05152abdd52ad822c3b3acf08cbf8e7f343d19a1b9864938` |
| Dlib calibration implementation | `7f5463dc32a00c1d64c4a54a69d749eb2492c4fbd602b2fbe68ba0506cd6c4df` |
| LFW acquisition helper | `fe32e172c68e518b00b9c3ef9541a0e67efeec0a45f678c74180013a9304cb2a` |
| Face-search adapter implementation | `22e8bdfcebf008396120e0d473b11ebe677e6c23db58ba81b19a9daa5312162f` |
| Production AI service implementation | `6932437ddd6bd2ce480c866b6408cc4cc24be01939dde61f21890e94c77e09c2` |
| Face-recognition API | `b4b0fb151588befa7270273b5a243537e532aba8a14674507806a18ba4a4c35e` |
| Dlib Python entry point | `1c46bd888b62a0a59af8b932f67528bb9c7fb7945bb0f1f2512fd294ab510fc3` |
| Dlib native binary | `0a0e75eb374cb0ca2d5afd8cc59124c9e8c1dec27620b25ab816eeaf2637fcc9` |
| Small five-point landmarks | `c4b1e9804792707d3a405c2c16a80a20269e6675021f64a41d30fffafbc41888` |
| ResNet face descriptor | `55533b28a95800a551ba546ba62fe69625c7e95a7061c338adffead08719da30` |
| Model locator implementation | `5b6daa86bef028cdb5092bb955f2f0c948246f44d46afa4e42b2fca040b7c595` |

The full receipt remains at
`/private/tmp/face-match-dlib-lfw-calibration/threshold-result.json`, with explicit
`selection.score_threshold` and `selection.distance_threshold`. Images,
embeddings and individual pair records remain outside Git. The preceding
AuraFace calibration artifacts and protocol were not modified.

Offline verification checked all 2,200 original pair records, class counts,
input hashes, unchanged protocol/code/runtime/model hashes, recomputed threshold
selection, every stored decision, receipt hashes and coverage. Independent
review additionally confirmed threshold optimality and artifact integrity.
Verification and the baseline comparison performed no native image inference.

## Timing and interpretation limits

The scoring run took **75.19 seconds with encoding memoization**, retaining
production's reference cache and caching ordered encodings by byte SHA256.
There were 4,074 encoder requests, 638 memo hits and 3,436 unique encoded
contents. Scan failures can return before a reference is acquired. This elapsed
time is **not a latency benchmark** and must not be used as a direct performance
comparison with an unmemoized pipeline or a different adapter's calibration run.

The reported rates are in-sample calibration statistics. A single observed
false positive among 1,089 completed negatives satisfies the empirical target;
it does not guarantee a population or private-domain FPR ≤ 0.001. Possible Dlib
pretraining overlap with LFW is unknown, and training independence is not
claimed. LFW labels identify the central face while the application may match
any scan face. Celebrity pair verification at 250×250 does not establish
accuracy on private collections, multi-person photos, different capture conditions
or gallery search. No private labels selected or changed this threshold.
