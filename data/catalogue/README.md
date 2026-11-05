# Parts catalogue (invented)

`catalogue.csv` is an invented parts catalogue for low-voltage switchboards. Every code, description, price and labour figure is made up for this project; none comes from a real catalogue or price list. The same rows are produced by `data_generator/catalogue.py` (`build_catalogue()`), and a test checks that the committed file matches it byte for byte. To rewrite the file:

```powershell
.venv\Scripts\python.exe -m data_generator catalogue
```

The enquiry generator designs boards only from parts in this catalogue, so every line of a correct estimate has a catalogue code. Prices in any estimate come only from this table.

## Data dictionary

| Column | Type | Unit | Meaning |
|---|---|---|---|
| `code` | text | | Part code, `PRT-` and four digits. The first two digits are the family (`01` ACB, `02` MCCB, `03` MCB, `04` switch-disconnector, `05` current transformer, `06` meter, `07` busbar, `08` enclosure section, `09` form kit, `10` cable gland) |
| `category` | text | | One of `acb`, `mccb`, `mcb`, `switch_disconnector`, `current_transformer`, `meter`, `busbar`, `enclosure_section`, `form_kit`, `cable_gland` |
| `description` | text | | Plain description |
| `rating_a` | integer | A | Rated current. For current transformers, the primary current. Empty when it does not apply |
| `poles` | integer | | Number of poles (3 or 4). Busbars are 4 (TP&N) |
| `breaking_ka` | integer | kA | Rated ultimate short-circuit breaking capacity (Icu) of a breaker. Empty for parts that do not break fault current |
| `ip_rating` | text | | Degree of protection of an enclosure section, `IP31`, `IP42` or `IP54` |
| `width_mm` | integer | mm | Width of an enclosure section (all sections are 2200 mm high) |
| `size` | text | | Family-specific size: CT ratio (`1600/5`), meter type (`MFM` or `kWh`), form of separation (`3b`, `4a`, `4b`) or gland thread (`M20` to `M63`) |
| `unit` | text | | Unit of sale: `each`, or `m` for busbars (priced per metre of board width) |
| `unit_price_gbp` | decimal | GBP | Invented unit price, two decimals, excluding VAT |
| `labour_hours` | decimal | h | Invented fitting time per unit |

## Families

| Family | Parts | Options |
|---|---|---|
| ACB (incomers) | 8 | 800 to 2500 A, 4-pole; 1250 and 1600 A also 3-pole; all 50 kA, withdrawable |
| MCCB | 17 | 100 to 630 A, 3- and 4-pole, 36 kA; 250, 400 and 630 A 4-pole also 50 kA |
| MCB | 5 | 16 to 63 A, 3-pole, 10 kA, type C (used only where cascading is allowed) |
| Switch-disconnector | 5 | 125 to 800 A, 4-pole |
| Current transformer | 6 | 800/5 to 2500/5 A |
| Meter | 2 | Multifunction (MFM), kWh |
| Busbar | 6 | 800 to 2500 A TP&N, per metre |
| Enclosure section | 6 | Incomer W800 and outgoing W600, each in IP31, IP42, IP54 |
| Form kit | 3 | Form 3b, 4a, 4b, one per section (Form 2b needs no kit) |
| Cable gland | 6 | M20 to M63, brass, for armoured cable |

Total: 64 parts.

## Matching rules used by the generator

`match_part()` in `data_generator/catalogue.py` returns the one part that fits, or raises; it never guesses.

- Breakers: same rating and poles; breaking capacity at least the fault level, lowest that fits.
- MCBs: same rating and poles; breaking capacity is not checked (cascade protection).
- Current transformers: primary equal to the incomer rating; three per board.
- Busbar: rating equal to the busbar rating; quantity is the board width in metres.
- Enclosure sections: one incomer section, plus one outgoing section per four mounting units (a way above 400 A takes two units).
- Form kits: one per section when the form is 3b, 4a or 4b.
- Glands: by cable size (see `CABLE_BY_RATING` in `data_generator/design.py`); two per way above 400 A.
