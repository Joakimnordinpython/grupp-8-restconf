from common import get_json, ietf_if_path, native_if_path, walk, walk_items
from skilla import DEVICES

results = []


def check(ok, text):
    results.append(ok)
    if ok:
        status = "GODKÄNT"
    else:
        status = "UNDERKÄNT"
    print(f"  [{status}] {text}")
    return ok


def first(obj, key):
    for val in walk(obj, key):
        return val
    return None


def classify_state(state):
    if not state:
        return None
    s = str(state).lower()
    if "other" in s:
        return "DROTHER"
    if "bdr" in s or "backup" in s:
        return "BDR"
    if s.endswith("dr"):
        return "DR"
    return s


def expected_router_id(role):
    for cfg in DEVICES.values():
        if cfg["ospf"]["role"] == role:
            return cfg["router_id"]
    return None


def ospf_interfaces(ip):
    data = get_json(ip, "Cisco-IOS-XE-ospf-oper:ospf-oper-data")
    if not data:
        return []
    return list(walk_items(data, "ospf-interface"))


def configured_priority(ip, ifname):
    path = f"{native_if_path(ifname)}/ip/Cisco-IOS-XE-ospf:router-ospf/ospf/priority"
    data = get_json(ip, path, quiet=True)
    if not data:
        return 1
    val = first(data, "priority")
    if val is None:
        return 1
    return val


def routes(ip):
    paths = [
        "ietf-routing:routing-state/routing-instance=default/ribs/rib=ipv4-default/routes",
        "ietf-routing:routing/routing-instance=default/ribs/rib=ipv4-default/routes",
    ]
    for path in paths:
        data = get_json(ip, path, quiet=True)
        if data:
            return list(walk_items(data, "route"))
    return []


def grade_device(name, cfg):
    ip = cfg["mgmt_ip"]
    print(f"\n=== {name} ({ip}) ===")

    data = get_json(ip, "Cisco-IOS-XE-native:native/hostname")
    actual_host = first(data, "hostname")
    check(actual_host == cfg["hostname"], f"hostname = {cfg['hostname']}")

    for iface in cfg["interfaces"]:
        data = get_json(ip, ietf_if_path(iface["name"]))
        addrs = []
        desc = None
        enabled = None

        if data:
            for a in walk_items(data, "address"):
                addrs.append(a.get("ip"))
            desc = first(data, "description")
            enabled = first(data, "enabled")

        is_up_and_ip = (iface["ip"] in addrs) and (enabled is True)
        check(is_up_and_ip, f"{iface['name']} har IP {iface['ip']} och är uppe")
        check(bool(desc), f"{iface['name']} har description")

    rid_path = "Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-ospf:router-ospf/ospf/process-id=1/router-id"
    data = get_json(ip, rid_path)
    check(first(data, "router-id") == cfg["router_id"], f"OSPF router-id = {cfg['router_id']}")

    ifaces = ospf_interfaces(ip)
    shared = None
    for i in ifaces:
        if i.get("name") == cfg["shared_if"]:
            shared = i
            break

    full_neighbors = set()
    for i in ifaces:
        for n in walk_items(i, "ospf-neighbor"):
            n_state = str(n.get("state", ""))
            if n_state.endswith("full"):
                full_neighbors.add(n.get("neighbor-id"))

    for other, ocfg in DEVICES.items():
        if other != name:
            check(ocfg["router_id"] in full_neighbors, f"granne {other} ({ocfg['router_id']}) är FULL")

    role = cfg["ospf"]["role"]
    if shared:
        state = classify_state(shared.get("state"))
        actual_dr = shared.get("dr")
        actual_bdr = shared.get("bdr")
    else:
        state = None
        actual_dr = None
        actual_bdr = None

    check(state == role, f"roll på {cfg['shared_if']} = {role} (läst: {state})")

    dr_id = expected_router_id("DR")
    bdr_id = expected_router_id("BDR")
    check(shared is not None and str(actual_dr) == dr_id, f"vald DR = {dr_id} (läst: {actual_dr})")
    check(shared is not None and str(actual_bdr) == bdr_id, f"vald BDR = {bdr_id} (läst: {actual_bdr})")

    prio = configured_priority(ip, cfg["shared_if"])
    check(prio == cfg["ospf"]["priority"], f"OSPF priority = {cfg['ospf']['priority']} (läst: {prio})")

    for iface in cfg["interfaces"]:
        if "ospf_cost" in iface:
            oi = None
            for i in ifaces:
                if i.get("name") == iface["name"]:
                    oi = i
                    break
            cost_ok = oi is not None and oi.get("cost") == iface["ospf_cost"]
            check(cost_ok, f"OSPF cost {iface['ospf_cost']} på {iface['name']}")

    default_routes = []
    for r in routes(ip):
        if r.get("destination-prefix") == "0.0.0.0/0":
            default_routes.append(r)

    if cfg["ospf"].get("default_route"):
        check(len(default_routes) > 0, "default route 0.0.0.0/0 finns (statisk mot Loopback0)")
    else:
        via_ospf = False
        for r in default_routes:
            proto = str(r.get("source-protocol", "")).lower()
            if "ospf" in proto:
                via_ospf = True
                break
        check(via_ospf, "default route 0.0.0.0/0 inlärd via OSPF")


def main():
    print("RÄTTNING - ARS110 OSPF-skill")
    for name, cfg in DEVICES.items():
        grade_device(name, cfg)

    ok = sum(results)
    total = len(results)
    print(f"\nRESULTAT: {ok}/{total}")
    if ok == total:
        print("BETYG: GODKÄNT (G)")
    else:
        print("BETYG: UNDERKÄNT - fixa felen och kör igen")


if __name__ == "__main__":
    main()

