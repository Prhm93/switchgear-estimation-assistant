# Evaluation

Written by `python -m backend.evaluation_report`. Every number below was run on the laptop; a row that needs model recordings says "waiting for Colab recordings". Field cells are P, R, **F1** (TP/FP/FN); a value counts when its field, file, page, value and unit match the answer key (docs/stage-2.md).

## Fresh set, not used for tuning (set hash c1488dbdeec22ed5)

20 projects (F01 to F20); 34 min of reading on the laptop.

### Field values (all fields, micro-averaged)

| Method | Drawing | P, R, **F1** (TP/FP/FN) |
|---|---|---|
| Rules | DXF | 0.971, 0.621, **0.758** (1754/52/1070) |
| Rules | none (drawing not read) | 1.000, 0.254, **0.405** (716/0/2108) |
| Rules + OCR | clean, no DXF | 0.993, 0.510, **0.674** (1439/10/1385) |
| Rules + OCR | scanned, no DXF | 0.989, 0.499, **0.663** (1408/15/1416) |
| Rules + OCR | photo, no DXF | 0.978, 0.329, **0.493** (930/21/1894) |
| Rules + model (v2, strict) | DXF | 0.842, 0.858, **0.850** (2423/454/401) |
| Rules + model (v2, strict) | none | 0.890, 0.415, **0.566** (1173/145/1651) |
| Model alone (v2, strict) | DXF | 0.832, 0.705, **0.763** (1990/402/834) |
| Model alone (v2, strict) | none | 0.882, 0.383, **0.534** (1081/145/1743) |
| Rules + OCR + vision | clean, no DXF | 0.991, 0.568, **0.722** (1604/14/1220) |
| Rules + OCR + vision | scanned, no DXF | 0.984, 0.574, **0.725** (1620/27/1204) |
| Rules + OCR + vision | photo, no DXF | 0.954, 0.444, **0.606** (1253/60/1571) |

### Field values per field group: F1 (TP/FP/FN)

| Field group | Rules, DXF | Rules, no drawing | Rules + OCR, clean | Rules + OCR, scanned | Rules + OCR, photo | Rules + model, DXF | Rules + model, none | Model alone, DXF | Model alone, none | Rules + OCR + vision, clean | Rules + OCR + vision, scanned | Rules + OCR + vision, photo |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| busbar.rating | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.519 (14/0/26) | 0.963 (39/2/1) | 0.656 (20/1/20) | 0.963 (39/2/1) | 0.656 (20/1/20) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.519 (14/0/26) |
| enclosure.cable_entry | 0.643 (27/0/30) | 0.480 (18/0/39) | 0.643 (27/0/30) | 0.643 (27/0/30) | 0.575 (23/0/34) | 0.906 (48/1/9) | 0.739 (34/1/23) | 0.906 (48/1/9) | 0.739 (34/1/23) | 0.643 (27/0/30) | 0.643 (27/0/30) | 0.575 (23/0/34) |
| enclosure.form | 0.690 (30/0/27) | 0.519 (20/0/37) | 0.659 (28/0/29) | 0.690 (30/0/27) | 0.610 (25/0/32) | 0.945 (52/1/5) | 0.766 (36/1/21) | 0.926 (50/1/7) | 0.739 (34/1/23) | 0.659 (28/0/29) | 0.690 (30/0/27) | 0.610 (25/0/32) |
| enclosure.ip_rating | 0.719 (32/0/25) | 0.557 (22/0/35) | 0.659 (28/0/29) | 0.719 (32/0/25) | 0.610 (25/0/32) | 0.982 (56/1/1) | 0.779 (37/1/20) | 0.982 (56/1/1) | 0.779 (37/1/20) | 0.659 (28/0/29) | 0.719 (32/0/25) | 0.610 (25/0/32) |
| enclosure.sections | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 0.947 (18/0/2) | 0.788 (13/0/7) | 0.976 (20/1/0) | 0.000 (0/1/20) | 0.865 (16/1/4) | 0.000 (0/1/20) | 1.000 (20/0/0) | 0.947 (18/0/2) | 0.788 (13/0/7) |
| enclosure.width | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 0.947 (18/0/2) | 0.788 (13/0/7) | 0.930 (20/3/0) | 0.000 (0/3/20) | 0.821 (16/3/4) | 0.000 (0/3/20) | 1.000 (20/0/0) | 0.947 (18/0/2) | 0.788 (13/0/7) |
| incomer.device | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.545 (15/0/25) | 0.750 (39/25/1) | 0.469 (19/22/21) | 0.750 (39/25/1) | 0.469 (19/22/21) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.545 (15/0/25) |
| incomer.poles | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.545 (15/0/25) | 0.975 (39/1/1) | 0.633 (19/1/21) | 0.975 (39/1/1) | 0.633 (19/1/21) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.545 (15/0/25) |
| incomer.rating | 0.667 (30/0/30) | 0.500 (20/0/40) | 0.667 (30/0/30) | 0.667 (30/0/30) | 0.588 (25/0/35) | 0.992 (60/1/0) | 0.792 (40/1/20) | 0.992 (60/1/0) | 0.792 (40/1/20) | 0.667 (30/0/30) | 0.667 (30/0/30) | 0.588 (25/0/35) |
| metering.ct_ratio | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.431 (11/0/29) | 0.431 (11/0/29) | 0.400 (10/0/30) | 0.938 (38/3/2) | 0.600 (18/2/22) | 0.911 (36/3/4) | 0.576 (17/2/23) | 0.431 (11/0/29) | 0.431 (11/0/29) | 0.400 (10/0/30) |
| metering.meter | 0.824 (42/0/18) | 0.537 (22/0/38) | 0.537 (22/0/38) | 0.537 (22/0/38) | 0.537 (22/0/38) | 0.895 (51/3/9) | 0.660 (31/3/29) | 0.727 (36/3/24) | 0.500 (21/3/39) | 0.537 (22/0/38) | 0.537 (22/0/38) | 0.537 (22/0/38) |
| system.earthing | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.509 (14/1/26) | 0.976 (40/2/0) | 0.645 (20/2/20) | 0.963 (39/2/1) | 0.645 (20/2/20) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.509 (14/1/26) |
| system.fault_level | 0.630 (17/0/20) | 0.391 (9/0/28) | 0.577 (15/0/22) | 0.630 (17/0/20) | 0.458 (11/0/26) | 0.864 (35/9/2) | 0.644 (19/3/18) | 0.740 (27/9/10) | 0.621 (18/3/19) | 0.577 (15/0/22) | 0.630 (17/0/20) | 0.458 (11/0/26) |
| system.frequency | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.621 (18/0/22) | 0.473 (13/2/27) | 0.988 (40/1/0) | 0.656 (20/1/20) | 0.988 (40/1/0) | 0.656 (20/1/20) | 0.667 (20/0/20) | 0.621 (18/0/22) | 0.473 (13/2/27) |
| system.voltage | 0.667 (30/0/30) | 0.500 (20/0/40) | 0.667 (30/0/30) | 0.636 (28/0/32) | 0.588 (25/0/35) | 0.992 (60/1/0) | 0.792 (40/1/20) | 0.992 (60/1/0) | 0.792 (40/1/20) | 0.667 (30/0/30) | 0.636 (28/0/32) | 0.588 (25/0/35) |
| way.*.breaking_capacity | 0.696 (144/0/126) | 0.412 (70/0/200) | 0.650 (130/0/140) | 0.640 (127/0/143) | 0.457 (80/0/190) | 0.738 (200/72/70) | 0.551 (109/17/161) | 0.593 (144/72/126) | 0.528 (103/17/167) | 0.767 (168/0/102) | 0.808 (183/0/87) | 0.737 (158/1/112) |
| way.*.cable | 0.863 (252/0/80) | 0.411 (86/0/246) | 0.728 (191/2/141) | 0.728 (190/0/142) | 0.481 (105/0/227) | 0.954 (304/1/28) | 0.587 (138/0/194) | 0.863 (253/1/79) | 0.560 (129/0/203) | 0.728 (191/2/141) | 0.728 (190/0/142) | 0.481 (105/0/227) |
| way.*.cable_length | 1.000 (166/0/0) | n/a (0/0/166) | 0.740 (98/1/68) | 0.757 (101/0/65) | 0.176 (16/0/150) | 0.830 (166/68/0) | 0.000 (0/68/166) | 0.732 (135/68/31) | 0.000 (0/68/166) | 0.740 (98/1/68) | 0.757 (101/0/65) | 0.176 (16/0/150) |
| way.*.description | 0.769 (240/52/92) | 0.411 (86/0/246) | 0.645 (158/0/174) | 0.621 (150/1/182) | 0.447 (98/8/234) | 0.853 (287/54/45) | 0.532 (121/2/211) | 0.790 (218/2/114) | 0.402 (84/2/248) | 0.645 (158/0/174) | 0.621 (150/1/182) | 0.447 (98/8/234) |
| way.*.device | 0.723 (188/0/144) | 0.411 (86/0/246) | 0.688 (174/0/158) | 0.675 (169/0/163) | 0.546 (125/1/207) | 0.891 (275/10/57) | 0.546 (128/9/204) | 0.866 (261/10/71) | 0.521 (120/9/212) | 0.765 (208/4/124) | 0.759 (210/11/122) | 0.740 (204/15/128) |
| way.*.poles | 0.695 (177/0/155) | 0.411 (86/0/246) | 0.648 (159/0/173) | 0.630 (153/1/179) | 0.513 (115/1/217) | 0.791 (261/67/71) | 0.605 (144/0/188) | 0.659 (196/67/136) | 0.581 (136/0/196) | 0.764 (205/0/127) | 0.780 (213/1/119) | 0.735 (198/9/134) |
| way.*.rating | 0.693 (176/0/156) | 0.411 (86/0/246) | 0.656 (162/0/170) | 0.634 (155/2/177) | 0.457 (99/2/233) | 0.678 (235/126/97) | 0.588 (140/4/192) | 0.476 (143/126/189) | 0.564 (132/4/200) | 0.773 (209/0/123) | 0.771 (210/3/122) | 0.684 (182/18/150) |
| ways.count | 0.835 (43/0/17) | 0.588 (25/0/35) | 0.699 (36/7/24) | 0.621 (32/11/28) | 0.611 (29/6/31) | 0.975 (58/1/2) | 0.792 (40/1/20) | 0.780 (39/1/21) | 0.768 (38/1/22) | 0.699 (36/7/24) | 0.621 (32/11/28) | 0.611 (29/6/31) |

### Vision model alone (drawing ways, recorded)

Each sheet of the version is one picture sent to the vision model (recorded on Colab). A sheet without a recording is **not read**: it is left out of these scores, never counted as an empty reading or an error. Scores are on the drawing's way values (device, rating, poles, breaking capacity) of the sheets that were read. "All" is against every value the key gives for those sheets; the model is asked only for ways, so its recall is low by design. "Empty ways" are ways the model listed with nothing read.

| Version | Sheets read | Not read | Device F1 | Rating F1 | Poles F1 | Breaking F1 | All (P, R, F1) | Empty ways |
|---|---|---|---|---|---|---|---|---|
| clean | 36 of 40 | F12 schematic.pdf sheet 1, F15 schematic.pdf sheet 1, F19 schematic.pdf sheet 1, F20 schematic.pdf sheet 1 | 0.860 | 0.883 | 0.882 | 0.860 | 0.986, 0.331, **0.496** (353/5/712) | 166 |
| scanned | 36 of 40 | F02 schematic_sheet1_scanned.png sheet 1, F12 schematic_sheet1_scanned.png sheet 1, F15 schematic_sheet1_scanned.png sheet 1, F19 schematic_sheet1_scanned.png sheet 1 | 0.834 | 0.907 | 0.927 | 0.935 | 0.957, 0.359, **0.522** (378/17/675) | 156 |
| photo | 38 of 40 | F12 schematic_sheet1_photo.png sheet 1, F15 schematic_sheet1_photo.png sheet 1 | 0.823 | 0.741 | 0.794 | 0.836 | 0.904, 0.307, **0.459** (384/41/865) | 166 |

### Symbol detector (template; breaker classes, IoU at least 0.5)

| Version | TP | FP | FN | P | R | F1 | acb found | s/sheet |
|---|---|---|---|---|---|---|---|---|
| clean | 165 | 21 | 21 | 0.887 | 0.887 | 0.887 | 0 of 20 | 8.88 |
| scanned | 166 | 20 | 20 | 0.892 | 0.892 | 0.892 | 0 of 20 | 8.53 |
| photo | 161 | 16 | 25 | 0.910 | 0.866 | 0.887 | 3 of 20 | 3.17 |

### Confidence calibration (Stage 6), rules with the DXF

| Level | Values | Right | Share right |
|---|---|---|---|
| high | 1678 | 1678 | 1.000 |
| medium | 2 | 2 | 1.000 |
| low | 1 | 1 | 1.000 |
| conflict | 125 | 73 | 0.584 |

### Confidence calibration, rules + OCR on the scanned drawing (no DXF)

| Level | Values | Right | Share right |
|---|---|---|---|
| high | 686 | 686 | 1.000 |
| medium | 689 | 688 | 0.999 |
| low | 13 | 9 | 0.692 |
| conflict | 35 | 25 | 0.714 |

### Cross-checks with the Stage 6 gate, rules with the DXF

Planted conflicts found: 8 of 10; false flags: 1. Planted missing values listed: 5 of 5.

### Error analysis

**Rules, with the DXF**

| Field group | Wrong | Missed | Examples |
|---|---|---|---|
| way.*.rating | 0 | 156 | missed 160 A on specification p5; missed 200 A on specification p5 |
| way.*.poles | 0 | 155 | missed 3 on specification p5; missed 3 on specification p5 |
| way.*.description | 52 | 92 | read M.C.C.B. 160 A 3-POLE Icu=36kA on schematic p1 (rules); key: Sprinkler pump; read 200 A MCCB 3P Icu=36kA on schematic p1 (rules); key: Small power DB-L2; missed Sprinkler pump on specification p5; missed Small power DB-L2 on specification p5 |
| way.*.device | 0 | 144 | missed mccb on specification p5; missed mccb on specification p5 |
| way.*.breaking_capacity | 0 | 126 | missed 36 kA on specification p5; missed 36 kA on specification p5 |
| way.*.cable | 0 | 80 | missed 4C 70 mm2 SWA on specification p5; missed 4C 95 mm2 SWA on specification p5 |

**Rules + OCR, scanned drawing, no DXF**

| Field group | Wrong | Missed | Examples |
|---|---|---|---|
| way.*.description | 1 | 182 | read AHU1 on schematic p1 (ocr); key: AHU 1; missed Sprinkler pump on specification p5; missed Small power DB-L2 on specification p5 |
| way.*.poles | 1 | 179 | read 3 on schematic p1 (ocr); key: 4; missed 3 on specification p5; missed 3 on specification p5 |
| way.*.rating | 2 | 177 | read 630 A on schematic p1 (ocr); key: 250 A; read 100 A on schematic p1 (ocr); key: 250 A; missed 160 A on specification p5; missed 200 A on specification p5 |
| way.*.device | 0 | 163 | missed mccb on specification p5; missed mccb on specification p5 |
| way.*.breaking_capacity | 0 | 143 | missed 36 kA on specification p5; missed 36 kA on specification p5 |
| way.*.cable | 0 | 142 | missed 4C 70 mm2 SWA on specification p5; missed 4C 95 mm2 SWA on specification p5 |

**Rules + model (v2, strict), no DXF**

| Field group | Wrong | Missed | Examples |
|---|---|---|---|
| way.*.cable_length | 68 | 166 | read m on specification p5 (llm); key: nothing on that page; read m on specification p5 (llm); key: nothing on that page; missed 74 m on schematic p1; missed 74 m on schematic p1 |
| way.*.device | 9 | 204 | read mcb on specification p5 (llm); key: mccb; read switch_disconnector on specification p5 (llm); key: mccb; missed switch_disconnector on schematic p1; missed switch_disconnector on schematic p1 |
| way.*.description | 2 | 211 | read DB-L1 on specification p4 (llm); key: nothing on that page; read AHU on specification p5 (llm); key: nothing on that page; missed Fire pump on schematic p1; missed Sprinkler pump on schematic p1 |
| way.*.rating | 4 | 192 | read In=400A A on specification p8 (llm); key: 400 A; read In=400A A on specification p8 (llm); key: 400 A; missed 250 A on schematic p1; missed 125 A on schematic p1 |
| way.*.cable | 0 | 194 | missed 4C 120 mm2 SWA on schematic p1; missed 4C 50 mm2 SWA on schematic p1 |
| way.*.poles | 0 | 188 | missed 4 on schematic p1; missed 4 on schematic p1 |

### Question box search (Stage 9)

One question per field the specification or letter states ("What is the fault level?"). Found at 1: the quoted passage holds the key's source text on the key's page; found in 3: one of the three best does. A refusal is **right** when the best passage did not hold the answer (answering would have quoted the wrong passage), wrong when it did and only the score was under the threshold. Nothing was tuned on these numbers.

| Embedder | Questions | Found at 1 | Found in 3 | Refused | Right refusals |
|---|---|---|---|---|---|
| words (threshold 0.2) | 236 | 0.593 | 0.767 | 15 | 5 |
| mxbai-embed-large (threshold 0.5) | 236 | 0.708 | 0.784 | 29 | 20 |

## Baseline: test set, not held out

20 projects (T01 to T20); 26 min of reading on the laptop.

### Field values (all fields, micro-averaged)

| Method | Drawing | P, R, **F1** (TP/FP/FN) |
|---|---|---|
| Rules | DXF | 1.000, 1.000, **1.000** (3105/0/0) |
| Rules | none (drawing not read) | 1.000, 0.486, **0.654** (1508/0/1597) |
| Rules + OCR | clean, no DXF | 0.996, 0.903, **0.948** (2805/10/300) |
| Rules + OCR | scanned, no DXF | 0.994, 0.880, **0.934** (2733/16/372) |
| Rules + OCR | photo, no DXF | 0.975, 0.699, **0.814** (2170/55/935) |
| Rules + model (v2, strict) | DXF | 0.893, 1.000, **0.944** (3105/371/0) |
| Rules + model (v2, strict) | none | 0.950, 0.486, **0.643** (1508/79/1597) |
| Model alone (v2, strict) | DXF | 0.856, 0.713, **0.778** (2214/371/891) |
| Model alone (v2, strict) | none | 0.940, 0.400, **0.561** (1241/79/1864) |
| Rules + OCR + vision | clean, no DXF | waiting for Colab recordings |
| Rules + OCR + vision | scanned, no DXF | waiting for Colab recordings |
| Rules + OCR + vision | photo, no DXF | waiting for Colab recordings |

### Field values per field group: F1 (TP/FP/FN)

| Field group | Rules, DXF | Rules, no drawing | Rules + OCR, clean | Rules + OCR, scanned | Rules + OCR, photo | Rules + model, DXF | Rules + model, none | Model alone, DXF | Model alone, none |
|---|---|---|---|---|---|---|---|---|---|
| busbar.rating | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 1.000 (40/0/0) | 0.974 (38/0/2) | 1.000 (40/0/0) | 0.667 (20/0/20) | 0.987 (39/0/1) | 0.644 (19/0/21) |
| enclosure.cable_entry | 1.000 (57/0/0) | 0.800 (38/0/19) | 1.000 (57/0/0) | 1.000 (57/0/0) | 0.935 (50/0/7) | 1.000 (57/0/0) | 0.800 (38/0/19) | 0.973 (54/0/3) | 0.774 (36/0/21) |
| enclosure.form | 1.000 (57/0/0) | 0.800 (38/0/19) | 0.991 (56/0/1) | 1.000 (57/0/0) | 0.925 (49/0/8) | 0.974 (57/3/0) | 0.776 (38/3/19) | 0.889 (48/3/9) | 0.667 (30/3/27) |
| enclosure.ip_rating | 1.000 (57/0/0) | 0.800 (38/0/19) | 0.973 (54/0/3) | 1.000 (57/0/0) | 0.893 (46/0/11) | 1.000 (57/0/0) | 0.800 (38/0/19) | 0.973 (54/0/3) | 0.774 (36/0/21) |
| enclosure.sections | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 1.000 (20/0/0) | 0.857 (15/0/5) | 1.000 (20/0/0) | n/a (0/0/20) | 0.824 (14/0/6) | n/a (0/0/20) |
| enclosure.width | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 1.000 (20/0/0) | 0.857 (15/0/5) | 0.952 (20/2/0) | 0.000 (0/2/20) | 0.778 (14/2/6) | 0.000 (0/2/20) |
| incomer.device | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 0.987 (39/0/1) | 0.961 (37/0/3) | 0.777 (40/23/0) | 0.500 (20/20/20) | 0.765 (39/23/1) | 0.481 (19/20/21) |
| incomer.poles | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 0.987 (39/0/1) | 0.961 (37/0/3) | 1.000 (40/0/0) | 0.667 (20/0/20) | 0.987 (39/0/1) | 0.644 (19/0/21) |
| incomer.rating | 1.000 (60/0/0) | 0.800 (40/0/20) | 1.000 (60/0/0) | 0.992 (59/0/1) | 0.974 (57/0/3) | 1.000 (60/0/0) | 0.800 (40/0/20) | 0.992 (59/0/1) | 0.788 (39/0/21) |
| metering.ct_ratio | 1.000 (40/0/0) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.710 (22/0/18) | 0.930 (40/6/0) | 0.656 (20/1/20) | 0.850 (34/6/6) | 0.633 (19/1/21) |
| metering.meter | 1.000 (60/0/0) | 0.800 (40/0/20) | 0.800 (40/0/20) | 0.800 (40/0/20) | 0.800 (40/0/20) | 1.000 (60/0/0) | 0.800 (40/0/20) | 0.763 (37/0/23) | 0.571 (24/0/36) |
| system.earthing | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 1.000 (40/0/0) | 0.873 (31/0/9) | 0.976 (40/2/0) | 0.645 (20/2/20) | 0.909 (35/2/5) | 0.645 (20/2/20) |
| system.fault_level | 1.000 (37/0/0) | 0.679 (19/0/18) | 0.958 (34/0/3) | 1.000 (37/0/0) | 0.943 (33/0/4) | 0.914 (37/7/0) | 0.655 (19/2/18) | 0.687 (23/7/14) | 0.632 (18/2/19) |
| system.frequency | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 0.947 (36/0/4) | 0.947 (36/0/4) | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 0.667 (20/0/20) |
| system.voltage | 1.000 (60/0/0) | 0.800 (40/0/20) | 1.000 (60/0/0) | 0.966 (56/0/4) | 0.966 (56/0/4) | 0.992 (60/1/0) | 0.792 (40/1/20) | 0.992 (60/1/0) | 0.792 (40/1/20) |
| way.*.breaking_capacity | 1.000 (309/0/0) | 0.668 (155/0/154) | 0.970 (291/0/18) | 0.958 (284/0/25) | 0.823 (218/3/91) | 0.862 (309/99/0) | 0.644 (155/17/154) | 0.576 (165/99/144) | 0.576 (132/17/177) |
| way.*.cable | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.888 (304/5/72) | 0.895 (307/3/69) | 0.767 (234/0/142) | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.930 (327/0/49) | 0.594 (159/0/217) |
| way.*.cable_length | 1.000 (188/0/0) | n/a (0/0/188) | 0.759 (115/0/73) | 0.747 (112/0/76) | 0.349 (40/1/148) | 0.917 (188/34/0) | 0.000 (0/26/188) | 0.810 (151/34/37) | 0.000 (0/26/188) |
| way.*.description | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.970 (354/0/22) | 0.949 (341/2/35) | 0.766 (250/27/126) | 0.999 (376/1/0) | 0.665 (188/1/188) | 0.809 (256/1/120) | 0.389 (91/1/285) |
| way.*.device | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.971 (355/0/21) | 0.951 (341/0/35) | 0.860 (285/2/91) | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.866 (287/0/89) | 0.597 (160/0/216) |
| way.*.poles | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.971 (355/0/21) | 0.951 (341/0/35) | 0.835 (271/2/105) | 0.910 (376/74/0) | 0.667 (188/0/188) | 0.665 (224/74/152) | 0.597 (160/0/216) |
| way.*.rating | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.971 (355/0/21) | 0.951 (341/0/35) | 0.829 (269/4/107) | 0.867 (376/115/0) | 0.667 (188/0/188) | 0.532 (178/115/198) | 0.605 (163/0/213) |
| ways.count | 1.000 (60/0/0) | 0.800 (40/0/20) | 0.917 (55/5/5) | 0.817 (49/11/11) | 0.701 (41/16/19) | 0.968 (60/4/0) | 0.769 (40/4/20) | 0.733 (37/4/23) | 0.733 (37/4/23) |

### Vision model alone (drawing ways, recorded)

Waiting for Colab recordings of the drawing pictures (`docs/colab-all.md`, Cell 8).

### Symbol detector (template; breaker classes, IoU at least 0.5)

| Version | TP | FP | FN | P | R | F1 | acb found | s/sheet |
|---|---|---|---|---|---|---|---|---|
| clean | 185 | 20 | 23 | 0.902 | 0.889 | 0.896 | 0 of 20 | 8.72 |
| scanned | 189 | 19 | 19 | 0.909 | 0.909 | 0.909 | 1 of 20 | 9.03 |
| photo | 174 | 17 | 34 | 0.911 | 0.837 | 0.872 | 3 of 20 | 3.33 |

### Confidence calibration (Stage 6), rules with the DXF

| Level | Values | Right | Share right |
|---|---|---|---|
| high | 3076 | 3076 | 1.000 |
| low | 1 | 1 | 1.000 |
| conflict | 27 | 27 | 1.000 |

### Confidence calibration, rules + OCR on the scanned drawing (no DXF)

| Level | Values | Right | Share right |
|---|---|---|---|
| high | 1471 | 1471 | 1.000 |
| medium | 1217 | 1216 | 0.999 |
| low | 3 | 3 | 1.000 |
| conflict | 57 | 42 | 0.737 |

### Cross-checks with the Stage 6 gate, rules with the DXF

Planted conflicts found: 10 of 10; false flags: 1. Planted missing values listed: 4 of 5.

### Error analysis

**Rules, with the DXF**

No wrong or missed values.

**Rules + OCR, scanned drawing, no DXF**

| Field group | Wrong | Missed | Examples |
|---|---|---|---|
| way.*.cable_length | 0 | 76 | missed 50 m on schematic p1; missed 24 m on schematic p1 |
| way.*.cable | 3 | 69 | read 4C 185 mm2 SWA on schematic p1 (ocr); key: 2x 4C 185 mm2 SWA; read 4C 185 mm2 SWA on schematic p1 (ocr); key: 2x 4C 185 mm2 SWA; missed 4C 4 mm2 SWA on schematic p1; missed 4C 4 mm2 SWA on schematic p1 |
| way.*.description | 2 | 35 | read Sw-DISC 125A 4P on schematic p1 (ocr); key: AHU 1; read SwW-DISC 800A 4P on schematic p1 (ocr); key: Small power DB-L2; missed Kitchen DB on schematic p1; missed Lift motor room on schematic p1 |
| way.*.device | 0 | 35 | missed mcb on schematic p1; missed mccb on schematic p1 |
| way.*.rating | 0 | 35 | missed 20 A on schematic p1; missed 630 A on schematic p1 |
| way.*.poles | 0 | 35 | missed 3 on schematic p1; missed 4 on schematic p1 |

**Rules + model (v2, strict), no DXF**

| Field group | Wrong | Missed | Examples |
|---|---|---|---|
| way.*.cable_length | 26 | 188 | read TBC m on specification p4 (llm); key: nothing on that page; read TBC m on specification p4 (llm); key: nothing on that page; missed 50 m on schematic p1; missed 24 m on schematic p1 |
| way.*.description | 1 | 188 | read DB-L1 on specification p6 (llm); key: nothing on that page; missed Small power DB-L1 on schematic p1; missed Chiller 2 on schematic p1 |
| way.*.device | 0 | 188 | missed mccb on schematic p1; missed mccb on schematic p1 |
| way.*.rating | 0 | 188 | missed 630 A on schematic p1; missed 400 A on schematic p1 |
| way.*.poles | 0 | 188 | missed 4 on schematic p1; missed 4 on schematic p1 |
| way.*.cable | 0 | 188 | missed 2x 4C 185 mm2 SWA on schematic p1; missed 2x 4C 185 mm2 SWA on schematic p1 |

