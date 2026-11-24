"""Trade and industrial policy for the battery horizon (horizon.py): US tariffs by good, exporter and year, the EU's
on China, and the US Section 45X production credit with its foreign-entity rules. PRELIMINARY.

Sources: data/battery_horizon/policy/ (tariffs.csv, ids R; credits.csv, ids C; one row per rate with its official
text: Federal Register notices, HTSUS chapter 99, executive orders, 26 U.S.C. 45X as amended by Public Law 119-21,
Treasury's final regulations T.D. 10010). Status as of 2026-11-24.

Tariffs are ad valorem on the traded good's value (build()'s `tariffs`), each year's rate the rates in force
weighted by the days they were in force. After the last rate's date the rates in force on 2026-11-24 are held to
2040 (an assumption; a scenario changes them). Layers, each where it applies:
  MFN            US column 1 general rates (R0-R22) on imports from China and the rest of the world; the allies are
                 taken at zero (most US imports from them enter under free-trade agreements: Korea, Australia,
                 Canada; ours)
  Section 301    on China (R24-R41): 25% on lithium chemicals, sulphates, cathode material, synthetic graphite and
                 nickel ore since 2019; cobalt ore from 2024-09-27; EV cells 25% from 2024-09-27 and other
                 lithium-ion cells from 2026-01-01 (7.5% before); natural graphite 25% from 2026-01-01; lithium ore
                 none; black mass 7.5%. The 2024 increases replace the earlier rates, not add to them (R25 note)
  IEEPA          fentanyl and reciprocal tariffs, 2025-02-04 to 2026-02-23 (R44-R50, R68-R86), ended by the Supreme
                 Court (R52); critical minerals and refined chemicals exempt from the reciprocal ones (R51)
  Section 122    10% on all countries, 2026-02-24 to 2026-07-23 (R53), minerals and chemicals exempt (as R51; ours)
  Forced labour  Section 301, from 2026-07-24 (R54, R87-R97): China 12.5% on top of its other duties; the allies
                 about 10% (Japan and Korea capped at 12.5% with MFN, the EU at 10%; Canada, the UK 10%, Australia
                 12.5%); the rest of the world 10% (Chile 12.5%); the DRC none. Minerals and refined chemicals exempt;
                 cells, cathode and anode material not (R54 note); pCAM, a refined chemical, taken as exempt (ours)
Not applied by default: Section 232's 25% on vehicle batteries (R59; whether it reaches other batteries is
contested: `s232=True` adds it to cells from all exporters); the graphite anode AD/CVD duties (R60-R67: the ITC
found no injury on 2026-03-31, so no orders); China's export controls (R123-R128: licences, not tariffs; a
scenario can close the arcs instead). The EU's tariffs on China (R99-R116) stand for the allies' on China; Japan,
Korea and Australia's were not found (R120-R122).

45X (credits()): per unit made in the US. Cells 35 USD per kWh; electrode active materials (cathode and anode) and
critical minerals (refined lithium, nickel, cobalt, manganese; graphite) 10% of production cost, recycled feed
included (C rows; T.D. 10010). Phase-down by year: components 75%/50%/25% in 2030-32, none from 2033; critical
minerals (PL 119-21) full to 2030, then 75%/50%/25%, none from 2034. pCAM's eligibility is unsettled (C rows: blank):
not credited. Modules are not in the network. law="IRA" uses the schedule before PL 119-21. The foreign-entity
rules (PL 119-21, from 2026): a credited component's material costs at least 60% (2026) to 85% (2030 on) from
outside prohibited foreign entities, critical minerals 25% (2030) to 50% (2033 on); feoc=True holds US production
to them, taking China's share of each input as the prohibited share (ours: China stands for "prohibited foreign
entity").
"""
from datetime import date

import pandas as pd

from . import network as N

DATA = N.RAW / "battery_horizon" / "policy"
ASOF = date(2026, 11, 24)
FAR = date(2100, 1, 1)

# (from, to, rate %) segments; None for open ends. Each list cites its rows.
_S301_CHN = {                                   # Section 301 on China, by (stage, good); stage-wide where good None
    ('mine', 'Li'): [],                                                       # R40: spodumene, none
    ('mine', 'Ni'): [(date(2019, 5, 10), None, 25.0)],                       # R37
    ('mine', 'Co'): [(date(2024, 9, 27), None, 25.0)],                       # R38, R39
    ('mine', 'graphite'): [(date(2026, 1, 1), None, 25.0)],                  # R32, R33
    ('refine', None): [(date(2019, 5, 10), None, 25.0)],                     # R34, R35
    ('pcam', None): [(date(2019, 5, 10), None, 25.0)],                       # as refined chemicals (R23: no HTS; ours)
    ('cath', None): [(date(2019, 5, 10), None, 25.0)],                       # R36
    ('anode', None): [(date(2019, 5, 10), None, 25.0)],                      # R31
    ('cell', None): [(date(2020, 2, 14), date(2024, 9, 26), 7.5),            # R24-R27: EV cells 25% from 2024-09-27,
                     (date(2024, 9, 27), date(2025, 12, 31), 16.25),         # others from 2026-01-01; between, the
                     (date(2026, 1, 1), None, 25.0)],                        # mean of the two (ours)
    ('shred', None): [(date(2022, 1, 1), None, 7.5)],                        # R41: black mass
}
_MFN = {'mine': 0.0, 'refine': 3.7, 'pcam': 3.7, 'cath': 5.0, 'anode': 3.7, 'cell': 3.4, 'shred': 0.0}  # R0-R22
EXEMPT = {'mine', 'refine', 'pcam'}             # minerals and refined chemicals: out of IEEPA reciprocal (R51),
                                                # Section 122 and forced-labour duties (ours for 122 and pCAM)
_IEEPA_CHN_FENT = [(date(2025, 2, 4), date(2025, 3, 3), 10.0), (date(2025, 3, 4), date(2025, 11, 9), 20.0),
                   (date(2025, 11, 10), date(2026, 2, 23), 10.0)]             # R44-R46: all products
_IEEPA_CHN_RECIP = [(date(2025, 4, 5), date(2025, 4, 8), 10.0), (date(2025, 4, 9), date(2025, 4, 9), 84.0),
                    (date(2025, 4, 10), date(2025, 5, 13), 125.0), (date(2025, 5, 14), date(2026, 2, 23), 10.0)]  # R47-R50
_IEEPA_ALLY = [(date(2025, 4, 5), date(2025, 8, 6), 10.0), (date(2025, 8, 7), date(2026, 2, 23), 15.0)]  # R68-R80
_IEEPA_ROW = [(date(2025, 4, 5), date(2025, 8, 6), 10.0), (date(2025, 8, 7), date(2026, 2, 23), 19.0)]   # R71, R81
_IEEPA_SPC = [(date(2025, 4, 5), date(2025, 8, 6), 10.0), (date(2025, 8, 7), date(2026, 2, 23), 15.0)]   # R72, R82
_S122 = [(date(2026, 2, 24), date(2026, 7, 23), 10.0)]                                                   # R53
_FL = {'CHN': 12.5, 'ALLY': 10.0, 'ROW': 10.0, 'SPC': 0.0}     # R54, R87-R97 (ALLY: Japan/Korea at 12.5% with MFN,
FL_FROM = date(2026, 7, 24)                                    # the EU 10%, Canada and the UK 10%; ROW: 10%, Chile
#                                                                12.5%; a round figure for each, ours)
FL_ALLY_CELL = 12.5     # cells from the allies come mostly from Korea and Japan; KORUS puts Li-ion batteries at 0% MFN,
#                         so the forced-labour duty is the full 12.5% (the check of 2026-11-24, R87, R88)
_EU_CHN = {'mine': 0.0, 'refine': 5.0, 'pcam': 5.0, 'cath': 5.5, 'anode': 3.6, 'cell': 2.7, 'shred': 2.6}  # R99-R113
_S232_CELL = [(date(2025, 5, 3), None, 25.0)]                                                            # R59


def _days(seg, y):
    """Mean rate over year y of [(from, to, rate)] segments (to None: open)."""
    a, b = date(y, 1, 1), date(y, 12, 31)
    tot = 0.0
    for f, t, r in seg:
        t = t or FAR
        lo, hi = max(a, f), min(b, t)
        if hi >= lo:
            tot += r * ((hi - lo).days + 1)
    return tot / ((b - a).days + 1)


def tariffs(years, stages=('mine', 'refine', 'pcam', 'cath', 'anode', 'cell', 'shred'), goods=None, s232=False):
    """{(stage, exporter, 'US') or (stage, good, exporter, 'US'): {year: rate}} and the EU's on China for the allies,
    {(stage, 'CHN', 'ALLY'): {year: rate}}; rates as shares (0.25), the layers in the module docstring. goods:
    {stage: [good, ...]} for the goods with their own Section 301 rate (mining's)."""
    def at(seg, y):                                # by days to ASOF's year; after it, the rate in force on ASOF
        if y <= ASOF.year:
            return _days(seg, y)
        return sum(r for f, t, r in seg if f <= ASOF <= (t or FAR))
    out = {}
    for s in stages:
        gl = [g for (st, g) in _S301_CHN if st == s and g is not None] or [None]
        for g in gl:
            s301 = _S301_CHN.get((s, g), _S301_CHN.get((s, None), []))
            for exp in ('CHN', 'ALLY', 'ROW', 'SPC'):
                r = {}
                for y in years:
                    v = 0.0
                    if exp in ('CHN', 'ROW'):
                        v += _MFN[s]
                    if exp == 'CHN':
                        v += at(s301, y) + at(_IEEPA_CHN_FENT, y) + (0.0 if s in EXEMPT else at(_IEEPA_CHN_RECIP, y))
                    else:
                        v += 0.0 if s in EXEMPT else at({'ALLY': _IEEPA_ALLY, 'ROW': _IEEPA_ROW,
                                                         'SPC': _IEEPA_SPC}[exp], y)
                    if s not in EXEMPT:
                        fl = FL_ALLY_CELL if (exp == 'ALLY' and s == 'cell') else _FL[exp]
                        v += at(_S122, y) + at([(FL_FROM, None, fl)], y)
                        if s232 and s == 'cell':
                            v += at(_S232_CELL, y)
                    r[y] = v / 100.0
                key = (s, exp, 'US') if g is None else (s, g, exp, 'US')
                out[key] = r
        out[s, 'CHN', 'ALLY'] = {y: _EU_CHN[s] / 100.0 for y in years}
    return out


def credits(years, law="PL 119-21"):
    """{kind: {year: value}} for 45X: 'cell' (USD per kWh = M USD per GWh), 'eam' and 'mineral' (shares of
    production cost), from credits.csv."""
    c = pd.read_csv(DATA / "credits.csv")
    q = c[(c.measure == "45X") & (c.law_version == law)]
    comp = {'cell': "battery cell", 'eam': "electrode active materials (cathode and anode active material)",
            'mineral': "applicable critical mineral: lithium"}
    out = {}
    for k, name in comp.items():
        rows = q[q.component == name]
        by = {int(r.year): float(r.value) for r in rows.itertuples() if pd.notna(r.year)}
        out[k] = {y: by.get(y, 0.0) * (1.0 if k == 'cell' else 0.01) for y in years}
    return out


def feoc_thresholds(years):
    """{kind: {year: minimum share of material cost from outside prohibited foreign entities}} (PL 119-21):
    'component' (cells, electrode active materials) and 'mineral'; zero before 2026, the last value held after."""
    c = pd.read_csv(DATA / "credits.csv")
    out = {}
    for k, name in (('component', "PFE material assistance threshold: qualifying battery components (EAM, cells, "
                                  "modules)"), ('mineral', "PFE material assistance threshold: applicable critical "
                                                          "minerals")):
        rows = c[c.component == name]
        by = {int(r.year): float(r.value) / 100.0 for r in rows.itertuples() if pd.notna(r.year)}
        last = max(by)
        out[k] = {y: (by.get(y, 0.0) if y <= last else by[last]) for y in years}
    return out
