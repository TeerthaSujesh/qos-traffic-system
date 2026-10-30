
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls
)
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ipv4
from ryu.lib.packet import udp


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

    def __init__(self, *args, **kwargs):
        super(QoSController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    def add_flow(self, datapath, priority, match, actions):
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        instructions = [
            parser.OFPInstructionActions(
                ofproto.OFPIT_APPLY_ACTIONS,
                actions
            )
        ]

        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=instructions
        )

        datapath.send_msg(mod)

    @set_ev_cls(
        ofp_event.EventOFPSwitchFeatures,
        CONFIG_DISPATCHER
    )
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

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

            self.add_flow(datapath, 10, match, actions)

        self.logger.info(
            "Switch %s connected: classification rules installed",
            datapath.id
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

                # Select OVS queue before output
                actions = [
                    parser.OFPActionSetQueue(queue_id),
                    parser.OFPActionOutput(out_port)
                ]

                priority = self.FLOW_PRIORITIES[traffic_class]

                self.add_flow(
                    datapath,
                    priority,
                    match,
                    actions
                )

                self.logger.info(
                    "INSTALLED %s FLOW: PORT %s | QUEUE %s | PRIORITY %s",
                    traffic_class,
                    traffic["dst_port"],
                    queue_id,
                    priority
                )

        elif out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_dst=dst
            )

            actions = [
                parser.OFPActionOutput(out_port)
            ]

            self.add_flow(datapath, 1, match, actions)

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
