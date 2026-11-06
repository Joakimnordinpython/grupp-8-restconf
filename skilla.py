from common import enc, ietf_if_path, native_if_path, request

DEVICES = {
    "ISP": {
        "mgmt_ip": "192.168.1.11",
        "hostname": "ISP",
        "router_id": "1.1.1.1",
        "shared_if": "GigabitEthernet0/0/0",
        "interfaces": [
            {
                "name": "GigabitEthernet0/0/0",
                "description": "Lank till gemensamt nat (switch)",
                "ip": "192.168.12.1",
                "mask": "255.255.255.0",
            },
            {
                "name": "Loopback0",
                "description": "Internet (simulerat)",
                "ip": "172.16.0.1",
                "mask": "255.255.0.0",
            },
        ],
        "ospf": {
            "priority": 0,
            "role": "DROTHER",
            "networks": [
                {"ip": "192.168.12.0", "wildcard": "0.0.0.255", "area": 0},
                {"ip": "172.16.0.0", "wildcard": "0.0.255.255", "area": 0},
            ],
            "default_route": True,
        },
    },
    "STO": {
        "mgmt_ip": "192.168.1.12",
        "hostname": "STO",
        "router_id": "2.2.2.2",
        "shared_if": "GigabitEthernet0/0/0",
        "interfaces": [
            {
                "name": "GigabitEthernet0/0/0",
                "description": "Lank till gemensamt nat (switch)",
                "ip": "192.168.12.2",
                "mask": "255.255.255.0",
            },
            {
                "name": "Loopback0",
                "description": "Lokal loopback STO",
                "ip": "172.17.0.1",
                "mask": "255.255.0.0",
            },
        ],
        "ospf": {
            "priority": 255,
            "role": "DR",
            "networks": [
                {"ip": "192.168.12.0", "wildcard": "0.0.0.255", "area": 0},
                {"ip": "172.17.0.0", "wildcard": "0.0.255.255", "area": 0},
            ],
        },
    },
    "GBG": {
        "mgmt_ip": "192.168.1.13",
        "hostname": "GBG",
        "router_id": "3.3.3.3",
        "shared_if": "GigabitEthernet0/0/0",
        "interfaces": [
            {
                "name": "GigabitEthernet0/0/0",
                "description": "Lank till gemensamt nat (switch)",
                "ip": "192.168.12.3",
                "mask": "255.255.255.0",
            },
            {
                "name": "GigabitEthernet0/0/1",
                "description": "Lank till PC",
                "ip": "12.12.12.13",
                "mask": "255.255.255.252",
                "ospf_cost": 14,
            },
            {
                "name": "Loopback0",
                "description": "Lokal loopback GBG",
                "ip": "172.18.0.1",
                "mask": "255.255.0.0",
            },
        ],
        "ospf": {
            "priority": 1,
            "role": "BDR",
            "networks": [
                {"ip": "192.168.12.0", "wildcard": "0.0.0.255", "area": 0},
                {"ip": "12.12.12.12", "wildcard": "0.0.0.3", "area": 0},
                {"ip": "172.18.0.0", "wildcard": "0.0.255.255", "area": 0},
            ],
        },
    },
}


def configure_hostname(ip, hostname):
    print(f"  Sätter hostname till {hostname}")
    payload = {"Cisco-IOS-XE-native:hostname": hostname}
    request("PUT", ip, "Cisco-IOS-XE-native:native/hostname", payload)


def configure_interface(ip, iface):
    print(f"  Konfigurerar interface {iface['name']}")
    if iface["name"].startswith("Loopback"):
        if_type = "iana-if-type:softwareLoopback"
    else:
        if_type = "iana-if-type:ethernetCsmacd"

    payload = {
        "ietf-interfaces:interface": {
            "name": iface["name"],
            "description": iface["description"],
            "type": if_type,
            "enabled": True,
            "ietf-ip:ipv4": {
                "address": [
                    {
                        "ip": iface["ip"],
                        "netmask": iface["mask"],
                    }
                ]
            },
        }
    }
    request("PUT", ip, ietf_if_path(iface["name"]), payload)


def configure_ospf_process(ip, router_id, ospf):
    print("  Konfigurerar OSPF process 1")
    net_list = []
    for n in ospf["networks"]:
        net_list.append({
            "ip": n["ip"],
            "wildcard": n["wildcard"],
            "area": n["area"],
        })

    entry = {
        "id": 1,
        "router-id": router_id,
        "network": net_list,
    }

    if ospf.get("default_route"):
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
    for name, cfg in DEVICES.items():
        ip = cfg["mgmt_ip"]
        print(f"--- {name} ({ip}) ---")

        configure_hostname(ip, cfg["hostname"])

        for iface in cfg["interfaces"]:
            configure_interface(ip, iface)

        configure_ospf_process(ip, cfg["router_id"], cfg["ospf"])

        if cfg["ospf"]["priority"] != 1:
            configure_ospf_priority(ip, cfg["shared_if"], cfg["ospf"]["priority"])

        for iface in cfg["interfaces"]:
            if "ospf_cost" in iface:
                configure_ospf_cost(ip, iface["name"], iface["ospf_cost"])

        if cfg["ospf"].get("default_route"):
            configure_default_route(ip)

        print()


if __name__ == "__main__":
    main()

