"""Explicit, reproducible frequency sampling without a numerical dependency."""
import math
from .config import Design


def resolve(design, maximum=2000., minimum=None, points=None, spacing='log'):
    if not math.isfinite(maximum) or maximum <= 0:
        raise ValueError('Maximum frequency must be positive and finite')
    if spacing not in ('log', 'linear'):
        raise ValueError('Frequency spacing must be log or linear')
    if minimum is not None and (not math.isfinite(minimum) or not 0 < minimum <= maximum):
        raise ValueError('Minimum frequency must be positive and no greater than maximum')
    if points is not None:
        if minimum is None:
            raise ValueError('--frequency-points requires --min-frequency and --max-frequency')
        if isinstance(points, bool) or not isinstance(points, int) or not 2 <= points <= 1000:
            raise ValueError('Frequency points must be an integer from 2 to 1000')
        if minimum == maximum:
            raise ValueError('A frequency sweep requires minimum < maximum')
        if spacing == 'log':
            frequencies = [math.exp(math.log(minimum)+(math.log(maximum)-math.log(minimum))*i/(points-1)) for i in range(points)]
        else:
            frequencies = [minimum+(maximum-minimum)*i/(points-1) for i in range(points)]
        frequencies[0], frequencies[-1] = float(minimum), float(maximum)
    else:
        frequencies = [f for f in design.manual.frequencies_hz if (minimum is None or f >= minimum) and f <= maximum]
    if not frequencies:
        raise ValueError('No configured frequencies in this range; specify --frequency-points to generate a sweep')
    data = design.model_dump()
    data['manual']['frequencies_hz'] = frequencies
    return Design.model_validate(data)
