import math
import unittest

from battery_model import Cell, Engineering, Limits, Load, configurations, evaluate


class ModelTests(unittest.TestCase):
    def setUp(self):
        self.cell = Cell()
        self.limits = Limits(0, 10000, 10000, 1000000)

    def test_exact_factor_pairs(self):
        self.assertEqual(configurations(12), [(1, 12), (2, 6), (3, 4), (4, 3), (6, 2), (12, 1)])
        self.assertEqual(configurations(13), [(1, 13), (13, 1)])
        self.assertEqual(configurations(1), [(1, 1)])

    def test_current_load_analytical(self):
        r = evaluate(self.cell, 10, 2, Load(2, 'current', 10), self.limits)
        self.assertAlmostEqual(r['Pack current (A)'], 20)
        self.assertAlmostEqual(r['Loaded voltage (V)'], 34.5)
        self.assertAlmostEqual(r['Heat (W)'], 30)
        self.assertAlmostEqual(r['Terminal power (kW)'], .69)
        self.assertAlmostEqual(r['Capacity (Ah)'], 10)
        self.assertAlmostEqual(r['Nominal energy (Wh)'], 360)

    def test_power_conservation_and_mechanical_conversion(self):
        r = evaluate(self.cell, 72, 2, Load(2, 'power', 5000, 'mechanical', .8, 200), self.limits)
        self.assertAlmostEqual(r['Terminal power (kW)'], 12.7)
        self.assertAlmostEqual(r['Shaft power estimate (kW)'], 10)
        self.assertAlmostEqual(r['Source power (kW)'], r['Terminal power (kW)'] + r['Heat (W)']/1000)

    def test_fixed_cell_count_invariants(self):
        a = evaluate(self.cell, 72, 2, Load(2, 'power', 5000), self.limits)
        b = evaluate(self.cell, 36, 4, Load(2, 'power', 5000), self.limits)
        for key in ['Nominal energy (Wh)', 'Heat (W)', 'Cell current (A)', 'Allowed terminal power (kW)',
                    'Pack mass (kg)', 'Estimated pack cost (USD)']:
            self.assertAlmostEqual(a[key], b[key], msg=key)
        self.assertAlmostEqual(b['Pack current (A)'], 2*a['Pack current (A)'])
        self.assertAlmostEqual(b['Loaded voltage (V)'], a['Loaded voltage (V)']/2)

    def test_impossible_power(self):
        r = evaluate(self.cell, 1, 1, Load(1, 'power', 1000), self.limits)
        self.assertFalse(r['Feasible'])
        self.assertTrue(math.isnan(r['Pack current (A)']))
        self.assertIn('no stable', r['Constraints'])

    def test_zero_resistance(self):
        r = evaluate(Cell(resistance_ohm=0), 10, 2, Load(1, 'power', 360), self.limits)
        self.assertAlmostEqual(r['Pack current (A)'], 10)
        self.assertEqual(r['Heat (W)'], 0)

    def test_current_plus_constant_power_auxiliary(self):
        r = evaluate(self.cell, 10, 2, Load(2, 'current', 10, auxiliary_w=100), self.limits)
        self.assertAlmostEqual(r['Pack current (A)'], 20 + 100/r['Loaded voltage (V)'])
        self.assertAlmostEqual(r['Terminal power (kW)']*1000, 20*r['Loaded voltage (V)'] + 100)

    def test_constraints(self):
        r = evaluate(self.cell, 10, 1, Load(1, 'current', 40), Limits(35, 40, 30, 10))
        for reason in ['Full-charge', 'minimum', 'Cell continuous', 'Controller DC', 'heat budget']:
            self.assertIn(reason, r['Constraints'])
        self.assertEqual(r['Allowed terminal power (kW)'], 0)

    def test_cutoff_and_no_load(self):
        r = evaluate(self.cell, 10, 2, Load(1, 'current', 1), self.limits, 2.5)
        self.assertIn('below cutoff', r['Constraints'])
        self.assertEqual(r['Allowed terminal power (kW)'], 0)
        idle = evaluate(self.cell, 10, 2, Load(1, 'power', 0), self.limits)
        self.assertEqual(idle['Pack current (A)'], 0)
        self.assertTrue(math.isnan(idle['Runtime estimate (min)']))

    def test_power_cap_heat_and_voltage_limits(self):
        for limits in [Limits(0, 10000, 1000, 10), Limits(35, 10000, 1000, 1e6),
                       Limits(0, 10000, 5, 1e6), self.limits]:
            r = evaluate(self.cell, 10, 2, Load(1, 'power', 0), limits)
            cap = evaluate(self.cell, 10, 2, Load(1, 'power', r['Allowed terminal power (kW)']*1000), limits)
            self.assertTrue(cap['Feasible'], cap['Constraints'])

    def test_engineering_metrics(self):
        e = Engineering(4, 100, 2, 20, .5, 1, 1000, 60)
        r = evaluate(self.cell, 10, 2, Load(1, 'current', 20), self.limits, engineering=e)
        self.assertAlmostEqual(r['Pack mass (kg)'], 3.4)
        self.assertAlmostEqual(r['Estimated pack cost (USD)'], 180)
        self.assertAlmostEqual(r['Energy cost (USD/kWh)'], 500)
        self.assertAlmostEqual(r['Pack volume estimate (L)'], 1.8)
        self.assertAlmostEqual(r['Adiabatic cell temperature rise (°C)'], 30*60/(1.4*1000))

    def test_invalid_inputs(self):
        for call in [lambda: Cell(resistance_ohm=-1), lambda: Cell(min_voltage=4),
                     lambda: Cell(capacity_ah=math.nan), lambda: Load(efficiency=0),
                     lambda: Load(motors=0), lambda: Limits(100, 50),
                     lambda: Engineering(packing_fraction=0), lambda: configurations(0),
                     lambda: evaluate(self.cell, 0, 2, Load(), self.limits)]:
            with self.assertRaises(ValueError):
                call()


if __name__ == '__main__':
    unittest.main()
