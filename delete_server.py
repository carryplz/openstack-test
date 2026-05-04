import openstack


def delete_full_stack():
    # -------------------------
    # 1. OpenStack 연결
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
    print("--- ZIASTACK 삭제 프로세스 시작 ---")
    print("※ 의존성 때문에 역순으로 삭제합니다: VM → Floating IP → 라우터 → 보안그룹 → 키페어\n")

    # -------------------------
    # 2. VM 삭제
    # ZIASTACK 관련 VM 전부 삭제 (ERROR 상태 포함)
    # -------------------------
    print("[1] VM 삭제")
    servers = list(conn.compute.servers(all_projects=True))
    ziastack_servers = [s for s in servers if "ZIASTACK" in s.name]

    if ziastack_servers:
        for server in ziastack_servers:
            print(f"    - 삭제 중: {server.name} (ID: {server.id}, Status: {server.status})")
            conn.compute.delete_server(server, force=True)

        # 전부 삭제될 때까지 대기
        for server in ziastack_servers:
            try:
                conn.compute.wait_for_delete(server, wait=120, interval=3)
                print(f"    - 삭제 완료: {server.name}")
            except Exception as e:
                print(f"    - [경고] {server.name} 삭제 대기 중 문제: {e}")
    else:
        print("    - 삭제할 ZIASTACK VM이 없습니다.")

    # -------------------------
    # 3. Floating IP 삭제
    # status=DOWN → 미연결 상태 IP
    # status=ACTIVE → VM에 연결됐다가 VM 삭제 후 남은 IP
    # -------------------------
    print("\n[2] Floating IP 삭제")
    fips = list(conn.network.ips())
    if fips:
        for fip in fips:
            print(f"    - 삭제 중: {fip.floating_ip_address} (Status: {fip.status})")
            try:
                conn.network.delete_ip(fip.id, ignore_missing=True)
                print(f"    - 삭제 완료: {fip.floating_ip_address}")
            except Exception as e:
                print(f"    - [경고] {fip.floating_ip_address} 삭제 실패: {e}")
    else:
        print("    - 삭제할 Floating IP가 없습니다.")

    # -------------------------
    # 4. 라우터 삭제
    # 순서: 서브넷 인터페이스 제거 → 외부 게이트웨이 제거 → 라우터 삭제
    # -------------------------
    print("\n[3] 라우터 삭제")
    router = conn.network.find_router("ziastack-router")
    if router:
        print(f"    - 라우터 발견: {router.name} (ID: {router.id})")

        # 라우터에 연결된 서브넷 인터페이스 제거
        ports = list(conn.network.ports(device_id=router.id, device_owner='network:router_interface'))
        for port in ports:
            for fixed_ip in port.fixed_ips:
                subnet_id = fixed_ip.get('subnet_id')
                if subnet_id:
                    print(f"    - 서브넷 인터페이스 제거 중: {subnet_id}")
                    try:
                        conn.network.remove_interface_from_router(router, subnet_id=subnet_id)
                    except Exception as e:
                        print(f"    - [경고] 인터페이스 제거 실패: {e}")

        # 외부 게이트웨이 제거
        if router.external_gateway_info:
            print(f"    - 외부 게이트웨이 제거 중")
            try:
                conn.network.update_router(router, external_gateway_info={})
            except Exception as e:
                print(f"    - [경고] 게이트웨이 제거 실패: {e}")

        # 라우터 삭제
        conn.network.delete_router(router, ignore_missing=True)
        print(f"    - 라우터 삭제 완료: {router.name}")
    else:
        print("    - 삭제할 ziastack-router가 없습니다.")

    # -------------------------
    # 5. 보안 그룹 삭제
    # -------------------------
    print("\n[4] 보안 그룹 삭제")
    sg = conn.network.find_security_group("ziastack-sg")
    if sg:
        conn.network.delete_security_group(sg, ignore_missing=True)
        print(f"    - 보안 그룹 삭제 완료: {sg.name}")
    else:
        print("    - 삭제할 ziastack-sg가 없습니다.")

    # -------------------------
    # 6. 키페어 삭제
    # -------------------------
    print("\n[5] 키페어 삭제")
    keypair = conn.compute.find_keypair("ziastack-key")
    if keypair:
        conn.compute.delete_keypair(keypair, ignore_missing=True)
        print(f"    - 키페어 삭제 완료: ziastack-key")

        # 로컬 pem 파일도 삭제
        import os
        pem_path = "ziastack-key.pem"
        if os.path.exists(pem_path):
            os.remove(pem_path)
            print(f"    - pem 파일 삭제 완료: {pem_path}")
    else:
        print("    - 삭제할 ziastack-key가 없습니다.")

    # -------------------------
    # 7. 최종 확인
    # -------------------------
    print("\n--- 삭제 완료. 현재 남은 자원 ---")

    remaining_servers = list(conn.compute.servers(all_projects=True))
    print(f"VM: {len(remaining_servers)}개 남음")
    for s in remaining_servers:
        print(f"    - {s.name} ({s.status})")

    remaining_routers = list(conn.network.routers())
    print(f"라우터: {len(remaining_routers)}개 남음")

    remaining_fips = list(conn.network.ips())
    print(f"Floating IP: {len(remaining_fips)}개 남음")

    print("\n--- ZIASTACK 삭제 프로세스 완료 ---")


if __name__ == "__main__":
    delete_full_stack()
