import random

from tests.BasicTest import BasicTest

"""
This tests out-of-order packet delivery in SACK mode. Packets are collected
and then sent in a random order to simulate network reordering.
"""
class SackOutOfOrderTest(BasicTest):
    def __init__(self, forwarder, input_file):
        super(SackOutOfOrderTest, self).__init__(forwarder, input_file, sackMode=True)
        self.pending_packets = []

    def handle_packet(self):
        # Collect all incoming packets
        for p in self.forwarder.in_queue:
            self.pending_packets.append(p)

        # Clear the in_queue
        self.forwarder.in_queue = []

        # If we have accumulated enough packets (e.g., 10), shuffle and send
        if len(self.pending_packets) >= 10:
            random.shuffle(self.pending_packets)
            self.forwarder.out_queue.extend(self.pending_packets)
            self.pending_packets = []

    def handle_tick(self, tick_interval):
        # At the end of the test, send any remaining packets in random order
        if self.pending_packets:
            random.shuffle(self.pending_packets)
            self.forwarder.out_queue.extend(self.pending_packets)
            self.pending_packets = []