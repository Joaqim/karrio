import unittest
from karrio.core.utils.tracing import Tracer


class TestTracerDrainRecords(unittest.TestCase):
    def test_drain_records_returns_and_clears(self):
        """drain_records returns the buffered records and empties the buffer."""
        tracer = Tracer()

        tracer.trace({"data": "one"}, "test.key1")
        tracer.trace({"data": "two"}, "test.key2")
        first = tracer.drain_records()

        self.assertEqual(len(first), 2)
        self.assertEqual({r.key for r in first}, {"test.key1", "test.key2"})
        self.assertEqual(tracer.drain_records(), [])

    def test_records_property_does_not_drain(self):
        """The records property keeps the buffer for subsequent saves."""
        tracer = Tracer()

        tracer.trace({"data": "one"}, "test.key1")
        first = tracer.records
        second = tracer.records

        self.assertEqual(len(first), 1)
        self.assertEqual(len(second), 1)

    def test_trace_after_drain_lands_in_next_drain(self):
        """A trace recorded after a drain is returned by the next one."""
        tracer = Tracer()

        tracer.trace({"data": "one"}, "test.key1")
        tracer.drain_records()
        tracer.trace({"data": "two"}, "test.key2")
        second = tracer.drain_records()

        self.assertEqual([r.key for r in second], ["test.key2"])


if __name__ == "__main__":
    unittest.main()
