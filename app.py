"""Run with: python -m streamlit run app.py"""
import json
from dataclasses import asdict

import pandas as pd
import plotly.express as px
import streamlit as st

from battery_model import Cell, Engineering, Limits, Load, configurations, evaluate

st.set_page_config(page_title='PER · Battery Design Lab', page_icon='⚡', layout='wide')
st.title('⚡ Battery Design Lab')
st.caption('Purdue Electric Racing · Series/parallel tradeoffs · Steady-state design estimates')

with st.sidebar:
    st.header('Pack configuration')
    total = st.number_input('Total available cells', 1, 100000, 144, step=1)
    series = st.number_input('Cells in series (S)', 1, 100000, 72, step=1)
    parallel = st.number_input('Cells in parallel (P)', 1, 100000, 2, step=1)
    st.caption('Selected pack uses S × P cells. The sweep uses every available cell.')
    st.header('Cell characteristics')
    st.caption('Illustrative inputs — replace with cell datasheet and measured values.')
    capacity = st.number_input('Capacity (Ah)', 0.01, 1000.0, 5.0, step=0.1)
    r_mohm = st.number_input('DC internal resistance (mΩ per cell)', 0.0, 1000.0, 15.0, step=0.5)
    v_max = st.number_input('Maximum cell voltage (V)', 0.01, 10.0, 4.2, step=0.05)
    v_nom = st.number_input('Nominal cell voltage (V)', 0.01, 10.0, 3.6, step=0.05)
    v_min = st.number_input('Minimum loaded cell voltage / cutoff (V)', 0.01, 10.0, 2.5, step=0.05)
    cell_current = st.number_input('Continuous cell discharge limit (A)', 0.01, 10000.0, 35.0)
    mass_g = st.number_input('Cell mass (g)', 0.01, 10000.0, 70.0)
    st.header('Weight, cost & packaging')
    cell_price = st.number_input('Price per cell (USD)', 0.0, 100000.0, 6.0)
    fixed_cost = st.number_input('Other pack costs (USD)', 0.0, 10000000.0, 1500.0)
    overhead_mass = st.number_input('Non-cell pack mass (kg)', 0.0, 10000.0, 8.0)
    st.caption('Include enclosure, busbars, cooling, BMS, contactors, wiring, and assembly in the overhead estimates.')
    volume_ml = st.number_input('External cell volume (mL)', 0.01, 100000.0, 24.25)
    packing = st.slider('Cell packing fraction (%)', 1, 100, 70) / 100
    fixed_volume = st.number_input('Additional equipment volume (L)', 0.0, 10000.0, 2.0)
    st.header('Thermal estimate')
    specific_heat = st.number_input('Cell specific heat (J/kg/K)', 0.01, 10000.0, 1000.0)
    duration = st.number_input('Constant-load duration (s)', 0.0, 100000.0, 60.0)
    st.header('Motor demand')
    motors = st.number_input('Number of motors', 1, 20, 2)
    mode_label = st.selectbox('Demand mode', ['Constant power', 'Constant DC current'])
    mode = 'power' if mode_label == 'Constant power' else 'current'
    basis = 'electrical'
    if mode == 'power':
        basis = st.selectbox('Power measured at', ['electrical', 'mechanical'],
                             format_func=lambda x: 'Controller DC input' if x == 'electrical' else 'Motor shaft')
        demand = st.number_input('Power per motor (kW)', 0.0, 1000.0, 5.0, step=0.5) * 1000
    else:
        demand = st.number_input('DC battery-side current per motor (A)', 0.0, 10000.0, 30.0)
        st.caption('DC input current, not motor phase current. Same current at a different voltage means different motor power.')
    efficiency = st.slider('Combined inverter + motor efficiency (%)', 1, 100, 90) / 100
    aux = st.number_input('Auxiliary electrical load (W)', 0.0, 100000.0, 200.0)
    st.header('System constraints')
    min_bus = st.number_input('Controller minimum operating voltage (V)', 0.0, 10000.0, 100.0)
    max_bus = st.number_input('Controller maximum voltage (V)', 0.01, 10000.0, 600.0)
    max_bus_a = st.number_input('Total controller DC current limit (A)', 0.01, 100000.0, 300.0)
    heat_budget = st.number_input('Allowed pack resistive heat (W)', 0.0, 1000000.0, 3000.0)

try:
    cell = Cell(capacity, r_mohm / 1000, v_max, v_nom, v_min, cell_current, mass_g / 1000)
    load = Load(motors, mode, demand, basis, efficiency, aux)
    limits = Limits(min_bus, max_bus, max_bus_a, heat_budget)
    engineering = Engineering(cell_price, fixed_cost, overhead_mass, volume_ml, packing,
                              fixed_volume, specific_heat, duration)
except ValueError as exc:
    st.error(str(exc))
    st.stop()

if series * parallel > total:
    st.error(f'This pack needs {series * parallel:,} cells, exceeding the {total:,} available. Adjust S, P, or the cell budget.')
    st.stop()
if series * parallel < total:
    st.info(f'Selected pack uses {series * parallel:,} cells; {total - series * parallel:,} remain unused. Sweep configurations use all {total:,}.')

st.subheader('Operating point')
ocv = st.slider('Cell open-circuit voltage for calculations (V)', float(v_min), float(v_max),
                float(v_nom), step=0.01, key=f'ocv_{v_min}_{v_nom}_{v_max}')
point = evaluate(cell, series, parallel, load, limits, ocv, engineering)
if point['Feasible']:
    st.success(f'{point["Configuration"]}: demand is within the entered limits at this open-circuit voltage.')
else:
    st.warning(point['Constraints'])

metrics = ['Loaded voltage (V)', 'Pack current (A)', 'Terminal power (kW)', 'Heat (W)']
for col, key in zip(st.columns(4), metrics):
    value = point[key]
    col.metric(key, f'{value:,.2f}' if pd.notna(value) else 'No solution')
for col, key in zip(st.columns(4), ['Pack mass (kg)', 'Estimated pack cost (USD)',
                                   'Specific energy (Wh/kg)', 'Pack volume estimate (L)']):
    col.metric(key, f'{point[key]:,.2f}')

overview, sweep_tab, operating_tab, assumptions = st.tabs(
    ['Pack summary', 'Fixed cell count optimization', 'Operating curves', 'Model & exports'])

def chart(frame, x, y, color=None, title=None):
    fig = px.line(frame, x=x, y=y, color=color, markers=True, title=title)
    fig.update_layout(legend_title_text='', hovermode='x unified')
    st.plotly_chart(fig, use_container_width=True)

with overview:
    left, right = st.columns(2)
    with left:
        st.subheader('Electrical & physical characteristics')
        keys = ['Cells', 'Capacity (Ah)', 'Nominal energy (Wh)', 'Cell mass (kg)',
                'Full-charge voltage (V)', 'Nominal voltage (V)', 'Cutoff voltage (V)',
                'Open-circuit voltage (V)', 'Pack resistance (mΩ)', 'Voltage sag (V)',
                'Cell current (A)', 'Discharge rate (C)', 'Heat per cell (W)',
                'Pack electrical efficiency (%)', 'Shaft power estimate (kW)',
                'Runtime estimate (min)', 'Allowed terminal power (kW)']
        keys += ['Pack mass (kg)', 'Pack weight (N)', 'Estimated pack cost (USD)',
                 'Pack volume estimate (L)', 'Specific energy (Wh/kg)', 'Energy density (Wh/L)',
                 'Energy cost (USD/kWh)', 'Allowed specific power (kW/kg)',
                 'Delivered specific power (kW/kg)', 'Heat over duration (kJ)',
                 'Adiabatic cell temperature rise (°C)']
        st.dataframe(pd.DataFrame({'Metric': keys, 'Value': [point[k] for k in keys]}),
                     hide_index=True, width='stretch')
        st.caption('Runtime is Ah ÷ current at this operating point, assuming full rated capacity. It does not predict usable endurance to cutoff. Cell mass excludes enclosure, cooling, busbars, and electronics.')
    with right:
        st.subheader('Where the electrical power goes')
        if pd.notna(point['Heat (W)']):
            terminal = point['Terminal power (kW)'] * 1000
            shaft = point['Shaft power estimate (kW)'] * 1000
            flow = pd.DataFrame({'Destination': ['Motor shaft estimate', 'Motor + inverter loss',
                                                  'Auxiliaries', 'Cell resistive heat'],
                                 'Power (W)': [shaft, max(0, terminal - aux - shaft), aux, point['Heat (W)']]})
            st.plotly_chart(px.bar(flow, x='Destination', y='Power (W)', color='Destination'),
                            use_container_width=True)
        st.info('Adiabatic temperature rise assumes constant I²R heating, no cooling, and cell thermal mass only. It is not a prediction of peak or steady-state temperature.')
        breakdown = pd.DataFrame({'Component': ['Cells', 'Pack overhead'],
                                  'Mass (kg)': [series * parallel * cell.mass_kg, overhead_mass],
                                  'Cost (USD)': [series * parallel * cell_price, fixed_cost]})
        st.plotly_chart(px.bar(breakdown, x='Component', y='Mass (kg)', color='Component'), use_container_width=True)
        st.plotly_chart(px.bar(breakdown, x='Component', y='Cost (USD)', color='Component'), use_container_width=True)

sweep = pd.DataFrame([evaluate(cell, s, p, load, limits, ocv, engineering) for s, p in configurations(total)])
with sweep_tab:
    st.subheader(f'All exact arrangements of {total:,} cells')
    st.write('Move left on the series axis to decrease series and increase parallel. Each point uses every cell; lines connect discrete options and do not imply fractional cell counts.')
    st.caption('At fixed cell count, nominal energy is invariant. Without system voltage/current constraints, identical-cell power capability is also invariant. There is no universally optimal arrangement.')
    objective = st.selectbox('Rank feasible configurations by',
                            ['Lowest heat', 'Lowest pack current', 'Highest allowed terminal power'])
    objective_key = {'Lowest heat': 'Heat (W)', 'Lowest pack current': 'Pack current (A)',
                     'Highest allowed terminal power': 'Allowed terminal power (kW)'}[objective]
    feasible = sweep[sweep['Feasible']].sort_values(objective_key, ascending=objective != 'Highest allowed terminal power')
    if feasible.empty:
        st.warning('No exact arrangement meets all entered constraints at this operating point. Inspect the constraint table or adjust the inputs.')
    else:
        best_value = feasible.iloc[0][objective_key]
        tied = feasible[(feasible[objective_key] - best_value).abs() <= max(1e-7, abs(best_value) * 1e-6)]
        st.success(f'{len(feasible)} feasible arrangement(s). Best {objective_key.lower()}: {best_value:,.3f}. '
                   f'Tied within numerical tolerance: {", ".join(tied["Configuration"])}.')
    st.caption('Ranking applies only to the chosen demand and open-circuit voltage. In current mode, power changes across configurations; lower heat can accompany lower delivered power.')
    for row in [('Open-circuit voltage (V)', 'Loaded voltage (V)'), ('Pack current (A)', 'Cell current (A)'),
                ('Terminal power (kW)', 'Allowed terminal power (kW)'), ('Heat (W)', 'Pack electrical efficiency (%)')]:
        for col, key in zip(st.columns(2), row):
            with col:
                fig = px.line(sweep, x='Series', y=key, markers=True,
                              hover_data=['Configuration', 'Parallel', 'Feasible', 'Constraints'])
                # Explicitly distinguish violated constraints without joining status subsets.
                for status, color in [(True, '#16a085'), (False, '#e74c3c')]:
                    subset = sweep[sweep['Feasible'] == status]
                    fig.add_scatter(x=subset['Series'], y=subset[key], mode='markers',
                                    marker={'color': color, 'size': 9}, name='Feasible' if status else 'Constraint exceeded')
                st.plotly_chart(fig, use_container_width=True)
    extra_metric = st.selectbox('Additional engineering comparison',
                               ['Nominal energy (Wh)', 'Pack mass (kg)', 'Estimated pack cost (USD)',
                                'Energy density (Wh/L)', 'Specific energy (Wh/kg)', 'Energy cost (USD/kWh)',
                                'Allowed specific power (kW/kg)', 'Adiabatic cell temperature rise (°C)'])
    chart(sweep, 'Series', extra_metric)
    st.caption('Mass, cost, and packaging estimates use the same overhead for each topology. They remain constant at fixed cell count; topology-specific busbars, cooling, and enclosure costs require separate estimates.')
    st.dataframe(sweep, hide_index=True, width='stretch')
    st.download_button('Download configuration comparison (CSV)', sweep.to_csv(index=False),
                       'battery_configurations.csv', 'text/csv')

with operating_tab:
    st.subheader('Sensitivity to cell open-circuit voltage')
    st.caption('This is an OCV sweep, not a state-of-charge or time simulation. Cell resistance is held constant. Inspect the Feasible and Constraints columns for operating limits.')
    voltages = [v_min + (v_max - v_min) * i / 80 for i in range(81)]
    curve = pd.DataFrame([dict(evaluate(cell, series, parallel, load, limits, v, engineering), **{'Cell OCV (V)': v}) for v in voltages])
    a, b = st.columns(2)
    with a:
        chart(curve, 'Cell OCV (V)', ['Open-circuit voltage (V)', 'Loaded voltage (V)', 'Cutoff voltage (V)'])
        chart(curve, 'Cell OCV (V)', ['Terminal power (kW)', 'Allowed terminal power (kW)'])
    with b:
        chart(curve, 'Cell OCV (V)', 'Pack current (A)')
        chart(curve, 'Cell OCV (V)', 'Heat (W)')
    st.dataframe(curve[['Cell OCV (V)', 'Loaded voltage (V)', 'Cell current (A)', 'Heat (W)', 'Feasible', 'Constraints']],
                 hide_index=True, width='stretch')
    st.download_button('Download OCV sweep (CSV)', curve.to_csv(index=False), 'ocv_sweep.csv', 'text/csv')
    st.subheader('Load capability at the selected OCV')
    max_plot_a = max(parallel * cell.max_current_a * 1.25, 1.0)
    rows = []
    for i in range(101):
        amps = max_plot_a * i / 100
        result = evaluate(cell, series, parallel, Load(1, 'current', amps, efficiency=efficiency), limits, ocv, engineering)
        rows.append(dict(result, **{'Requested DC current (A)': amps}))
    current_curve = pd.DataFrame(rows)
    st.caption('This independent load sweep uses total battery DC current and no auxiliary load. Values beyond constraints are illustrative only.')
    a, b = st.columns(2)
    with a:
        chart(current_curve, 'Requested DC current (A)', 'Loaded voltage (V)')
    with b:
        chart(current_curve, 'Requested DC current (A)', ['Terminal power (kW)', 'Source power (kW)'])

with assumptions:
    st.subheader('Equations & scope')
    st.markdown(r'''
- Identical, balanced cells: $N=S P$, $V_{oc}=S V_{cell}$, $R_{pack}=S R_{cell}/P$.
- Capacity: $Q_{pack}=P Q_{cell}$; nominal energy: $E=N V_{nom} Q_{cell}$ (Wh).
- Loaded voltage: $V=V_{oc}-I R_{pack}$; cell current: $I_{cell}=I/P$.
- Terminal power: $P_{out}=VI$; cell resistive heat: $P_{heat}=I^2R_{pack}$.
- Constant electrical power: solve $P_{out}=I(V_{oc}-IR_{pack})$ using the lower-current, higher-voltage root. Impossible demands produce missing values.
- Mechanical demand is divided by combined motor/inverter efficiency to obtain DC demand. Auxiliary power is added at the battery terminals.
- Allowed terminal power maximizes $I(V_{oc}-IR)$ subject to cell current, controller current, loaded cell cutoff, controller voltage, and heat budget. It excludes motor ratings and is before auxiliary consumption.
- Full-charge pack voltage must fit the controller maximum even when the operating OCV is lower. Feasibility at one OCV does not establish feasibility across discharge.
- Pack mass = cell mass × count + non-cell mass. Pack cost = cell price × count + other pack costs (USD).
- Pack volume = total external cell volume / packing fraction + additional equipment volume. This is an estimate, not a geometric layout check.
- Specific energy and energy density use nominal energy. Adiabatic temperature rise is $\Delta T=I^2 R t/(N m_{cell} c_p)$; no cooling or overhead thermal mass is included.

This model omits cell imbalance, aging, temperature-dependent resistance, interconnect and contactor resistance, transient loads, regenerative charging, cooling, and detailed discharge curves. Nominal energy and runtime are estimates, not usable race endurance. A thermal limit in watts does not predict temperature. Verify cell data, protection, insulation, cooling, and applicable competition rules before hardware decisions. This tool does not certify a pack design.
''')
    inputs = {'total_cells': total, 'series': series, 'parallel': parallel, 'cell_ocv_v': ocv,
              'cell': asdict(cell), 'load': asdict(load), 'limits': asdict(limits), 'engineering': asdict(engineering)}
    st.download_button('Download inputs (JSON)', json.dumps(inputs, indent=2), 'battery_inputs.json', 'application/json')
    st.download_button('Download selected pack (CSV)', pd.DataFrame([point]).to_csv(index=False), 'selected_pack.csv', 'text/csv')
    st.caption('Charts support zoom, pan, hover, and PNG export through the Plotly toolbar.')
