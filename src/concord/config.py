"""Strict units, ownership and invariants. m is never a design variable."""
from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

Positive = Annotated[float, Field(gt=0, allow_inf_nan=False)]


class Model(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Fixed(Model):
    superformula_m: Literal[8] = 8
    lf_driver: Literal["B&C 6NDL38"] = "B&C 6NDL38"
    lf_count: Literal[2] = 2
    hf_driver: Literal["B&C DH450"] = "B&C DH450"
    architecture: Literal["central_hf_spine_flanking_lf_slots"] = "central_hf_spine_flanking_lf_slots"
    throat_diameter_mm: Literal[25.4] = 25.4


class Coverage(Model):
    horizontal_target_deg: Annotated[float, Field(ge=90, le=110)] = 90
    horizontal_stretch_deg: Literal[110] = 110
    vertical_target_deg: Annotated[float, Field(gt=0, le=30)] = 10


class Manual(Model):
    hf_only: bool = True  # LF requirements retained, lofts and LF optimization disabled.
    coverage: Coverage = Coverage()
    hf_count: Literal[1] = 1  # V0 assumption: one DH450/module
    module_depth_mm: Positive = 330
    hf_transformer_depth_mm: Positive = 85
    lf_transition_depth_mm: Positive = 75
    lf_inlet_diameter_mm: Positive = 130  # geometric proxy, NOT driver basket/Sd
    lf_inlet_center_x_mm: Positive = 110
    angular_segments: Annotated[int, Field(ge=16, le=256, multiple_of=4)] = 64
    length_segments: Annotated[int, Field(ge=4, le=128)] = 12
    frequencies_hz: list[Positive] = [1000,1250,1600,2000,2500,3150,4000,5000,6300,8000,10000,12500,16000]
    sound_speed_m_s: Positive = 343
    density_kg_m3: Positive = 1.21
    elements_per_wavelength: Annotated[int, Field(ge=6, le=20)] = 6
    array_elements: Annotated[int, Field(ge=1, le=32)] = 3
    array_gap_mm: Annotated[float, Field(ge=0)] = 4
    array_splay_deg: list[Annotated[float, Field(ge=0, le=10)]] = [0, 0]
    crossover_hz: Positive = 1200
    crossover_label: Literal["LR6_acoustic_target"] = "LR6_acoustic_target"

    @model_validator(mode="after")
    def consistent(self):
        if len(self.array_splay_deg) != self.array_elements - 1:
            raise ValueError("array_splay_deg needs exactly array_elements - 1 inter-module angles")
        if not self.frequencies_hz or self.frequencies_hz != sorted(set(self.frequencies_hz)):
            raise ValueError("frequencies_hz must be nonempty, unique and increasing")
        return self


class Optimized(Model):
    mouth_width_mm: Annotated[float, Field(ge=360, le=400)] = 380
    mouth_height_mm: Annotated[float, Field(ge=230, le=270)] = 250
    horn_length_mm: Annotated[float, Field(ge=100, le=200)] = 140
    hf_aperture_width_mm: Annotated[float, Field(ge=8, le=22)] = 14
    hf_aperture_height_mm: Annotated[float, Field(ge=200, le=250)] = 238
    lf_slot_width_mm: Annotated[float, Field(ge=20, le=45)] = 32
    lf_slot_height_mm: Annotated[float, Field(ge=150, le=220)] = 190
    lf_slot_center_x_mm: Annotated[float, Field(ge=35, le=90)] = 60
    lf_slot_z_fraction: Annotated[float, Field(ge=0.2, le=0.6)] = 0.35
    morph_rate: Annotated[float, Field(ge=1, le=5)] = 3.693701077
    sf_a: Annotated[float, Field(ge=0.8, le=2)] = 1.375827392
    sf_b: Annotated[float, Field(ge=0.8, le=2)] = 1.437994835
    sf_n1: Annotated[float, Field(ge=1, le=5)] = 2.152737774
    sf_n2: Annotated[float, Field(ge=1, le=8)] = 5.245161223
    sf_n3: Annotated[float, Field(ge=1, le=8)] = 3.01531782


class Design(Model):
    schema_version: Literal[1] = 1
    fixed: Fixed = Fixed()
    manual: Manual = Manual()
    optimized: Optimized = Optimized()

    @model_validator(mode="after")
    def clearance(self):
        p, m = self.optimized, self.manual
        if p.hf_aperture_height_mm >= p.mouth_height_mm:
            raise ValueError("HF aperture must fit within module/mouth height")
        if not m.hf_only:
            if p.lf_slot_height_mm >= p.mouth_height_mm:
                raise ValueError("LF slot must fit within module/mouth height")
            if p.lf_slot_center_x_mm - p.lf_slot_width_mm/2 <= p.hf_aperture_width_mm/2 + 3:
                raise ValueError("LF slot/HF spine projected clearance must exceed 3 mm")
            if p.lf_slot_center_x_mm + p.lf_slot_width_mm/2 >= p.mouth_width_mm/2:
                raise ValueError("LF slots must fit within mouth width")
        if 2*m.lf_inlet_center_x_mm <= m.lf_inlet_diameter_mm:
            raise ValueError("LF inlet proxies overlap")
        if m.lf_inlet_center_x_mm + m.lf_inlet_diameter_mm/2 >= p.mouth_width_mm/2:
            raise ValueError("LF inlet proxies exceed module width")
        active_depth = m.hf_transformer_depth_mm if m.hf_only else max(m.hf_transformer_depth_mm, m.lf_transition_depth_mm)
        if p.horn_length_mm + active_depth > m.module_depth_mm:
            raise ValueError("acoustic concept exceeds module depth")
        return self


class UniqueLoader(yaml.SafeLoader):
    pass


def _mapping(loader, node):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node)
        if key in result:
            raise ValueError(f"Duplicate YAML key: {key}")
        result[key] = loader.construct_object(value_node)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def load(path: str | Path) -> Design:
    return Design.model_validate(yaml.load(Path(path).read_text(), Loader=UniqueLoader))


def save(design: Design, path: str | Path):
    Path(path).write_text(yaml.safe_dump(design.model_dump(), sort_keys=False))


def bounds() -> dict[str, tuple[float, float]]:
    props = Optimized.model_json_schema()["properties"]
    return {key: (p["minimum"], p["maximum"]) for key, p in props.items()}
