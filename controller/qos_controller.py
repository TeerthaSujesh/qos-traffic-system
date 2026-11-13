
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls
)
from ryu.ofproto import ofproto_v1_3
from ryu.ofproto import ofproto_v1_3_parser
from ryu.lib import hub
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import udp
import time


class QoSController(app_manager.RyuApp):

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    TRAFFIC_CLASSES = {
        5001: "HIGH",
        5002: "MEDIUM",
        5003: "LOW"
    }

    FLOW_PRIORITIES = {
        "HIGH": 300,
        "MEDIUM": 200,
        "LOW": 100
    }

    QUEUE_IDS = {
        "HIGH": 3,
        "MEDIUM": 2,
        "LOW": 1
    }

    # Adaptive QoS configuration
    MONITOR_PORT = 2
    MONITOR_INTERVAL = 2
    CONGESTION_THRESHOLD_KBPS = 4500
    LOW_METER_ID = 1
    LOW_METER_RATE_KBPS = 1000

    def __init__(self, *args, **kwargs):
        super(QoSController, self).__init__(*args, **kwargs)

        self.mac_to_port = {}
        self.datapaths = {}

        # Monitoring state
        self.previous_port_stats = {}
        self.congested = {}

        # Remember installed LOW traffic flows
        self.low_flows = {}

        self.monitor_thread = hub.spawn(self._monitor)

    def add_flow(
        self,
        datapath,
        priority,
        match,
        actions,
        meter_id=None,
        command=None
    ):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        instructions = []

        # Meter instruction must precede apply-actions
        if meter_id is not None:
            instructions.append(
                parser.OFPInstructionMeter(meter_id)
            )

        instructions.append(
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        )

        if command is None:
            command = ofproto.OFPFC_ADD

        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=command,
            priority=priority,
            match=match,
            instructions=instructions
        )

        datapath.send_msg(mod)

    def install_low_meter(self, datapath):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        band = parser.OFPMeterBandDrop(
            rate=self.LOW_METER_RATE_KBPS,
            burst_size=0
        )

        meter = parser.OFPMeterMod(
            datapath=datapath,
            command=ofproto.OFPMC_ADD,
            flags=ofproto.OFPMF_KBPS,
            meter_id=self.LOW_METER_ID,
            bands=[band]
        )

        datapath.send_msg(meter)

        self.logger.info(
            "ADAPTIVE QoS: LOW traffic meter created at %s Kbps",
            self.LOW_METER_RATE_KBPS
        )

    def update_low_flow(self, datapath):
        dpid = datapath.id
        flow_data = self.low_flows.get(dpid)

        if flow_data is None:
            return

        congested = self.congested.get(dpid, False)

        meter_id = self.LOW_METER_ID if congested else None

        self.add_flow(
            datapath,
            flow_data["priority"],
            flow_data["match"],
            flow_data["actions"],
            meter_id=meter_id,
            command=datapath.ofproto.OFPFC_MODIFY
        )

        if congested:
            self.logger.warning(
                "CONGESTION RESPONSE: LOW traffic limited to %s Kbps",
                self.LOW_METER_RATE_KBPS
            )
        else:
            self.logger.info(
                "LINK RECOVERED: LOW traffic meter removed"
            )

    def _monitor(self):
        while True:
            for datapath in list(self.datapaths.values()):
                parser = datapath.ofproto_parser

                request = parser.OFPPortStatsRequest(
                    datapath,
                    0,
                    self.MONITOR_PORT
                )

                datapath.send_msg(request)

            hub.sleep(self.MONITOR_INTERVAL)

    @set_ev_cls(
        ofp_event.EventOFPPortStatsReply,
        MAIN_DISPATCHER
    )
    def port_stats_reply_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id

        now = time.monotonic()

        for stat in msg.body:
            if stat.port_no != self.MONITOR_PORT:
                continue

            current_bytes = stat.tx_bytes

            previous = self.previous_port_stats.get(dpid)

            self.previous_port_stats[dpid] = (
                current_bytes,
                now
            )

            if previous is None:
                continue

            previous_bytes, previous_time = previous
            elapsed = now - previous_time

            if elapsed <= 0:
                continue

            byte_difference = current_bytes - previous_bytes

            # Counter reset or switch restart
            if byte_difference < 0:
                continue

            rate_kbps = (
                byte_difference * 8 / elapsed / 1000
            )

            is_congested = (
                rate_kbps >= self.CONGESTION_THRESHOLD_KBPS
            )

            old_state = self.congested.get(dpid, False)

            self.logger.info(
                "PORT MONITOR: switch=%s port=%s rate=%.2f Kbps",
                dpid,
                self.MONITOR_PORT,
                rate_kbps
            )

            if is_congested != old_state:
                self.congested[dpid] = is_congested
                self.logger.warning(
                    "CONGESTION STATE CHANGED: %s",
                    "CONGESTED" if is_congested else "NORMAL"
                )

                self.update_low_flow(datapath)

    @set_ev_cls(
        ofp_event.EventOFPSwitchFeatures,
        CONFIG_DISPATCHER
    )
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        dpid = datapath.id

        self.datapaths[dpid] = datapath
        self.congested[dpid] = False

        # Install the adaptive meter
        self.install_low_meter(datapath)

        # Table-miss rule
        self.add_flow(
            datapath,
            0,
            parser.OFPMatch(),
            [
                parser.OFPActionOutput(
                    ofproto.OFPP_CONTROLLER,
                    ofproto.OFPCML_NO_BUFFER
                )
            ]
        )

        # Send classified UDP traffic to Ryu
        for port in self.TRAFFIC_CLASSES:
            match = parser.OFPMatch(
                eth_type=0x0800,
                ip_proto=17,
                udp_dst=port
            )

            actions = [
                parser.OFPActionOutput(
                    ofproto.OFPP_CONTROLLER,
                    ofproto.OFPCML_NO_BUFFER
                )
            ]

            self.add_flow(
                datapath,
                10,
                match,
                actions
            )

        self.logger.info(
            "Switch %s connected: classification rules installed",
            dpid
        )

    def classify_traffic(self, pkt):
        ip_header = pkt.get_protocol(ipv4.ipv4)
        udp_header = pkt.get_protocol(udp.udp)

        if ip_header is None or udp_header is None:
            return None

        traffic_class = self.TRAFFIC_CLASSES.get(
            udp_header.dst_port
        )

        if traffic_class is None:
            return None

        return {
            "class": traffic_class,
            "src_ip": ip_header.src,
            "dst_ip": ip_header.dst,
            "src_port": udp_header.src_port,
            "dst_port": udp_header.dst_port
        }

    @set_ev_cls(
        ofp_event.EventOFPPacketIn,
        MAIN_DISPATCHER
    )
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto
        dpid = datapath.id

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None or eth.ethertype == 0x88cc:
            return

        src = eth.src
        dst = eth.dst
        in_port = msg.match["in_port"]

        # Learn source MAC
        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][src] = in_port

        out_port = self.mac_to_port[dpid].get(
            dst,
            ofproto.OFPP_FLOOD
        )

        traffic = self.classify_traffic(pkt)

        if traffic:
            traffic_class = traffic["class"]
            queue_id = self.QUEUE_IDS[traffic_class]

            self.logger.info(
                "UDP CLASSIFIED: %s | %s:%s -> %s:%s",
                traffic_class,
                traffic["src_ip"],
                traffic["src_port"],
                traffic["dst_ip"],
                traffic["dst_port"]
            )

            if out_port != ofproto.OFPP_FLOOD:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_type=0x0800,
                    ip_proto=17,
                    ipv4_src=traffic["src_ip"],
                    ipv4_dst=traffic["dst_ip"],
                    udp_dst=traffic["dst_port"]
                )

                actions = [
                    parser.OFPActionSetQueue(queue_id),
                    parser.OFPActionOutput(out_port)
                ]

                priority = self.FLOW_PRIORITIES[traffic_class]

                meter_id = None

                if traffic_class == "LOW":
                    self.low_flows[dpid] = {
                        "match": match,
                        "actions": actions,
                        "priority": priority
                    }

                    if self.congested.get(dpid, False):
                        meter_id = self.LOW_METER_ID

                self.add_flow(
                    datapath,
                    priority,
                    match,
                    actions,
                    meter_id=meter_id
                )

                self.logger.info(
                    "INSTALLED %s FLOW: PORT %s | QUEUE %s | PRIORITY %s",
                    traffic_class,
                    traffic["dst_port"],
                    queue_id,
                    priority
                )

                if meter_id is not None:
                    self.logger.warning(
                        "LOW FLOW INSTALLED WITH CONGESTION METER"
                    )

        elif out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_dst=dst
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(
                datapath,
                1,
                match,
                actions
            )

        # Forward current packet
        actions = [
            parser.OFPActionOutput(out_port)
        ]

        data = None

        if msg.buffer_id == ofproto.OFP_NO_BUFFER:
            data = msg.data

        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )

        datapath.send_msg(out)
