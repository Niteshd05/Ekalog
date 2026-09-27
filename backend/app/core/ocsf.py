"""Pinned OCSF 1.3 subset used by EKALOG (perimeter-device scope).

This module is the *closed world* the LLM is allowed to answer in: class ids and
field paths below become JSON-schema enums, so a model cannot invent a field.
"""
from __future__ import annotations

OCSF_VERSION = "1.3.0"

CLASSES: dict[int, dict] = {
    0: {"name": "Base Event", "category_uid": 0, "category": "Uncategorized", "required": []},
    2004: {"name": "Detection Finding", "category_uid": 2, "category": "Findings",
           "required": ["finding_info.title"]},
    3002: {"name": "Authentication", "category_uid": 3, "category": "Identity & Access Management",
           "required": ["user.name"]},
    4001: {"name": "Network Activity", "category_uid": 4, "category": "Network Activity",
           "required": ["src_endpoint.ip", "dst_endpoint.ip"]},
    4002: {"name": "HTTP Activity", "category_uid": 4, "category": "Network Activity",
           "required": ["http_request.url.hostname"]},
    4003: {"name": "DNS Activity", "category_uid": 4, "category": "Network Activity",
           "required": ["query.hostname"]},
}

# path -> expected value kind ("ip", "int", "str", "ts", "mac")
FIELDS: dict[str, str] = {
    "time": "ts",
    "src_endpoint.ip": "ip", "src_endpoint.port": "int", "src_endpoint.hostname": "str",
    "src_endpoint.mac": "mac", "src_endpoint.interface_name": "str", "src_endpoint.zone": "str",
    "src_endpoint.location.country": "str",
    "dst_endpoint.ip": "ip", "dst_endpoint.port": "int", "dst_endpoint.hostname": "str",
    "dst_endpoint.mac": "mac", "dst_endpoint.interface_name": "str", "dst_endpoint.zone": "str",
    "dst_endpoint.location.country": "str",
    "connection_info.protocol_name": "str", "connection_info.protocol_num": "int",
    "connection_info.uid": "str", "connection_info.direction": "str",
    "traffic.bytes_in": "int", "traffic.bytes_out": "int", "traffic.bytes": "int",
    "traffic.packets_in": "int", "traffic.packets_out": "int", "traffic.packets": "int",
    "duration": "int",
    "disposition": "str", "action": "str",
    "device.hostname": "str", "device.ip": "ip", "device.uid": "str",
    "policy.uid": "str", "policy.name": "str",
    "user.name": "str", "user.domain": "str",
    "app_name": "str", "message": "str", "status_detail": "str",
    "severity": "str",
    "finding_info.title": "str", "finding_info.uid": "str", "finding_info.types": "str",
    "http_request.url.hostname": "str", "http_request.url.path": "str", "http_request.url.url_string": "str",
    "http_request.http_method": "str", "http_request.user_agent": "str",
    "http_response.code": "int",
    "query.hostname": "str", "query.type": "str", "rcode": "str",
    "auth_protocol": "str", "logon_type": "str",
    "tunnel.ip": "ip",
}

# Normalized key (lowercase, no _ - . space) -> OCSF path. Used by the deterministic pre-labeler.
SYNONYMS: dict[str, str] = {}
_SYN_SRC = {
    "src_endpoint.ip": "srcip src srcaddr sourceip sourceaddress saddr idorigh sip clientip src_ip srcaddress",
    "dst_endpoint.ip": "dstip dst dstaddr destip destinationaddress daddr idresph dip destip dest_ip destaddr serverip",
    "src_endpoint.port": "srcport spt sport sourceport idorigp srcprt src_port",
    "dst_endpoint.port": "dstport dpt dport destport destinationport idrespp dest_port dstprt",
    "src_endpoint.hostname": "srchost shost srcname sourcehostname",
    "dst_endpoint.hostname": "dsthost dhost dstname destinationhostname hostname",
    "src_endpoint.mac": "srcmac smac",
    "dst_endpoint.mac": "dstmac dmac",
    "src_endpoint.interface_name": "srcintf ininterface inboundinterface deviceinboundinterface inif",
    "dst_endpoint.interface_name": "dstintf outinterface outboundinterface deviceoutboundinterface outif",
    "src_endpoint.zone": "fromzone srczone",
    "dst_endpoint.zone": "tozone dstzone",
    "src_endpoint.location.country": "srccountry",
    "dst_endpoint.location.country": "dstcountry",
    "connection_info.protocol_name": "protoname transport protocol",
    "connection_info.protocol_num": "proto protonum ipprotocol",
    "connection_info.uid": "sessionid flowid uid sessid session",
    "connection_info.direction": "direction dir",
    "traffic.bytes_in": "rcvdbyte bytesin bytestoclient respbytes rcvdbytes bytesrecv",
    "traffic.bytes_out": "sentbyte bytesout bytestoserver origbytes sentbytes bytessent",
    "traffic.bytes": "bytes totalbytes len",
    "traffic.packets_in": "rcvdpkt pktstoclient resppkts packetsrecv",
    "traffic.packets_out": "sentpkt pktstoserver origpkts packetssent",
    "traffic.packets": "packets pkts",
    "duration": "duration elapsed elapsedtime",
    "action": "action act deviceaction",
    "disposition": "disposition utmaction",
    "device.hostname": "devname dvchost devicehostname dvc host serial",
    "device.uid": "devid deviceid serialnumber",
    "policy.uid": "policyid ruleid rule_uid ruleuid",
    "policy.name": "policyname rule rulename cs1 aclname",
    "user.name": "user username suser duser srcuser dstuser usrname login",
    "user.domain": "domain userdomain",
    "app_name": "app application service appname",
    "message": "msg message logdesc desc description",
    "status_detail": "reason status statusdetail",
    "severity": "level severity sev pri priority",
    "finding_info.title": "signature attack attackname signaturename threatname threatid alertsignature",
    "finding_info.uid": "signatureid sid attackid",
    "finding_info.types": "category threattype alertcategory",
    "http_request.url.hostname": "httphost urlhost",
    "http_request.url.path": "url uri urlpath",
    "http_request.http_method": "method httpmethod requestmethod",
    "http_request.user_agent": "useragent httpuseragent requestclientapplication",
    "http_response.code": "status_code statuscode httpstatus",
    "query.hostname": "query rrname qname dnsquery",
    "query.type": "qtype rrtype qtypename",
    "rcode": "rcode rcodename",
    "auth_protocol": "authproto authprotocol",
    "tunnel.ip": "tunnelip assignip assignedip",
    "time": "time timestamp ts rt start eventtime date",
}
for _path, _keys in _SYN_SRC.items():
    for _k in _keys.split():
        SYNONYMS.setdefault(_k.replace("_", ""), _path)


def norm_key(k: str) -> str:
    return "".join(ch for ch in k.lower() if ch.isalnum())


# Action vocabulary -> (activity_id for 4001, disposition_id)
ACTION_MAP: dict[str, tuple[int, int]] = {
    "accept": (6, 1), "allow": (6, 1), "allowed": (6, 1), "permit": (6, 1), "permitted": (6, 1),
    "pass": (6, 1), "built": (1, 1), "open": (1, 1), "start": (1, 1),
    "teardown": (2, 1), "close": (2, 1), "end": (2, 1), "timeout": (2, 1),
    "deny": (5, 2), "denied": (5, 2), "drop": (5, 2), "dropped": (5, 2), "block": (5, 2),
    "blocked": (5, 2), "reject": (5, 2), "reset-both": (3, 2), "reset": (3, 2),
    "server-rst": (3, 1), "client-rst": (3, 1), "alert": (99, 1),
}
ACTIVITY_NAMES_4001 = {0: "Unknown", 1: "Open", 2: "Close", 3: "Reset", 4: "Fail", 5: "Refuse",
                       6: "Traffic", 7: "Listen", 99: "Other"}
DISPOSITIONS = {0: "Unknown", 1: "Allowed", 2: "Blocked", 99: "Other"}
SEVERITIES = {0: "Unknown", 1: "Informational", 2: "Low", 3: "Medium", 4: "High", 5: "Critical", 6: "Fatal"}

_SYSLOG_TO_OCSF = {0: 6, 1: 5, 2: 5, 3: 4, 4: 3, 5: 2, 6: 1, 7: 1}
_WORD_SEV = {
    "emergency": 6, "emerg": 6, "alert": 5, "critical": 5, "crit": 5, "error": 4, "err": 4,
    "high": 4, "warning": 3, "warn": 3, "medium": 3, "notice": 2, "low": 2,
    "information": 1, "informational": 1, "info": 1, "debug": 1,
}


def severity_from(value: str | int | None, kind: str = "auto") -> int:
    if value is None or value == "":
        return 0
    s = str(value).strip().lower()
    if s in _WORD_SEV:
        return _WORD_SEV[s]
    if s.isdigit():
        n = int(s)
        if kind == "pri":
            return _SYSLOG_TO_OCSF.get(n % 8, 0)
        if kind == "suricata":
            return {1: 4, 2: 3, 3: 2}.get(n, 1)
        if kind == "cef":
            return 1 if n <= 3 else 3 if n <= 6 else 4 if n <= 8 else 5
        return _SYSLOG_TO_OCSF.get(n, 0) if n <= 7 else 0
    return 0


# ---------------- nested path helpers ----------------
def set_path(obj: dict, path: str, value) -> None:
    parts = path.split(".")
    cur = obj
    for p in parts[:-1]:
        nxt = cur.get(p)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[p] = nxt
        cur = nxt
    cur[parts[-1]] = value


_MISSING = object()


def get_path(obj: dict, path: str, default=None):
    cur = obj
    for p in path.split("."):
        if not isinstance(cur, dict):
            return default
        cur = cur.get(p, _MISSING)
        if cur is _MISSING:
            return default
    return cur


def type_compatible(ocsf_path: str, slot_type: str) -> bool:
    """Gate: the LLM may not map an IP field onto a non-IP slot, etc."""
    want = FIELDS.get(ocsf_path)
    if want is None:
        return False
    if want == "ip":
        return slot_type in ("ipv4", "ipv6")
    if want == "int":
        return slot_type == "int"
    if want == "mac":
        return slot_type == "mac"
    if want == "ts":
        return slot_type in ("ts", "epoch", "float", "int")
    return True  # str accepts anything
