import random

from tests.BasicTest import BasicTest

"""
This tests duplicate packet delivery in SACK mode. Randomly duplicates some
packets to simulate network duplication.
"""
class SackDuplicateTest(BasicTest):
    def __init__(self, forwarder, input_file):
        super(SackDuplicateTest, self).__init__(forwarder, input_file, sackMode=True)

    def handle_packet(self):
        for p in self.forwarder.in_queue:
            # Always send the original packet
            self.forwarder.out_queue.append(p)
            # Randomly duplicate about 30% of packets
            if random.random() < 0.3:
                self.forwarder.out_queue.append(p)

        # Empty out the in_queue
        self.forwarder.in_queue = []