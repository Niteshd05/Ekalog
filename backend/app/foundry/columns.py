"""Column schemas for positional formats (CSV/TSV).

Sources, in order: a header present in the sample itself (Zeek `#fields`, a CSV header row),
then publicly documented vendor layouts. Column names then flow through the normal synonym
dictionary to OCSF, so this stays deterministic and auditable.
"""
from __future__ import annotations

import re

_PAN_COMMON = ("future_use_1 receive_time serial type subtype future_use_2 generated_time src dst natsrc natdst "
               "rule srcuser dstuser app vsys from_zone to_zone inbound_if outbound_if log_action future_use_3 "
               "sessionid repeatcnt sport dport natsport natdport flags proto action").split()
KNOWN: dict[str, list[str]] = {
    "panos_traffic": _PAN_COMMON + ("bytes bytes_sent bytes_received packets start_time elapsed category future_use_4 "
                                    "seqno actionflags srcloc dstloc future_use_5 pkts_sent pkts_received "
                                    "session_end_reason").split(),
    "panos_threat": _PAN_COMMON + ("url threat_name category severity direction seqno actionflags srcloc dstloc "
                                   "future_use_4").split(),
    "pfsense_tcp": ("rule_number sub_rule anchor tracker interface reason action direction ip_version tos ecn ttl "
                    "ip_id offset ip_flags proto_id proto length src dst sport dport data_length tcp_flags seq_num "
                    "ack_num window urg options").split(),
    "pfsense_udp": ("rule_number sub_rule anchor tracker interface reason action direction ip_version tos ecn ttl "
                    "ip_id offset ip_flags proto_id proto length src dst sport dport data_length").split(),
}
# extra synonyms for documented column names
COLUMN_SYNONYMS = {
    "src": "src_endpoint.ip", "dst": "dst_endpoint.ip", "sport": "src_endpoint.port", "dport": "dst_endpoint.port",
    "rule": "policy.name", "srcuser": "user.name", "app": "app_name", "fromzone": "src_endpoint.zone",
    "tozone": "dst_endpoint.zone", "inboundif": "src_endpoint.interface_name",
    "outboundif": "dst_endpoint.interface_name", "interface": "src_endpoint.interface_name",
    "sessionid": "connection_info.uid", "proto": "connection_info.protocol_name", "action": "action",
    "bytes": "traffic.bytes", "bytessent": "traffic.bytes_out", "bytesreceived": "traffic.bytes_in",
    "packets": "traffic.packets", "pktssent": "traffic.packets_out", "pktsreceived": "traffic.packets_in",
    "elapsed": "duration", "srcloc": "src_endpoint.location.country", "dstloc": "dst_endpoint.location.country",
    "threatname": "finding_info.title", "severity": "severity", "sessionendreason": "status_detail",
    "receivetime": "time", "direction": "connection_info.direction", "serial": "device.uid",
    # Zeek conn.log
    "ts": "time", "uid": "connection_info.uid", "idorigh": "src_endpoint.ip", "idorigp": "src_endpoint.port",
    "idresph": "dst_endpoint.ip", "idrespp": "dst_endpoint.port", "service": "app_name", "duration": "duration",
    "origbytes": "traffic.bytes_out", "respbytes": "traffic.bytes_in", "connstate": "status_detail",
    "origpkts": "traffic.packets_out", "resppkts": "traffic.packets_in",
}

_ZEEK_FIELDS = re.compile(r"^#fields\t(.+)$")


def header_from_sample(lines: list[str]) -> tuple[list[str] | None, list[str]]:
    """Strip comment/header lines; return (column names or None, data lines)."""
    cols = None
    data = []
    for ln in lines:
        if ln.startswith("#"):
            m = _ZEEK_FIELDS.match(ln)
            if m:
                cols = m.group(1).split("\t")
            continue
        data.append(ln)
    return cols, data


def known_columns(product: str, template_words: tuple, first_comma: int) -> list[str] | None:
    lits = {w for w in template_words if w}
    if product == "PAN-OS":
        if "TRAFFIC" in lits:
            return KNOWN["panos_traffic"]
        if "THREAT" in lits:
            return KNOWN["panos_threat"]
    if product == "pfSense":
        ncols = len(template_words) - first_comma
        return KNOWN["pfsense_tcp"] if ncols >= 29 else KNOWN["pfsense_udp"]
    return None
