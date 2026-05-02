import openstack


# TODO: 실제 사용 시 token과 auth_url을 파라미터로 받아야 함
# def get_openstack_connection(token: str, auth_url: str):
#     return openstack.connect(
#         auth_url=auth_url,
#         token=token,
#     )
def get_openstack_connection():
    """
    [개발/테스트용] admin 계정으로 직접 연결
    실제 서비스에서는 Horizon에서 넘어온 사용자 token + auth_url 기반으로 교체 필요
    """
    return openstack.connect(
        auth_url='http://10.0.2.15/identity/v3',
        project_name='admin',
        username='admin',
        password='0000',
        user_domain_name='Default',
        project_domain_name='Default',
        region_name='RegionOne'
    )


def find_all_materials():
    """
    VM 생성 전 사용자에게 보여줄 자원 목록을 조회하는 함수
    
    현재: print로 출력
    TODO: 나중에 return result 방식으로 전환
    
    result = {
        "images": [],
        "flavors": [],
        "networks": [],
        "subnets": [],
        "security_groups": [],
        "keypairs": [],
        "availability_zones": [],
        "floating_ips": [],
    }
    """

    conn = get_openstack_connection()
    print("--- OpenStack Resource Scan Start ---")

    # -------------------------
    # 1. 이미지 조회 (Glance)
    # -------------------------
    print("\n[Images]")
    try:
        # TODO: return 전환 시 → result["images"].append({...})
        for image in conn.image.images():
            print(f"  ID: {image.id} | Name: {image.name} | Status: {image.status}")
    except Exception as e:
        print(f"  [Images] 조회 실패: {e}")

    # -------------------------
    # 2. 사양 조회 (Nova Flavor)
    # -------------------------
    print("\n[Flavors]")
    try:
        # TODO: return 전환 시 → result["flavors"].append({...})
        for flavor in conn.compute.flavors():
            print(
                f"  ID: {flavor.id} | Name: {flavor.name} "
                f"| vCPUs: {flavor.vcpus} | RAM: {flavor.ram}MB | Disk: {flavor.disk}GB"
            )
    except Exception as e:
        print(f"  [Flavors] 조회 실패: {e}")

    # -------------------------
    # 3. 네트워크 조회 (Neutron)
    # -------------------------
    print("\n[Networks]")
    try:
        # TODO: return 전환 시 → result["networks"].append({...})
        for network in conn.network.networks():
            print(
                f"  ID: {network.id} | Name: {network.name} "
                f"| External: {network.is_router_external}"
            )
    except Exception as e:
        print(f"  [Networks] 조회 실패: {e}")

    # -------------------------
    # 4. 서브넷 조회 (Neutron Subnet)
    # VM 생성 시 network_id만으로는 부족하고 subnet이 여러 개일 경우 명시 필요
    # POST /v2.1/servers 의 networks[].fixed_ip 또는 subnet_id 지정에 사용
    # -------------------------
    print("\n[Subnets]")
    try:
        # TODO: return 전환 시 → result["subnets"].append({...})
        for subnet in conn.network.subnets():
            print(
                f"  ID: {subnet.id} | Name: {subnet.name} "
                f"| Network ID: {subnet.network_id} | CIDR: {subnet.cidr}"
            )
    except Exception as e:
        print(f"  [Subnets] 조회 실패: {e}")

    # -------------------------
    # 5. 보안 그룹 조회 (Neutron Security Group)
    # -------------------------
    print("\n[Security Groups]")
    try:
        # TODO: return 전환 시 → result["security_groups"].append({...})
        for sg in conn.network.security_groups():
            print(f"  ID: {sg.id} | Name: {sg.name} | Description: {sg.description}")
    except Exception as e:
        print(f"  [Security Groups] 조회 실패: {e}")

    # -------------------------
    # 6. 키페어 조회 (Nova Keypair)
    # -------------------------
    print("\n[Keypairs]")
    try:
        # TODO: return 전환 시 → result["keypairs"].append({...})
        for keypair in conn.compute.keypairs():
            print(f"  Name: {keypair.name} | Fingerprint: {keypair.fingerprint}")
    except Exception as e:
        print(f"  [Keypairs] 조회 실패: {e}")

    # -------------------------
    # 7. 가용 구역 조회 (Nova Availability Zone)
    # az.name, az.state로 직접 접근 (to_dict() 후 get() 방식은 불안정)
    # -------------------------
    print("\n[Availability Zones]")
    try:
        # TODO: return 전환 시 → result["availability_zones"].append({...})
        for az in conn.compute.availability_zones():
            available = az.state.get('available', False) if az.state else False
            print(f"  Zone: {az.name} | Available: {available}")
    except Exception as e:
        print(f"  [Availability Zones] 조회 실패: {e}")

    # -------------------------
    # 8. 플로팅 IP 조회 (Neutron Floating IP)
    # status='DOWN' → 아직 VM에 연결되지 않은 사용 가능한 IP만 조회
    # VM 생성 완료(ACTIVE 상태) 후 associate 단계에서 사용
    #
    # [Floating IP 연결 흐름]
    # 1단계: POST /v2.1/servers          → VM 생성 (fixed IP만 붙은 상태)
    # 2단계: VM이 ACTIVE 될 때까지 폴링
    # 3단계: PUT /v2.0/floatingips/{id}  → floating IP 연결
    # -------------------------
    print("\n[Floating IPs] (사용 가능한 것만)")
    try:
        # status='DOWN': API 레벨 필터 → Python 레벨 필터보다 빠름
        # (기존 port_id 필터는 전체를 가져온 후 Python에서 거르는 방식이라 느림)
        # TODO: return 전환 시 → result["floating_ips"].append({...})
        for ip in conn.network.ips(status='DOWN'):
            print(f"  ID: {ip.id} | Floating IP: {ip.floating_ip_address}")
    except Exception as e:
        print(f"  [Floating IPs] 조회 실패: {e}")

    print("\n--- OpenStack Resource Scan End ---")

    # TODO: return 전환 시 아래로 교체
    # return result


if __name__ == "__main__":
    find_all_materials()
