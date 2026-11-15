import json
import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

HEADERS = {
    "Accept": "application/yang-data+json",
    "Content-Type": "application/yang-data+json",
}

ISP_IP = "192.168.1.11"
STO_IP = "192.168.1.12"
GBG_IP = "192.168.1.13"

USER = input("Användarnamn: ")
PASS = input("Lösenord: ")


def ietf_if_path(name):
    fixed_name = name.replace("/", "%2F")
    return f"ietf-interfaces:interfaces/interface={fixed_name}"


def native_if_path(name):
    if name.startswith("GigabitEthernet"):
        if_num = name.replace("GigabitEthernet", "").replace("/", "%2F")
        return f"Cisco-IOS-XE-native:native/interface/GigabitEthernet={if_num}"
    if name.startswith("Loopback"):
        if_num = name.replace("Loopback", "")
        return f"Cisco-IOS-XE-native:native/interface/Loopback={if_num}"
    return f"Cisco-IOS-XE-native:native/interface/{name}"


def request(method, ip, path, payload=None, quiet=False):
    url = f"https://{ip}/restconf/data/{path}"
    body = json.dumps(payload) if payload is not None else None

    resp = requests.request(
        method,
        url,
        auth=(USER, PASS),
        headers=HEADERS,
        verify=False,
        data=body,
    )

    if not quiet and method != "GET":
        if resp.status_code in (200, 201, 204):
            print(f"[OK]  {method} {path}")
        else:
            print(f"[FEL] {method} {path} -> {resp.status_code}")
            print(resp.text)
    return resp


# Sätter hostname
def configure_hostname(ip, hostname):
    print(f"  Sätter hostname till {hostname}")
    payload = {"Cisco-IOS-XE-native:hostname": hostname}
    request("PUT", ip, "Cisco-IOS-XE-native:native/hostname", payload)


# Konfigurerar interface med IP och no shutdown
def configure_interface(ip, name, desc, ip_addr, mask):
    print(f"  Konfigurerar interface {name}")
    if name.startswith("Loopback"):
        if_type = "iana-if-type:softwareLoopback"
    else:
        if_type = "iana-if-type:ethernetCsmacd"

    payload = {
        "ietf-interfaces:interface": {
            "name": name,
            "description": desc,
            "type": if_type,
            "enabled": True,
            "ietf-ip:ipv4": {
                "address": [
                    {
                        "ip": ip_addr,
                        "netmask": mask,
                    }
                ]
            },
        }
    }
    request("PUT", ip, ietf_if_path(name), payload)


# Startar OSPF process 1
def configure_ospf_process(ip, router_id, networks, default_route=False):
    print("  Konfigurerar OSPF process 1")
    entry = {
        "id": 1,
        "router-id": router_id,
        "network": networks,
    }

    if default_route:
        entry["default-information"] = {"originate": {"always": [None]}}

    path = "Cisco-IOS-XE-native:native/router/Cisco-IOS-XE-ospf:router-ospf/ospf/process-id=1"
    request("PUT", ip, path, {"Cisco-IOS-XE-ospf:process-id": [entry]})


def configure_ospf_priority(ip, ifname, priority):
    print(f"  Sätter OSPF priority {priority} på {ifname}")
    path = f"{native_if_path(ifname)}/ip/Cisco-IOS-XE-ospf:router-ospf/ospf/priority"
    request("PUT", ip, path, {"Cisco-IOS-XE-ospf:priority": priority})


def configure_ospf_cost(ip, ifname, cost):
    print(f"  Sätter OSPF cost {cost} på {ifname}")
    path = f"{native_if_path(ifname)}/ip/Cisco-IOS-XE-ospf:router-ospf/ospf/cost"
    request("PUT", ip, path, {"Cisco-IOS-XE-ospf:cost": cost})


# Statisk default route på ISP
def configure_default_route(ip):
    print("  Lägger till default route 0.0.0.0/0 -> Loopback0")
    path = "Cisco-IOS-XE-native:native/ip/route/ip-route-interface-forwarding-list=0.0.0.0,0.0.0.0"
    payload = {
        "Cisco-IOS-XE-native:ip-route-interface-forwarding-list": [
            {
                "prefix": "0.0.0.0",
                "mask": "0.0.0.0",
                "fwd-list": [{"fwd": "Loopback0"}],
            }
        ]
    }
    request("PUT", ip, path, payload)


def main():
    print("Startar konfiguration med RESTCONF...\n")

    # ISP
    print(f"--- ISP ({ISP_IP}) ---")
    configure_hostname(ISP_IP, "ISP")
    configure_interface(ISP_IP, "GigabitEthernet0/0/0", "Lank till gemensamt nat (switch)", "192.168.12.1", "255.255.255.0")
    configure_interface(ISP_IP, "Loopback0", "Internet (simulerat)", "172.16.0.1", "255.255.0.0")
    configure_ospf_process(ISP_IP, "1.1.1.1", [
        {"ip": "192.168.12.0", "wildcard": "0.0.0.255", "area": 0},
        {"ip": "172.16.0.0", "wildcard": "0.0.255.255", "area": 0},
    ], default_route=True)
    configure_ospf_priority(ISP_IP, "GigabitEthernet0/0/0", 0)
    configure_default_route(ISP_IP)
    print()

    # STO
    print(f"--- STO ({STO_IP}) ---")
    configure_hostname(STO_IP, "STO")
    configure_interface(STO_IP, "GigabitEthernet0/0/0", "Lank till gemensamt nat (switch)", "192.168.12.2", "255.255.255.0")
    configure_interface(STO_IP, "Loopback0", "Lokal loopback STO", "172.17.0.1", "255.255.0.0")
    configure_ospf_process(STO_IP, "2.2.2.2", [
        {"ip": "192.168.12.0", "wildcard": "0.0.0.255", "area": 0},
        {"ip": "172.17.0.0", "wildcard": "0.0.255.255", "area": 0},
    ])
    configure_ospf_priority(STO_IP, "GigabitEthernet0/0/0", 255)
    print()

    # GBG
    print(f"--- GBG ({GBG_IP}) ---")
    configure_hostname(GBG_IP, "GBG")
    configure_interface(GBG_IP, "GigabitEthernet0/0/0", "Lank till gemensamt nat (switch)", "192.168.12.3", "255.255.255.0")
    configure_interface(GBG_IP, "GigabitEthernet0/0/1", "Lank till PC", "12.12.12.13", "255.255.255.252")
    configure_interface(GBG_IP, "Loopback0", "Lokal loopback GBG", "172.18.0.1", "255.255.0.0")
    configure_ospf_process(GBG_IP, "3.3.3.3", [
        {"ip": "192.168.12.0", "wildcard": "0.0.0.255", "area": 0},
        {"ip": "12.12.12.12", "wildcard": "0.0.0.3", "area": 0},
        {"ip": "172.18.0.0", "wildcard": "0.0.255.255", "area": 0},
    ])
    configure_ospf_cost(GBG_IP, "GigabitEthernet0/0/1", 14)
    print()


if __name__ == "__main__":
    main()
