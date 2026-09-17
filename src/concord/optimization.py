"""Bounded candidate generation and external-result scoring, never fake acoustics."""
from copy import deepcopy
import random

from pydantic import ValidationError
from .config import Design,bounds
from .bem import Response


def candidates(design: Design,count: int,seed: int):
    if not 1<=count<=1000:
        raise ValueError("candidate count must be between 1 and 1000")
    rng=random.Random(seed)
    allowed={key: value for key,value in bounds().items()
             if not (design.manual.hf_only and key.startswith("lf_"))}
    result=[]
    for _ in range(count*100):
        data=deepcopy(design.model_dump())
        data["optimized"].update({key:rng.uniform(lo,hi) for key,(lo,hi) in allowed.items()})
        try:
            result.append(Design.model_validate(data))
        except ValidationError:
            continue
        if len(result)==count:
            return result
    raise ValueError("Could not sample enough feasible candidates; inspect manual settings and bounds")


def beamwidth(angles,row):
    """First -6 dB crossings around boresight; reject truncated main lobes."""
    center=angles.index(0)
    def crossing(indices):
        previous=center
        for i in indices:
            if row[i]<=-6:
                t=(-6-row[previous])/(row[i]-row[previous])
                return angles[previous]+t*(angles[i]-angles[previous])
            previous=i
        raise ValueError("Polar does not contain both -6 dB crossings; expand angular range")
    return crossing(range(center+1,len(angles)))-crossing(range(center-1,-1,-1))


def score(design: Design,response: Response):
    if response.synthetic:
        raise ValueError("Synthetic data cannot rank design candidates")
    if response.frequencies_hz!=design.manual.frequencies_hz:
        raise ValueError("Response frequencies do not match design request")
    h=[beamwidth(response.angles_deg,row) for row in response.horizontal_db]
    v=[beamwidth(response.angles_deg,row) for row in response.vertical_db]
    target=design.manual.coverage
    mean=lambda values:sum(values)/len(values)
    mse=lambda values,t:mean([(x-t)**2 for x in values])
    # V0 ranking only. Future full objective needs complex LF/HF fields and loading.
    terms={"horizontal_error":mse(h,target.horizontal_target_deg)/target.horizontal_target_deg**2,
           "vertical_error":mse(v,target.vertical_target_deg)/target.vertical_target_deg**2,
           "horizontal_ripple":mse(h,mean(h))/target.horizontal_target_deg**2,
           "off_axis_peak":mean([max(0,max(row))**2 for row in response.horizontal_db+response.vertical_db])/36}
    return {"objective":sum(terms.values()),"terms":terms,"horizontal_beamwidth_deg":h,
            "vertical_beamwidth_deg":v,"scope":"V0 beamwidth ranking; not complete acoustic qualification"}
