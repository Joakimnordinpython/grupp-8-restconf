from skilla import GBG_IP, ISP_IP, STO_IP, ietf_if_path, native_if_path, request

results = []


def get_json(ip, path, quiet=False):
    resp = request("GET", ip, path, quiet=True)
    if resp is None or resp.status_code != 200:
        if not quiet and resp is not None:
            print(f"      (GET {path} på {ip} gav {resp.status_code})")
        return None
    return resp.json()


def check(ok, text):
    results.append(ok)
    if ok:
        status = "GODKÄNT"
    else:
        status = "UNDERKÄNT"
    print(f"  [{status}] {text}")
    return ok


def classify_state(state):
    if not state:
        return None
    s = str(state).lower()
    if "other" in s:
        return "DROTHER"
    if "bdr" in s:
        return "BDR"
    if s.endswith("dr"):
        return "DR"
    return s


# Hämtar OSPF oper-data
def ospf_interfaces(ip):
    data = get_json(ip, "Cisco-IOS-XE-ospf-oper:ospf-oper-data")
    if not data:
        return []
    state = data["Cisco-IOS-XE-ospf-oper:ospf-oper-data"]["ospf-state"]
    ifaces = []
    for inst in state.get("ospf-instance", []):
        for area in inst.get("ospf-area", []):
            for iface in area.get("ospf-interface", []):
                ifaces.append(iface)
    return ifaces


def configured_priority(ip, ifname):
    path = f"{native_if_path(ifname)}/ip/Cisco-IOS-XE-ospf:router-ospf/ospf/priority"
    data = get_json(ip, path, quiet=True)
    if not data:
        return 1
    return data.get("Cisco-IOS-XE-ospf:priority", 1)


# Hämtar routingtabellen
def routes(ip):
    path = "ietf-routing:routing-state/routing-instance=default/ribs/rib=ipv4-default/routes"
    data = get_json(ip, path, quiet=True)
    if not data:
        return []
    return data["ietf-routing:routes"]["route"]


def check_hostname(ip, expected):
    data = get_json(ip, "Cisco-IOS-XE-native:native/hostname")
    actual = data.get("Cisco-IOS-XE-native:hostname") if data else None
    check(actual == expected, f"hostname = {expected}")


def check_interface(ip, ifname, expected_ip):
    data = get_json(ip, ietf_if_path(ifname))
    addrs = []
    desc = None
    enabled = False

    if data:
        if_data = data["ietf-interfaces:interface"]
        desc = if_data.get("description")
        enabled = if_data.get("enabled")
        ipv4 = if_data.get("ietf-ip:ipv4", {})
        for a in ipv4.get("address", []):
            addrs.append(a.get("ip"))

    check(expected_ip in addrs and enabled == True, f"{ifname} har IP {expected_ip} och är uppe")
    check(desc is not None, f"{ifname} har description")


def check_ospf(ip, expected_rid, expected_neighbors, expected_role, expected_prio, check_cost=False):
    rid_path = "Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-ospf:router-ospf/ospf/process-id=1/router-id"
    data = get_json(ip, rid_path)
    actual_rid = data.get("Cisco-IOS-XE-ospf:router-id") if data else None
    check(actual_rid == expected_rid, f"OSPF router-id = {expected_rid}")

    ifaces = ospf_interfaces(ip)
    shared = None
    for i in ifaces:
        if i.get("name") == "GigabitEthernet0/0/0":
            shared = i
            break

    full_neighbors = []
    for i in ifaces:
        for n in i.get("ospf-neighbor", []):
            if "full" in str(n.get("state", "")).lower():
                full_neighbors.append(n.get("neighbor-id"))

    for nbr_name, nbr_id in expected_neighbors:
        check(nbr_id in full_neighbors, f"granne {nbr_name} ({nbr_id}) är FULL")

    if shared:
        state = classify_state(shared.get("state"))
        actual_dr = shared.get("dr")
        actual_bdr = shared.get("bdr")
    else:
        state = None
        actual_dr = None
        actual_bdr = None

    check(state == expected_role, f"roll på GigabitEthernet0/0/0 = {expected_role} (läst: {state})")
    check(actual_dr == "2.2.2.2", f"vald DR = 2.2.2.2 (läst: {actual_dr})")
    check(actual_bdr == "3.3.3.3", f"vald BDR = 3.3.3.3 (läst: {actual_bdr})")

    prio = configured_priority(ip, "GigabitEthernet0/0/0")
    check(prio == expected_prio, f"OSPF priority = {expected_prio} (läst: {prio})")

    if check_cost:
        oi = None
        for i in ifaces:
            if i.get("name") == "GigabitEthernet0/0/1":
                oi = i
                break
        cost_ok = oi is not None and oi.get("cost") == 14
        check(cost_ok, "OSPF cost 14 på GigabitEthernet0/0/1")


def check_default_route(ip, is_isp=False):
    default_routes = []
    for r in routes(ip):
        if r.get("destination-prefix") == "0.0.0.0/0":
            default_routes.append(r)

    if is_isp:
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

    # ISP
    print(f"\n=== ISP ({ISP_IP}) ===")
    check_hostname(ISP_IP, "ISP")
    check_interface(ISP_IP, "GigabitEthernet0/0/0", "192.168.12.1")
    check_interface(ISP_IP, "Loopback0", "172.16.0.1")
    check_ospf(ISP_IP, "1.1.1.1", [("STO", "2.2.2.2"), ("GBG", "3.3.3.3")], "DROTHER", 0)
    check_default_route(ISP_IP, is_isp=True)

    # STO
    print(f"\n=== STO ({STO_IP}) ===")
    check_hostname(STO_IP, "STO")
    check_interface(STO_IP, "GigabitEthernet0/0/0", "192.168.12.2")
    check_interface(STO_IP, "Loopback0", "172.17.0.1")
    check_ospf(STO_IP, "2.2.2.2", [("ISP", "1.1.1.1"), ("GBG", "3.3.3.3")], "DR", 255)
    check_default_route(STO_IP, is_isp=False)

    # GBG
    print(f"\n=== GBG ({GBG_IP}) ===")
    check_hostname(GBG_IP, "GBG")
    check_interface(GBG_IP, "GigabitEthernet0/0/0", "192.168.12.3")
    check_interface(GBG_IP, "GigabitEthernet0/0/1", "12.12.12.13")
    check_interface(GBG_IP, "Loopback0", "172.18.0.1")
    check_ospf(GBG_IP, "3.3.3.3", [("ISP", "1.1.1.1"), ("STO", "2.2.2.2")], "BDR", 1, check_cost=True)
    check_default_route(GBG_IP, is_isp=False)

    ok = sum(results)
    total = len(results)
    print(f"\nRESULTAT: {ok}/{total}")
    if ok == total:
        print("BETYG: GODKÄNT (G)")
    else:
        print("BETYG: UNDERKÄNT - fixa felen och kör igen")


if __name__ == "__main__":
    main()
