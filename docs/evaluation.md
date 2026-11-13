# Evaluation

Written by `python -m backend.evaluation_report`. Every number below was run on the laptop; a row that needs model recordings says "waiting for Colab recordings". Field cells are P, R, **F1** (TP/FP/FN); a value counts when its field, file, page, value and unit match the answer key (docs/stage-2.md).

## Fresh set, not used for tuning (set hash c1488dbdeec22ed5)

20 projects (F01 to F20); 23 min of reading on the laptop.

### Field values (all fields, micro-averaged)

| Method | Drawing | P, R, **F1** (TP/FP/FN) |
|---|---|---|
| Rules | DXF | 0.971, 0.621, **0.758** (1754/52/1070) |
| Rules | none (drawing not read) | 1.000, 0.254, **0.405** (716/0/2108) |
| Rules + OCR | clean, no DXF | 0.993, 0.510, **0.674** (1439/10/1385) |
| Rules + OCR | scanned, no DXF | 0.989, 0.499, **0.663** (1408/15/1416) |
| Rules + OCR | photo, no DXF | 0.978, 0.329, **0.493** (930/21/1894) |
| Rules + model | DXF | waiting for Colab recordings |
| Rules + model | none | waiting for Colab recordings |

### Field values per field group: F1 (TP/FP/FN)

| Field group | Rules, DXF | Rules, no drawing | Rules + OCR, clean | Rules + OCR, scanned | Rules + OCR, photo |
|---|---|---|---|---|---|
| busbar.rating | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.519 (14/0/26) |
| enclosure.cable_entry | 0.643 (27/0/30) | 0.480 (18/0/39) | 0.643 (27/0/30) | 0.643 (27/0/30) | 0.575 (23/0/34) |
| enclosure.form | 0.690 (30/0/27) | 0.519 (20/0/37) | 0.659 (28/0/29) | 0.690 (30/0/27) | 0.610 (25/0/32) |
| enclosure.ip_rating | 0.719 (32/0/25) | 0.557 (22/0/35) | 0.659 (28/0/29) | 0.719 (32/0/25) | 0.610 (25/0/32) |
| enclosure.sections | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 0.947 (18/0/2) | 0.788 (13/0/7) |
| enclosure.width | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 0.947 (18/0/2) | 0.788 (13/0/7) |
| incomer.device | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.545 (15/0/25) |
| incomer.poles | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.545 (15/0/25) |
| incomer.rating | 0.667 (30/0/30) | 0.500 (20/0/40) | 0.667 (30/0/30) | 0.667 (30/0/30) | 0.588 (25/0/35) |
| metering.ct_ratio | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.431 (11/0/29) | 0.431 (11/0/29) | 0.400 (10/0/30) |
| metering.meter | 0.824 (42/0/18) | 0.537 (22/0/38) | 0.537 (22/0/38) | 0.537 (22/0/38) | 0.537 (22/0/38) |
| system.earthing | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.509 (14/1/26) |
| system.fault_level | 0.630 (17/0/20) | 0.391 (9/0/28) | 0.577 (15/0/22) | 0.630 (17/0/20) | 0.458 (11/0/26) |
| system.frequency | 0.667 (20/0/20) | 0.400 (10/0/30) | 0.667 (20/0/20) | 0.621 (18/0/22) | 0.473 (13/2/27) |
| system.voltage | 0.667 (30/0/30) | 0.500 (20/0/40) | 0.667 (30/0/30) | 0.636 (28/0/32) | 0.588 (25/0/35) |
| way.*.breaking_capacity | 0.696 (144/0/126) | 0.412 (70/0/200) | 0.650 (130/0/140) | 0.640 (127/0/143) | 0.457 (80/0/190) |
| way.*.cable | 0.863 (252/0/80) | 0.411 (86/0/246) | 0.728 (191/2/141) | 0.728 (190/0/142) | 0.481 (105/0/227) |
| way.*.cable_length | 1.000 (166/0/0) | n/a (0/0/166) | 0.740 (98/1/68) | 0.757 (101/0/65) | 0.176 (16/0/150) |
| way.*.description | 0.769 (240/52/92) | 0.411 (86/0/246) | 0.645 (158/0/174) | 0.621 (150/1/182) | 0.447 (98/8/234) |
| way.*.device | 0.723 (188/0/144) | 0.411 (86/0/246) | 0.688 (174/0/158) | 0.675 (169/0/163) | 0.546 (125/1/207) |
| way.*.poles | 0.695 (177/0/155) | 0.411 (86/0/246) | 0.648 (159/0/173) | 0.630 (153/1/179) | 0.513 (115/1/217) |
| way.*.rating | 0.693 (176/0/156) | 0.411 (86/0/246) | 0.656 (162/0/170) | 0.634 (155/2/177) | 0.457 (99/2/233) |
| ways.count | 0.835 (43/0/17) | 0.588 (25/0/35) | 0.699 (36/7/24) | 0.621 (32/11/28) | 0.611 (29/6/31) |

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

## Baseline: test set, not held out

20 projects (T01 to T20); 25 min of reading on the laptop.

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

### Field values per field group: F1 (TP/FP/FN)

| Field group | Rules, DXF | Rules, no drawing | Rules + OCR, clean | Rules + OCR, scanned | Rules + OCR, photo | Rules + model, DXF | Rules + model, none |
|---|---|---|---|---|---|---|---|
| busbar.rating | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 1.000 (40/0/0) | 0.974 (38/0/2) | 1.000 (40/0/0) | 0.667 (20/0/20) |
| enclosure.cable_entry | 1.000 (57/0/0) | 0.800 (38/0/19) | 1.000 (57/0/0) | 1.000 (57/0/0) | 0.935 (50/0/7) | 1.000 (57/0/0) | 0.800 (38/0/19) |
| enclosure.form | 1.000 (57/0/0) | 0.800 (38/0/19) | 0.991 (56/0/1) | 1.000 (57/0/0) | 0.925 (49/0/8) | 0.974 (57/3/0) | 0.776 (38/3/19) |
| enclosure.ip_rating | 1.000 (57/0/0) | 0.800 (38/0/19) | 0.973 (54/0/3) | 1.000 (57/0/0) | 0.893 (46/0/11) | 1.000 (57/0/0) | 0.800 (38/0/19) |
| enclosure.sections | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 1.000 (20/0/0) | 0.857 (15/0/5) | 1.000 (20/0/0) | n/a (0/0/20) |
| enclosure.width | 1.000 (20/0/0) | n/a (0/0/20) | 1.000 (20/0/0) | 1.000 (20/0/0) | 0.857 (15/0/5) | 0.952 (20/2/0) | 0.000 (0/2/20) |
| incomer.device | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 0.987 (39/0/1) | 0.961 (37/0/3) | 0.777 (40/23/0) | 0.500 (20/20/20) |
| incomer.poles | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 0.987 (39/0/1) | 0.961 (37/0/3) | 1.000 (40/0/0) | 0.667 (20/0/20) |
| incomer.rating | 1.000 (60/0/0) | 0.800 (40/0/20) | 1.000 (60/0/0) | 0.992 (59/0/1) | 0.974 (57/0/3) | 1.000 (60/0/0) | 0.800 (40/0/20) |
| metering.ct_ratio | 1.000 (40/0/0) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.667 (20/0/20) | 0.710 (22/0/18) | 0.930 (40/6/0) | 0.656 (20/1/20) |
| metering.meter | 1.000 (60/0/0) | 0.800 (40/0/20) | 0.800 (40/0/20) | 0.800 (40/0/20) | 0.800 (40/0/20) | 1.000 (60/0/0) | 0.800 (40/0/20) |
| system.earthing | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 1.000 (40/0/0) | 0.873 (31/0/9) | 0.976 (40/2/0) | 0.645 (20/2/20) |
| system.fault_level | 1.000 (37/0/0) | 0.679 (19/0/18) | 0.958 (34/0/3) | 1.000 (37/0/0) | 0.943 (33/0/4) | 0.914 (37/7/0) | 0.655 (19/2/18) |
| system.frequency | 1.000 (40/0/0) | 0.667 (20/0/20) | 1.000 (40/0/0) | 0.947 (36/0/4) | 0.947 (36/0/4) | 1.000 (40/0/0) | 0.667 (20/0/20) |
| system.voltage | 1.000 (60/0/0) | 0.800 (40/0/20) | 1.000 (60/0/0) | 0.966 (56/0/4) | 0.966 (56/0/4) | 0.992 (60/1/0) | 0.792 (40/1/20) |
| way.*.breaking_capacity | 1.000 (309/0/0) | 0.668 (155/0/154) | 0.970 (291/0/18) | 0.958 (284/0/25) | 0.823 (218/3/91) | 0.862 (309/99/0) | 0.644 (155/17/154) |
| way.*.cable | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.888 (304/5/72) | 0.895 (307/3/69) | 0.767 (234/0/142) | 1.000 (376/0/0) | 0.667 (188/0/188) |
| way.*.cable_length | 1.000 (188/0/0) | n/a (0/0/188) | 0.759 (115/0/73) | 0.747 (112/0/76) | 0.349 (40/1/148) | 0.917 (188/34/0) | 0.000 (0/26/188) |
| way.*.description | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.970 (354/0/22) | 0.949 (341/2/35) | 0.766 (250/27/126) | 0.999 (376/1/0) | 0.665 (188/1/188) |
| way.*.device | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.971 (355/0/21) | 0.951 (341/0/35) | 0.860 (285/2/91) | 1.000 (376/0/0) | 0.667 (188/0/188) |
| way.*.poles | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.971 (355/0/21) | 0.951 (341/0/35) | 0.835 (271/2/105) | 0.910 (376/74/0) | 0.667 (188/0/188) |
| way.*.rating | 1.000 (376/0/0) | 0.667 (188/0/188) | 0.971 (355/0/21) | 0.951 (341/0/35) | 0.829 (269/4/107) | 0.867 (376/115/0) | 0.667 (188/0/188) |
| ways.count | 1.000 (60/0/0) | 0.800 (40/0/20) | 0.917 (55/5/5) | 0.817 (49/11/11) | 0.701 (41/16/19) | 0.968 (60/4/0) | 0.769 (40/4/20) |

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

