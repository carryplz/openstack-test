import os
import openstack


def create_full_stack_vm():
    # -------------------------
    # 1. OpenStack 연결
    # TODO: 실제 서비스에서는 admin 하드코딩 대신 사용자 token + auth_url로 교체
    # conn = openstack.connect(auth_url=auth_url, token=token)
    # -------------------------
    conn = openstack.connect(
        auth_url='http://10.0.2.15/identity/v3',
        project_name='admin',
        username='admin',
        password='0000',
        user_domain_name='Default',
        project_domain_name='Default',
        region_name='RegionOne'
    )
    print("--- ZIASTACK 통합 생성 프로세스 시작 ---")

    # -------------------------
    # 2. 필수 자원 설정 (사용자 선택값 가정)
    # TODO: 실제 서비스에서는 사용자가 조회 후 선택한 값을 파라미터로 받아야 함
    # -------------------------
    image_id    = "617ca135-93ac-433c-954e-f4dab3db0089"
    flavor_id   = "1"
    network_id  = "5ae8952f-cbae-47ef-8f80-4fa67168c064"  # my_test 네트워크
    key_name    = "ziastack-key"
    sg_name     = "ziastack-sg"
    router_name = "ziastack-router"

    # -------------------------
    # 3-1. 키페어 체크 및 생성
    # -------------------------
    if not conn.compute.find_keypair(key_name):
        print(f"[*] 키페어({key_name})가 없어 새로 생성합니다.")
        keypair = conn.compute.create_keypair(name=key_name)

        # private key는 생성 시 딱 한 번만 반환됨 → 반드시 저장
        pem_path = f"{key_name}.pem"
        with open(pem_path, "w") as f:
            f.write(keypair.private_key)
        os.chmod(pem_path, 0o600)  # SSH 접속 시 권한 문제 방지
        print(f"    - 키페어 생성 완료 (저장 경로: {pem_path})")
    else:
        print(f"[*] 기존 키페어({key_name})를 사용합니다.")

    # -------------------------
    # 3-2. 보안 그룹 체크 및 생성
    # -------------------------
    sg = conn.network.find_security_group(sg_name)
    if not sg:
        print(f"[*] 보안 그룹({sg_name})을 생성하고 규칙을 추가합니다.")
        sg = conn.network.create_security_group(
            name=sg_name,
            description="ZIASTACK Default SG"
        )

        # SSH (TCP 22) 인바운드 허용
        conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction='ingress',
            protocol='tcp',
            port_range_min=22,
            port_range_max=22,
            remote_ip_prefix='0.0.0.0/0'
        )

        # ICMP (ping) 인바운드 허용 → VM 생존 확인용
        conn.network.create_security_group_rule(
            security_group_id=sg.id,
            direction='ingress',
            protocol='icmp',
            remote_ip_prefix='0.0.0.0/0'
        )
        print(f"    - 보안 그룹 생성 완료 (SSH, ICMP 허용)")
    else:
        print(f"[*] 기존 보안 그룹({sg_name})을 사용합니다.")

    # -------------------------
    # 3-3. 외부 네트워크 확인
    # Floating IP 생성/연결에 필요 → 라우터 생성 전에 미리 확인
    # -------------------------
    public_net = conn.network.find_network("public", is_router_external=True)
    if not public_net:
        raise ValueError("[오류] 외부 네트워크 'public'을 찾을 수 없습니다. 네트워크 이름을 확인하세요.")

    # -------------------------
    # 3-4. 라우터 체크 및 생성
    # my_test 네트워크 ↔ public 네트워크 연결용
    # 라우터 없으면 Floating IP 연결 불가 (subnet not reachable 에러)
    # -------------------------
    router = conn.network.find_router(router_name)
    if not router:
        print(f"[*] 라우터({router_name})를 생성하고 외부 네트워크에 연결합니다.")

        # 라우터 생성 + 외부 게이트웨이(public) 설정
        router = conn.network.create_router(
            name=router_name,
            external_gateway_info={"network_id": public_net.id}
        )

        # my_test 네트워크의 서브넷 찾기
        subnets = list(conn.network.subnets(network_id=network_id))
        if not subnets:
            raise ValueError("[오류] my_test 네트워크에 서브넷이 없습니다.")

        subnet = subnets[0]

        # 라우터에 서브넷 연결 (인터페이스 추가)
        conn.network.add_interface_to_router(router, subnet_id=subnet.id)
        print(f"    - 라우터 생성 완료 (서브넷 {subnet.cidr} 연결됨)")
    else:
        print(f"[*] 기존 라우터({router_name})를 사용합니다.")

    # -------------------------
    # 4. VM 인스턴스 생성
    # -------------------------
    print(f"[*] VM 생성을 요청합니다... (Image: {image_id})")
    server = conn.compute.create_server(
        name="ZIASTACK-Recovered-VM",
        image_id=image_id,
        flavor_id=flavor_id,
        networks=[{"uuid": network_id}],
        key_name=key_name,
        security_groups=[{"name": sg.name}]
    )

    # -------------------------
    # 5. ACTIVE 상태 대기
    # 타임아웃 없으면 VM이 ERROR로 빠졌을 때 무한 대기 가능
    # -------------------------
    print("[*] VM이 ACTIVE 상태가 될 때까지 대기합니다. (최대 300초)")
    try:
        server = conn.compute.wait_for_server(
            server,
            status='ACTIVE',
            wait=300,    # 최대 5분
            interval=5,  # 5초마다 상태 체크
        )
        print(f"    - VM 생성 완료 (Status: ACTIVE, ID: {server.id})")
    except Exception as e:
        print(f"    - [오류] VM이 ACTIVE 상태가 되지 않았습니다: {e}")
        raise

    # -------------------------
    # 6. Floating IP 확보
    # openstacksdk 4.12.0 실제 확인된 메서드명:
    #   조회: conn.network.ips()       (floating_ips() 없음)
    #   생성: conn.network.create_ip() (create_floating_ip() 없음)
    #   연결: conn.network.update_ip() (update_floating_ip() 없음)
    # 사용 가능한 IP(status=DOWN) 우선 재사용, 없으면 신규 할당
    # -------------------------
    print("[*] 유동 IP를 확보합니다.")
    available_ips = list(conn.network.ips(status='DOWN'))

    if available_ips:
        fip = available_ips[0]
        print(f"    - 기존 유동 IP 재사용: {fip.floating_ip_address}")
    else:
        fip = conn.network.create_ip(floating_network_id=public_net.id)
        print(f"    - 신규 유동 IP 할당 완료: {fip.floating_ip_address}")

    # -------------------------
    # 7. Floating IP 연결 (Neutron 방식)
    # VM의 port를 직접 찾아서 연결
    # Nova의 add_floating_ip_to_server()는 deprecated라 사용 안 함
    # -------------------------
    print("[*] 유동 IP를 VM에 연결합니다.")
    ports = list(conn.network.ports(device_id=server.id))
    if not ports:
        raise RuntimeError("[오류] VM에 연결된 포트를 찾을 수 없습니다.")

    port = ports[0]
    conn.network.update_ip(fip.id, port_id=port.id)
    print(f"    - 연결 완료! 접속 IP: {fip.floating_ip_address}")

    print("\n--- 모든 복구 프로세스가 성공적으로 완료되었습니다 ---")
    print(f"    SSH 접속: ssh -i {key_name}.pem cirros@{fip.floating_ip_address}")


if __name__ == "__main__":
    create_full_stack_vm()
