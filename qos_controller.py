from os_ken.base import app_manager
from os_ken.controller import ofp_event
from os_ken.controller.handler import (
    CONFIG_DISPATCHER,
    MAIN_DISPATCHER,
    set_ev_cls,
)
from os_ken.ofproto import ofproto_v1_3
from os_ken.lib.packet import (
    packet, ethernet, ether_types, ipv4, udp
)


class QosController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(QosController, self).__init__(*args, **kwargs)
        self.mac_to_port = {}

    def add_flow(self, dp, priority, match, actions):
        parser = dp.ofproto_parser
        instructions = [
            parser.OFPInstructionActions(
                dp.ofproto.OFPIT_APPLY_ACTIONS, actions
            )
        ]
        dp.send_msg(
            parser.OFPFlowMod(
                datapath=dp,
                priority=priority,
                match=match,
                instructions=instructions,
            )
        )

    @set_ev_cls(
        ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER
    )
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        parser = dp.ofproto_parser
        ofproto = dp.ofproto

        match = parser.OFPMatch()
        actions = [
            parser.OFPActionOutput(
                ofproto.OFPP_CONTROLLER,
                ofproto.OFPCML_NO_BUFFER,
            )
        ]
        self.add_flow(dp, 0, match, actions)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        parser = dp.ofproto_parser
        ofproto = dp.ofproto

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)

        if eth is None or eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        dpid = dp.id
        in_port = msg.match["in_port"]

        self.mac_to_port.setdefault(dpid, {})
        self.mac_to_port[dpid][eth.src] = in_port

        out_port = self.mac_to_port[dpid].get(
            eth.dst, ofproto.OFPP_FLOOD
        )

        actions = []
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        udp_pkt = pkt.get_protocol(udp.udp)

        queue_map = {
            5001: 3,  # High
            5002: 2,  # Medium
            5003: 1,  # Low
        }

        queue_id = None
        if ip_pkt is not None and udp_pkt is not None:
            queue_id = queue_map.get(udp_pkt.dst_port)

        if out_port != ofproto.OFPP_FLOOD and queue_id is not None:
            actions.append(parser.OFPActionSetQueue(queue_id))

        actions.append(parser.OFPActionOutput(out_port))

        if out_port != ofproto.OFPP_FLOOD:
            if ip_pkt is not None and udp_pkt is not None:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=eth.dst,
                    eth_type=ether_types.ETH_TYPE_IP,
                    ip_proto=17,
                    udp_dst=udp_pkt.dst_port,
                )
                priority = 100 if queue_id is not None else 10
            else:
                match = parser.OFPMatch(
                    in_port=in_port,
                    eth_dst=eth.dst,
                )
                priority = 10

            self.add_flow(dp, priority, match, actions)

        data = (
            msg.data
            if msg.buffer_id == ofproto.OFP_NO_BUFFER
            else None
        )

        dp.send_msg(
            parser.OFPPacketOut(
                datapath=dp,
                buffer_id=msg.buffer_id,
                in_port=in_port,
                actions=actions,
                data=data,
            )
        )
