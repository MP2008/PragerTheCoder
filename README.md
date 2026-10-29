# Battery Design Lab

An interactive Python dashboard for Purdue Electric Racing battery configuration studies.
Enter cell characteristics, series/parallel counts, motor demand, and controller limits;
compare pack voltage, current, energy, power, resistive heat, and operating feasibility.
Illustrative defaults are not a recommendation for a specific cell or vehicle.

## Run

Python 3.10 or later:

```sh
python -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m streamlit run app.py --server.address 0.0.0.0
```

On Windows, use `.venv\Scripts\python` instead of `.venv/bin/python`.
Streamlit opens an interactive web dashboard. Inputs are in the sidebar.
The dashboard has pack summaries, exact-factor configuration comparisons, operating
curves, constraint explanations, CSV/JSON downloads, and chart PNG exports.
No API keys or external services are required.

Engineering inputs include cell and non-cell mass, price per cell and other pack costs,
external cell volume, packing fraction, additional equipment volume, cell specific heat,
and load duration. Outputs include total mass and weight, estimated cost, Wh/kg, Wh/L,
USD/kWh, delivered and allowed kW/kg, accumulated resistive heat, and an adiabatic
cell temperature-rise estimate. Costs use USD. Pack overhead is held constant across
the topology sweep; adjust it manually when a design needs different hardware.

## How to compare designs

1. Enter measured DC cell resistance, rated capacity, voltage limits, mass, and continuous discharge current.
2. Set the cell budget and selected series/parallel topology. The selected pack may leave cells unused; the optimization sweep uses all cells.
3. Choose constant motor electrical/mechanical power or battery-side DC current. Phase current is not DC battery current.
4. Enter controller voltage/current limits, auxiliary demand, and an allowed resistive heat budget.
5. Inspect feasibility at the selected cell open-circuit voltage, then sweep OCV to inspect lower-voltage operation.
6. Rank feasible exact-factor arrangements by heat, pack current, or allowed terminal power. Ties are reported; there is no universal optimum.

At fixed cell count, nominal energy remains constant. Ideal identical-cell maximum
power also remains constant without system constraints. More series increases voltage
and decreases pack current for the same power; cell current and cell heat remain
unchanged. Controller constraints can break that equivalence. In constant-current
mode, delivered power changes with voltage, so comparisons are not at equal output.

## Model

`battery_model.py` is a dependency-free, reusable calculation module. It models identical
cells as ideal voltage sources with series DC resistance. Constant-power loads use the
stable high-voltage solution and impossible requests are reported, not silently clipped.
Cell cutoff, continuous current, full-charge controller voltage, operating bus voltage,
controller current, and heat constraints are checked. Heat is I²R in watts, not temperature.
Nominal energy and Ah/current runtime do not model usable endurance or SOC. Resistance
and efficiency are constant; no dynamic, regenerative, aging, or cooling model is included.
Temperature rise uses heat × duration / cell thermal capacity with no cooling and no
heat transfer into the pack structure. Volume is a packing estimate, not a CAD layout.
All internal quantities use volts, amps, watts, ohms, kilograms, and amp-hours.

## Validate

```sh
.venv/bin/python -m unittest discover -s tests -v
```

The tests exercise analytical pack scaling, conservation of power, constant-power
solutions, infeasible loads, constraint boundaries, and the Streamlit UI.
