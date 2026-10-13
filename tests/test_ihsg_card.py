import unittest
from data.ihsg_card import build_snapshot

class TestIHSGCard(unittest.TestCase):
    def source(self):
        return {"provider":"purbayasadewa.id","session":"2026-10-13","fallback":False}
    def rows(self, last=101):
        return [{"date":"2026-10-12","close":100},{"date":"2026-10-13","close":last}]
    def test_up(self):
        d=build_snapshot(self.rows(), "2026-10-13", self.source())
        self.assertEqual(d["latest"]["change_pct"],1)
    def test_down(self):
        self.assertEqual(build_snapshot(self.rows(99),"2026-10-13",self.source())["latest"]["change"],-1)
    def test_flat(self):
        self.assertEqual(build_snapshot(self.rows(100),"2026-10-13",self.source())["latest"]["change_pct"],0)
    def test_stale(self):
        with self.assertRaises(ValueError):build_snapshot(self.rows()[:1],"2026-10-13",self.source())
    def test_duplicate(self):
        with self.assertRaises(ValueError):build_snapshot(self.rows()+self.rows(),"2026-10-13",self.source())
    def test_future(self):
        with self.assertRaises(ValueError):build_snapshot(self.rows()+[{"date":"2026-10-14","close":105}],"2026-10-13",self.source())
    def test_invalid_close(self):
        for value in [None,True,0,-1,float("nan"),float("inf"),"100"]:
            with self.subTest(value=value),self.assertRaises(ValueError):build_snapshot(self.rows(value),"2026-10-13",self.source())
    def test_wrong_source_session(self):
        source=self.source();source["session"]="2026-10-12"
        with self.assertRaises(ValueError):build_snapshot(self.rows(),"2026-10-13",source)
    def test_unknown_source(self):
        source=self.source();source["provider"]="demo"
        with self.assertRaises(ValueError):build_snapshot(self.rows(),"2026-10-13",source)
    def test_missing_previous(self):
        with self.assertRaises(ValueError):build_snapshot(self.rows()[1:],"2026-10-13",self.source())
    def test_weekend(self):
        with self.assertRaises(ValueError):build_snapshot([{"date":"2026-10-11","close":98}]+self.rows(),"2026-10-13",self.source())
    def test_sorted(self):
        self.assertEqual(build_snapshot(list(reversed(self.rows())),"2026-10-13",self.source())["latest"]["close"],101)
if __name__=="__main__":unittest.main()
