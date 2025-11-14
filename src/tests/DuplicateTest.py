import random

from tests.BasicTest import BasicTest

"""
This tests duplicate packet delivery. Randomly duplicates some packets to
simulate network duplication.
"""
class DuplicateTest(BasicTest):
    def handle_packet(self):
        for p in self.forwarder.in_queue:
            # Always send the original packet
            self.forwarder.out_queue.append(p)
            # Randomly duplicate about 30% of packets
            if random.random() < 0.3:
                self.forwarder.out_queue.append(p)

        # Empty out the in_queue
        self.forwarder.in_queue = []