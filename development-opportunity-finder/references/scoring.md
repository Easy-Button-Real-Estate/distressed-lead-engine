# How the Land Score works

`scripts/score_parcels.py` scores every parcel from 0 to 1 on each factor in the buy box, multiplies by the factor's weight (points out of 100), and adds it up.

## Factors

| Factor | Data it uses | Full points | Zero points |
|---|---|---|---|
| Access | `road_frontage_ft`, `landlocked` | frontage >= `min_frontage_ft` | land-locked (also excluded unless `require_access: false`) |
| Highway access | nearest interchange / on-ramp (or major highway x1.5) | <= `distances.highway.ideal` mi | >= `limit` mi |
| Power | nearest substation and transmission line, blended by `power_mix` | <= ideal mi | >= limit mi |
| Rail | nearest mainline rail | <= ideal mi | >= limit mi |
| Water / sewer | `public_water`, `public_sewer` yes/no (data center can fall back to distance to a water/wastewater plant as a weak proxy) | both yes | both no |
| Size | `acres` | inside `ideal_min`-`ideal_max` | outside `min`-`max` (excluded) |
| Zoning / use | `zoning` + `land_use` text vs `zoning_keywords` | keyword match | `zoning_exclude` match (excluded). Vacant / ag land gets 0.55 and a "may need rezoning" flag |
| FEMA flood | `flood_pct` or `fema_zone` | 0% | >= 50% (excluded above `max_flood_pct`) |
| Wetlands | `wetlands_pct` | 0% | >= 40% |
| Slope / buildable | `buildable_pct` (or `slope_pct`) | >= 90% buildable |  -  |
| Valuation | asking price, else county land/market value, per acre vs the comp anchor | <= 0.6x anchor | >= 1.4x anchor |

## Unknown data stays unknown

If a parcel has no data for a factor, that factor is left out. It does not get a neutral or average score. The Land Score is computed on the factors that are known, and **data confidence** = share of buy-box weight that had data.

To keep data-thin parcels from floating to the top:

```
rank_score = land_score x (0.6 + 0.4 x confidence)
priority   = (1 - m) x rank_score + m x motivation      (m = --motivation-weight, default 0.2)
```

Tiers: **A - research first** (priority >= 72 and flood, wetlands and slope all checked; research before any
outreach), **B - work next** (>= 58, or >= 72 with a constraint still unchecked: "held out of tier A until
checked"), **C - park**. Parcels under 60% confidence get a "thin data" flag.

## Owner motivation (0-100)

Only from fields in the file: years since last sale (2 pts/yr, max 30), out-of-state owner (+25), or out-of-county owner (+15 from a mailing-county column, or +12 when the mailing ZIP is not one of the county's parcel ZIPs; vacant land has no "owner-occupied" so absentee is not used), no mortgage on record (+15), tax delinquent (+20), estate / heirs / trust / et al in the owner name (+10). Government owners (owner type or names like "State of", "County of", "United States") are excluded unless `--include-public`.

## Expected value

Blended $/acre: comp median (60%) + the parcel's own county land/market value per acre (40%). Comps go through an IQR outlier filter. The range is +/-5% when there are 3+ clean comps, otherwise +/-10%. With no comps, the anchor is the median county value per acre in the file (needs 5+ rows), and the range is +/-10%. This is a screening number, not an appraisal.

## Hard gates (excluded, never ranked)

Size outside min/max, land-locked (when access is required), flood above `max_flood_pct`, excluded zoning, asking price above `max_price`, substation farther than `max_substation_mi`, public owner, no acreage.
