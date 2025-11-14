import sys
import getopt
import time

import Checksum
import BasicSender

'''
This is a skeleton sender class. Create a fantastic transport protocol here.
'''
class Sender(BasicSender.BasicSender):
    def __init__(self, dest, port, filename, debug=False, sackMode=False):
        super(Sender, self).__init__(dest, port, filename, debug)
        self.sackMode = sackMode
        
        # 滑动窗口参数
        self.window_size = 5
        self.seqno = 0  # 当前发送的序列号
        self.send_base = 0  # 窗口基序号（最小未确认包）
        
        # 数据包缓存
        self.packets = []  # 存储所有要发送的数据包
        self.send_times = {}  # 记录每个包的发送时间
        
        # 超时设置
        self.timeout = 0.5  # 500ms
        
        # SACK模式下的选择性确认
        self.sack_received = set()  # 记录已接收但乱序的包
        
        # 数据包最大载荷：1472 - len("data|0||0000000000") ≈ 1450字节
        # 保守估计，预留更多空间给序列号和校验和
        self.max_payload = 1400

    # Main sending loop.
    def start(self):
        # 1. 读取文件并分段
        self.prepare_packets()
        
        # 2. 发送start消息
        self.send_packet(0)
        
        # 3. 使用滑动窗口发送数据
        while self.send_base < len(self.packets):
            # 发送窗口内的所有未发送包
            while self.seqno < len(self.packets) and self.seqno < self.send_base + self.window_size:
                self.send_packet(self.seqno)
                self.seqno += 1
            
            # 接收ACK
            response = self.receive(timeout=0.1)
            
            if response:
                response = response.decode()
                if Checksum.validate_checksum(response):
                    self.handle_ack(response)
                else:
                    self.log("Received corrupted ACK: %s" % response)
            
            # 检查超时
            self.handle_timeout()
        
        self.log("All packets sent and acknowledged!")

    def prepare_packets(self):
        """读取文件并准备所有数据包"""
        seqno = 0
        
        # 读取所有数据
        if self.infile == sys.stdin:
            data = sys.stdin.read()
        else:
            # 以二进制模式读取以支持任意文件类型
            with open(self.infile.name, 'rb') as f:
                data = f.read().decode('latin-1')  # 使用latin-1编码保持字节一致性
        
        # 分段
        pos = 0
        while pos < len(data):
            chunk = data[pos:pos + self.max_payload]
            
            if seqno == 0:
                msg_type = 'start'
            elif pos + self.max_payload >= len(data):
                msg_type = 'end'
            else:
                msg_type = 'data'
            
            packet = self.make_packet(msg_type, seqno, chunk)
            self.packets.append(packet)
            
            pos += self.max_payload
            seqno += 1
        
        self.log("Prepared %d packets" % len(self.packets))

    def send_packet(self, seqno):
        """发送指定序列号的数据包"""
        if seqno < len(self.packets):
            packet = self.packets[seqno]
            self.send(packet)
            self.send_times[seqno] = time.time()
            self.log("Sent packet %d" % seqno)

    def handle_ack(self, response):
        """处理收到的ACK"""
        try:
            if self.sackMode and response.startswith('sack|'):
                # 处理SACK消息
                self.handle_sack(response)
            else:
                # 处理普通ACK消息
                msg_type, seqno_str, data, checksum = self.split_packet(response)
                ack_num = int(seqno_str)
                
                self.log("Received ACK: %d (send_base: %d)" % (ack_num, self.send_base))
                
                if ack_num > self.send_base:
                    # 新的ACK，滑动窗口
                    self.handle_new_ack(ack_num)
                elif ack_num == self.send_base:
                    # 重复ACK
                    self.handle_dup_ack(ack_num)
                    
        except Exception as e:
            self.log("Error handling ACK: %s" % str(e))

    def handle_sack(self, response):
        """处理SACK消息"""
        try:
            msg_type, seqno_str, data, checksum = self.split_packet(response)
            
            # 解析累积ACK和选择性ACK
            parts = seqno_str.split(';')
            cum_ack = int(parts[0])
            
            # 解析选择性ACK列表
            if len(parts) > 1 and parts[1]:
                sacks = [int(x) for x in parts[1].split(',')]
                self.sack_received.update(sacks)
            
            self.log("Received SACK: cum_ack=%d, sacks=%s" % (cum_ack, self.sack_received))
            
            # 处理累积ACK
            if cum_ack > self.send_base:
                self.handle_new_ack(cum_ack)
            
        except Exception as e:
            self.log("Error handling SACK: %s" % str(e))

    def handle_timeout(self):
        """处理超时，重传窗口内的数据包"""
        current_time = time.time()
        
        if self.sackMode:
            # SACK模式：只重传未确认的包
            for seqno in range(self.send_base, min(self.send_base + self.window_size, len(self.packets))):
                if seqno in self.send_times:
                    if current_time - self.send_times[seqno] > self.timeout:
                        # 检查是否已被SACK确认
                        if seqno not in self.sack_received:
                            self.log("Timeout! Retransmitting packet %d (SACK mode)" % seqno)
                            self.send_packet(seqno)
        else:
            # Go-Back-N模式：重传整个窗口
            if self.send_base in self.send_times:
                if current_time - self.send_times[self.send_base] > self.timeout:
                    self.log("Timeout! Retransmitting from packet %d (GBN mode)" % self.send_base)
                    # 重传窗口内的所有包
                    for seqno in range(self.send_base, min(self.seqno, len(self.packets))):
                        self.send_packet(seqno)

    def handle_new_ack(self, ack):
        """处理新的ACK，滑动窗口"""
        # 滑动窗口到ack位置
        self.send_base = ack
        
        # 清理已确认包的发送时间记录
        seqnos_to_remove = [s for s in self.send_times.keys() if s < ack]
        for s in seqnos_to_remove:
            del self.send_times[s]
        
        # 清理SACK记录中已累积确认的包
        self.sack_received = {s for s in self.sack_received if s >= ack}
        
        self.log("Window slid to %d" % self.send_base)

    def handle_dup_ack(self, ack):
        """处理重复ACK"""
        self.log("Received duplicate ACK: %d" % ack)
        # Go-Back-N中，重复ACK通常意味着丢包
        # 但我们主要依赖超时机制来处理

    def log(self, msg):
        if self.debug:
            print(msg)


'''
This will be run if you run this script from the command line. You should not
change any of this; the grader may rely on the behavior here to test your
submission.
'''
if __name__ == "__main__":
    def usage():
        print("RUDP Sender")
        print("-f FILE | --file=FILE The file to transfer; if empty reads from STDIN")
        print("-p PORT | --port=PORT The destination port, defaults to 33122")
        print("-a ADDRESS | --address=ADDRESS The receiver address or hostname, defaults to localhost")
        print("-d | --debug Print debug messages")
        print("-h | --help Print this usage message")
        print("-k | --sack Enable selective acknowledgement mode")

    try:
        opts, args = getopt.getopt(sys.argv[1:],
                               "f:p:a:dk", ["file=", "port=", "address=", "debug=", "sack="])
    except:
        usage()
        exit()

    port = 33122
    dest = "localhost"
    filename = None
    debug = False
    sackMode = False

    for o,a in opts:
        if o in ("-f", "--file="):
            filename = a
        elif o in ("-p", "--port="):
            port = int(a)
        elif o in ("-a", "--address="):
            dest = a
        elif o in ("-d", "--debug="):
            debug = True
        elif o in ("-k", "--sack="):
            sackMode = True

    s = Sender(dest, port, filename, debug, sackMode)
    try:
        s.start()
    except (KeyboardInterrupt, SystemExit):
        exit()