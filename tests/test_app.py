import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest


class DashboardTests(unittest.TestCase):
    def test_default_and_current_mode(self):
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.metric), 8)
        self.assertGreater(len(at.dataframe), 2)
        self.assertTrue(any('demand is within' in s.value for s in at.success))
        next(w for w in at.number_input if w.label == 'Price per cell (USD)').set_value(10.0).run(timeout=30)
        cost = next(w for w in at.metric if w.label == 'Estimated pack cost (USD)')
        self.assertEqual(cost.value, '2,940.00')
        next(w for w in at.selectbox if w.label == 'Demand mode').select('Constant DC current').run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertEqual(len(at.metric), 8)

    def test_invalid_cell_budget(self):
        at = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'app.py')).run(timeout=30)
        next(w for w in at.number_input if w.label == 'Total available cells').set_value(100).run(timeout=30)
        self.assertEqual(len(at.exception), 0)
        self.assertTrue(any('exceeding' in e.value for e in at.error))


if __name__ == '__main__':
    unittest.main()
