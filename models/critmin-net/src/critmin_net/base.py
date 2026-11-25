"""Base materials: minerals and metals whose supply is so large that energy uses are a small, steady part of it.

Jones, 2026-11-22: they get simple supply at a price, not a full chain. A network names them as goods with no
process behind them and gives each a price (and optionally a ceiling) in net["base"]; build() buys them in each
region (see network's base-materials notes). This module holds their published prices and world output, shared by
every network, so a network does not carry its own copper.

prices()      {(material, year): USD per tonne contained}, USGS MCS 2025 (data/base_materials/usgs_mcs2025.csv,
              its "price_contained" rows, each derived from the published price as its note says):
              iron ore (US mine average unit value over its implied Fe grade), manganese (44% ore, CIF China, per
              metric ton unit), copper (LME grade A cash), aluminium (US market ingot spot). 2024 is USGS's estimate.
world()       {(material, year): world output, kt contained}, from the same tables, for checking that a network's use
              is small beside it.

Not here yet: phosphate (USGS gives a price for marketable rock of all grades but no grade, so no price per tonne
of P) and steel (USGS gives only a producer price index). Both need another source before a network prices them.
"""
import pandas as pd

from . import network as N

DATA = N.RAW / "base_materials"
MATERIALS = ['iron_ore', 'manganese', 'copper', 'aluminum', 'phosphate_rock', 'steel']
CONTAINED = {'iron_ore': 'Fe', 'manganese': 'Mn', 'copper': 'Cu', 'aluminum': 'Al'}


def _read():
    return pd.read_csv(DATA / "usgs_mcs2025.csv")


def prices():
    """{(material, year): USD per tonne of contained element}, for the materials that have one (CONTAINED)."""
    d = _read()
    d = d[d.item == "price_contained"]
    return {(r.material, int(r.year)): float(r.value) for r in d.itertuples()}


def world():
    """{(material, year): world output in kt of contained element} (refined copper, primary aluminium; iron ore and
    manganese as their metal content)."""
    d = _read()
    d = d[(d.item == "world_production") & (d.country_or_region == "World")]
    pick = {'iron_ore': "iron content", 'manganese': "Mn content", 'aluminum': "thousand metric tons"}
    out = {}
    for r in d.itertuples():
        if r.material == 'copper':
            if "refinery" not in str(r.note).lower():
                continue
        elif r.material not in pick or pick[r.material] not in r.unit:
            continue
        out[r.material, int(r.year)] = float(r.value)
    return out
