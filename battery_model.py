"""Steady-state, identical-cell Thevenin pack model. All quantities use SI units."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class Cell:
    capacity_ah: float = 5.0
    resistance_ohm: float = 0.015
    max_voltage: float = 4.2
    nominal_voltage: float = 3.6
    min_voltage: float = 2.5
    max_current_a: float = 35.0
    mass_kg: float = 0.070

    def __post_init__(self):
        values = vars(self)
        if any(not math.isfinite(v) for v in values.values()):
            raise ValueError('Cell parameters must be finite.')
        if self.resistance_ohm < 0 or any(v <= 0 for k, v in values.items() if k != 'resistance_ohm'):
            raise ValueError('Cell parameters must be positive; resistance may be zero.')
        if not self.min_voltage < self.nominal_voltage <= self.max_voltage:
            raise ValueError('Require minimum < nominal ≤ maximum cell voltage.')


@dataclass(frozen=True)
class Load:
    motors: int = 2
    mode: str = 'power'
    per_motor: float = 10000.0  # W (power) or DC battery-side A (current)
    power_basis: str = 'electrical'
    efficiency: float = 0.90
    auxiliary_w: float = 0.0

    def __post_init__(self):
        if not isinstance(self.motors, int) or self.motors < 1:
            raise ValueError('Motor count must be a positive integer.')
        if self.mode not in ('power', 'current') or self.power_basis not in ('electrical', 'mechanical'):
            raise ValueError('Invalid load mode or power basis.')
        if any(not math.isfinite(v) for v in (self.per_motor, self.efficiency, self.auxiliary_w)):
            raise ValueError('Load parameters must be finite.')
        if self.per_motor < 0 or self.auxiliary_w < 0 or not 0 < self.efficiency <= 1:
            raise ValueError('Load must be nonnegative and efficiency must be in (0, 1].')


@dataclass(frozen=True)
class Limits:
    min_bus_v: float = 0.0
    max_bus_v: float = 600.0
    max_bus_a: float = 300.0
    max_heat_w: float = 3000.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in vars(self).values()):
            raise ValueError('Limits must be finite and nonnegative.')
        if self.max_bus_v <= self.min_bus_v or self.max_bus_a <= 0:
            raise ValueError('Require maximum bus voltage > minimum and positive bus current limit.')


@dataclass(frozen=True)
class Engineering:
    cell_price: float = 6.0
    fixed_pack_cost: float = 1500.0
    overhead_mass_kg: float = 8.0
    cell_volume_ml: float = 24.25
    packing_fraction: float = 0.70
    fixed_volume_l: float = 2.0
    specific_heat_j_kg_k: float = 1000.0
    load_duration_s: float = 60.0

    def __post_init__(self):
        if any(not math.isfinite(v) or v < 0 for v in vars(self).values()):
            raise ValueError('Engineering inputs must be finite and nonnegative.')
        if not 0 < self.packing_fraction <= 1:
            raise ValueError('Packing fraction must be in (0, 1].')
        if self.cell_volume_ml <= 0 or self.specific_heat_j_kg_k <= 0:
            raise ValueError('Cell volume and specific heat must be positive.')


def evaluate(cell: Cell, series: int, parallel: int, load: Load, limits: Limits,
             cell_ocv: float | None = None, engineering: Engineering | None = None) -> dict:
    """Evaluate one topology; invalid operating points are NaN, never clipped loads.

    Constant power uses the lower-current root of P=I(Voc-I R). In current
    mode motors draw fixed DC current and auxiliary electronics draw fixed power.
    Limits are comparison constraints, not a dynamic protection simulation.
    """
    if any(not isinstance(n, int) or n < 1 for n in (series, parallel)):
        raise ValueError('Series and parallel counts must be positive integers.')
    ocv = cell.nominal_voltage if cell_ocv is None else cell_ocv
    if not math.isfinite(ocv) or not cell.min_voltage <= ocv <= cell.max_voltage:
        raise ValueError('Cell open-circuit voltage must be between minimum and maximum.')
    count = series * parallel
    engineering = engineering or Engineering()
    voltage = series * ocv
    resistance = series * cell.resistance_ohm / parallel
    fixed_current = load.motors * load.per_motor if load.mode == 'current' else 0.0
    motor_w = load.motors * load.per_motor
    if load.power_basis == 'mechanical':
        motor_w /= load.efficiency
    fixed_power = load.auxiliary_w + (motor_w if load.mode == 'power' else 0.0)
    # V^2 - (Voc - R I_fixed)V + R P_fixed = 0; stable high-voltage root.
    available_voltage = voltage - resistance * fixed_current
    discriminant = available_voltage**2 - 4 * resistance * fixed_power
    solved = available_voltage > 0 and discriminant >= 0
    if solved:
        loaded_v = (available_voltage + math.sqrt(discriminant)) / 2
        current = fixed_current + fixed_power / loaded_v
        cell_a = current / parallel
        heat = current**2 * resistance
        terminal_w = current * loaded_v
        shaft_w = max(0, terminal_w - load.auxiliary_w) * load.efficiency
    else:
        loaded_v = current = cell_a = heat = terminal_w = shaft_w = math.nan

    reasons = []
    if series * cell.max_voltage > limits.max_bus_v + 1e-9:
        reasons.append('Full-charge voltage exceeds controller limit')
    if not solved:
        reasons.append('Demand has no stable positive-voltage solution')
    else:
        for failed, reason in (
            (loaded_v / series < cell.min_voltage - 1e-9, 'Loaded cell voltage below cutoff'),
            (loaded_v < limits.min_bus_v - 1e-9, 'Loaded bus voltage below controller minimum'),
            (cell_a > cell.max_current_a + 1e-9, 'Cell continuous current exceeded'),
            (current > limits.max_bus_a + 1e-9, 'Controller DC current exceeded'),
            (heat > limits.max_heat_w + 1e-9, 'Pack heat budget exceeded'),
        ):
            if failed:
                reasons.append(reason)

    # Maximum terminal power subject to all entered constraints at this OCV.
    min_v = max(series * cell.min_voltage, limits.min_bus_v)
    cap_a = min(parallel * cell.max_current_a, limits.max_bus_a)
    if resistance > 0:
        cap_a = min(cap_a, max(0, (voltage - min_v) / resistance),
                    voltage / (2 * resistance), math.sqrt(limits.max_heat_w / resistance))
    if voltage < min_v or series * cell.max_voltage > limits.max_bus_v:
        cap_a = 0.0
    max_terminal_w = cap_a * (voltage - cap_a * resistance)
    energy_wh = count * cell.nominal_voltage * cell.capacity_ah
    pack_mass = count * cell.mass_kg + engineering.overhead_mass_kg
    pack_cost = count * engineering.cell_price + engineering.fixed_pack_cost
    pack_volume = count * engineering.cell_volume_ml / 1000 / engineering.packing_fraction + engineering.fixed_volume_l
    source_w = voltage * current
    return {
        'Configuration': f'{series}S{parallel}P', 'Series': series, 'Parallel': parallel,
        'Cells': count, 'Capacity (Ah)': parallel * cell.capacity_ah,
        'Nominal energy (Wh)': energy_wh, 'Cell mass (kg)': count * cell.mass_kg,
        'Pack mass (kg)': pack_mass, 'Pack weight (N)': pack_mass * 9.80665,
        'Estimated pack cost (USD)': pack_cost, 'Pack volume estimate (L)': pack_volume,
        'Specific energy (Wh/kg)': energy_wh / pack_mass,
        'Energy density (Wh/L)': energy_wh / pack_volume,
        'Energy cost (USD/kWh)': pack_cost / (energy_wh / 1000),
        'Allowed specific power (kW/kg)': max_terminal_w / 1000 / pack_mass,
        'Delivered specific power (kW/kg)': terminal_w / 1000 / pack_mass,
        'Heat over duration (kJ)': heat * engineering.load_duration_s / 1000,
        'Adiabatic cell temperature rise (°C)': heat * engineering.load_duration_s / (count * cell.mass_kg * engineering.specific_heat_j_kg_k),
        'Full-charge voltage (V)': series * cell.max_voltage,
        'Nominal voltage (V)': series * cell.nominal_voltage,
        'Cutoff voltage (V)': series * cell.min_voltage,
        'Open-circuit voltage (V)': voltage, 'Loaded voltage (V)': loaded_v,
        'Voltage sag (V)': voltage - loaded_v, 'Pack resistance (mΩ)': resistance * 1000,
        'Pack current (A)': current, 'Cell current (A)': cell_a,
        'Discharge rate (C)': cell_a / cell.capacity_ah,
        'Terminal power (kW)': terminal_w / 1000,
        'Shaft power estimate (kW)': shaft_w / 1000,
        'Heat (W)': heat, 'Heat per cell (W)': heat / count,
        'Pack electrical efficiency (%)': 100 * loaded_v / voltage if solved else math.nan,
        'Runtime estimate (min)': parallel * cell.capacity_ah / current * 60 if solved and current > 0 else math.nan,
        'Source power (kW)': source_w / 1000,
        'Allowed terminal power (kW)': max_terminal_w / 1000,
        'Feasible': not reasons, 'Constraints': '; '.join(reasons) or 'Within entered limits',
    }


def configurations(total: int) -> list[tuple[int, int]]:
    """Every exact factor pair, in increasing series order (no unused cells)."""
    if not isinstance(total, int) or total < 1:
        raise ValueError('Total cell count must be a positive integer.')
    low, high = [], []
    for s in range(1, math.isqrt(total) + 1):
        if total % s == 0:
            low.append((s, total // s))
            if s != total // s:
                high.append((total // s, s))
    return low + high[::-1]
