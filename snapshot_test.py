import os
import openstack
from datetime import datetime, timezone, timedelta


def get_connection():
    """
    [개발/테스트용] admin 계정으로 직접 연결
    TODO: 실제 서비스에서는 사용자 token + auth_url로 교체
    conn = openstack.connect(auth_url=auth_url, token=token)
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


# =============================================================
# 1. 스냅샷 생성
# =============================================================
def create_snapshot(server_name: str, shutdown_before_snapshot: bool = True):
    """
    VM 스냅샷 생성 후 Glance에 Private Image로 등록

    [흐름]
    VM 정지(선택) → 스냅샷 요청 → ACTIVE 대기 → VM 재기동(선택)

    Args:
        server_name: 스냅샷을 찍을 VM 이름
        shutdown_before_snapshot: True면 스냅샷 전 VM 정지 (데이터 정합성 보장)
                                  False면 ACTIVE 상태에서 Hot Snapshot (빠르지만 파일 깨질 위험)
    """
    conn = get_connection()
    print(f"--- 스냅샷 생성 프로세스 시작: {server_name} ---")

    # -------------------------
    # 1-1. 대상 VM 확인
    # -------------------------
    server = conn.compute.find_server(server_name)
    if not server:
        raise ValueError(f"[오류] '{server_name}' 서버를 찾을 수 없습니다.")

    original_status = server.status
    print(f"    - 대상 VM 상태: {original_status}")

    # -------------------------
    # 1-2. 스냅샷 전 VM 정지 (Cold Snapshot)
    # Hot Snapshot: ACTIVE 상태에서 찍으면 빠르지만 파일 시스템 깨질 위험 있음
    # Cold Snapshot: 정지 후 찍으면 안전하지만 서비스 중단 발생
    # -------------------------
    if shutdown_before_snapshot and original_status == 'ACTIVE':
        print("[*] 데이터 정합성을 위해 VM을 정지합니다. (Cold Snapshot)")
        conn.compute.stop_server(server)

        try:
            conn.compute.wait_for_server(
                server,
                status='SHUTOFF',
                wait=120,
                interval=3
            )
            print("    - VM 정지 완료 (SHUTOFF)")
        except Exception as e:
            raise RuntimeError(f"[오류] VM 정지 실패: {e}")
    else:
        print("[*] ACTIVE 상태에서 Hot Snapshot을 찍습니다. (파일시스템 깨질 위험 있음)")

    # -------------------------
    # 1-3. 스냅샷 생성 요청
    # 스냅샷 = Glance에 Private Image로 등록되는 것
    # create_server_image()는 생성될 이미지 ID를 즉시 반환
    # -------------------------
    today = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    snapshot_name = f"{server_name}_snapshot_{today}"

    print(f"[*] 스냅샷 생성을 요청합니다: {snapshot_name}")
    # 4.12.0에서 create_server_image()는 ID 문자열이 아닌 Image 객체를 반환
    # → .id로 명시적으로 추출해야 함
    snapshot_image_raw = conn.compute.create_server_image(server, name=snapshot_name)
    snapshot_image_id = snapshot_image_raw.id if hasattr(snapshot_image_raw, 'id') else str(snapshot_image_raw)
    print(f"    - 스냅샷 ID 발급: {snapshot_image_id}")

    # -------------------------
    # 1-4. 스냅샷 ACTIVE 대기
    # QUEUED → SAVING → ACTIVE 순서로 상태 변화
    # 디스크 크기에 따라 수 분 이상 걸릴 수 있음
    # -------------------------
    print("[*] 스냅샷이 ACTIVE 상태가 될 때까지 대기합니다. (최대 600초)")
    try:
        # wait_for_image() → 4.12.0에서 없음
        # wait_for_status()로 대체 (실제 dir(conn.image)로 확인)
        snapshot_image = conn.image.get_image(snapshot_image_id)
        conn.image.wait_for_status(
            snapshot_image,
            status='active',
            failures=['killed', 'deleted'],
            wait=600,     # 최대 10분
            interval=10   # 10초마다 상태 체크
        )
        print(f"    - 스냅샷 저장 완료! (ID: {snapshot_image_id})")
    except Exception as e:
        raise RuntimeError(f"[오류] 스냅샷 ACTIVE 대기 실패: {e}")

    # -------------------------
    # 1-5. VM 재기동 (정지했던 경우만)
    # -------------------------
    if shutdown_before_snapshot and original_status == 'ACTIVE':
        print("[*] 스냅샷 완료. VM을 재기동합니다.")
        conn.compute.start_server(server)

        try:
            conn.compute.wait_for_server(
                server,
                status='ACTIVE',
                wait=120,
                interval=3
            )
            print("    - VM 재기동 완료 (ACTIVE)")
        except Exception as e:
            print(f"    - [경고] VM 재기동 실패: {e} (수동으로 확인 필요)")

    print(f"\n--- 스냅샷 생성 완료 ---")
    print(f"    스냅샷 이름: {snapshot_name}")
    print(f"    스냅샷 ID  : {snapshot_image_id}")
    return snapshot_image_id


# =============================================================
# 2. 스냅샷 기반 복구 VM 생성
# =============================================================
def recover_from_snapshot(
    snapshot_image_id: str,
    original_server_name: str,
    isolated_network: bool = False
):
    """
    스냅샷 이미지로 복구 VM 생성

    [흐름]
    원본 VM 정보 조회 → 격리 네트워크 선택(선택) → 복구 VM 생성 → Floating IP 연결

    Args:
        snapshot_image_id: create_snapshot()에서 반환된 스냅샷 ID
        original_server_name: 원본 VM 이름 (사양/보안그룹/키페어 참조용)
        isolated_network: True면 격리된 테스트 네트워크에 배포 (네트워크 충돌 방지)
                          False면 원본과 동일한 네트워크에 배포 (실제 재난 복구 시)
    """
    conn = get_connection()
    print(f"\n--- 스냅샷 기반 복구 프로세스 시작 ---")

    # -------------------------
    # 2-1. 스냅샷 이미지 유효성 확인
    # -------------------------
    # snapshot_image_id가 객체로 넘어온 경우 .id 추출
    if hasattr(snapshot_image_id, 'id'):
        snapshot_image_id = snapshot_image_id.id
    snapshot = conn.image.get_image(snapshot_image_id)
    if not snapshot or snapshot.status != 'active':
        raise ValueError(f"[오류] 스냅샷 ID '{snapshot_image_id}'가 유효하지 않거나 ACTIVE 상태가 아닙니다.")
    print(f"[*] 스냅샷 확인: {snapshot.name} (status: {snapshot.status})")

    # -------------------------
    # 2-2. 원본 VM 정보로 복구 파라미터 구성
    # 원본 VM이 죽었을 수도 있으니 try/except로 처리
    # -------------------------
    original_server = conn.compute.find_server(original_server_name)
    if not original_server:
        raise ValueError(
            f"[오류] 원본 VM '{original_server_name}'을 찾을 수 없습니다. "
            f"flavor_id, network_id, key_name, security_groups를 수동으로 지정하세요."
        )

    # server.flavor['id']가 4.12.0에서 UUID가 아닌 이름(m1.tiny)을 반환하는 문제
    # → original_name으로 flavor를 다시 조회해서 실제 ID 얻기
    flavor_name = original_server.flavor.get('original_name') or original_server.flavor.get('id')
    flavor_obj = conn.compute.find_flavor(flavor_name)
    if not flavor_obj:
        raise ValueError(f"[오류] Flavor '{flavor_name}'을 찾을 수 없습니다.")
    flavor_id = flavor_obj.id

    # key_name이 None이면 키페어 없이 생성된 VM → 파라미터에서 제외
    key_name = original_server.key_name  # None 가능

    # 보안 그룹 이름 목록 추출
    sg_names = [sg['name'] for sg in original_server.security_groups]
    security_groups = [{"name": name} for name in sg_names]

    # 네트워크 복구:
    # server.addresses = {"my_test": [{IP정보}]} 형태 → UUID가 없음
    # 반드시 find_network()로 UUID를 별도 조회해야 함
    net_name = list(original_server.addresses.keys())[0]

    # public_net은 isolated_network 여부와 관계없이 Floating IP 연결 시 필요
    # 분기 전에 미리 조회해두어야 UnboundLocalError 방지
    public_net = conn.network.find_network("public", is_router_external=True)
    if not public_net:
        raise ValueError("[오류] 외부 네트워크 'public'을 찾을 수 없습니다.")

    if isolated_network:
        # 테스트 복구: 격리된 네트워크에 배포 (원본과 충돌 방지)
        # 동시에 원본 + 복구 VM이 떠있을 때 MAC/호스트네임 충돌 방지용
        isolated_net = conn.network.find_network("isolated_test_net")
        if not isolated_net:
            print("[*] 격리 네트워크가 없어 새로 생성합니다.")
            isolated_net = conn.network.create_network(name="isolated_test_net")
            conn.network.create_subnet(
                name="isolated_test_subnet",
                network_id=isolated_net.id,
                ip_version=4,
                cidr="192.168.200.0/24",
                gateway_ip="192.168.200.1"
            )
        network_id = isolated_net.id
        print(f"[*] 격리 네트워크 사용: isolated_test_net (충돌 방지)")
    else:
        # 실제 재난 복구: 원본과 동일한 네트워크 (원본 VM이 죽은 상태여야 함)
        original_net = conn.network.find_network(net_name)
        if not original_net:
            raise ValueError(f"[오류] 네트워크 '{net_name}'을 찾을 수 없습니다.")
        network_id = original_net.id
        print(f"[*] 원본 네트워크 사용: {net_name}")

        # 라우터 체크 및 생성 (없으면 Floating IP 연결 불가)
        router_name = "ziastack-router"
        router = conn.network.find_router(router_name)
        if not router:
            print(f"[*] 라우터({router_name})가 없어 생성합니다.")
            router = conn.network.create_router(
                name=router_name,
                external_gateway_info={"network_id": public_net.id}
            )
            subnets = list(conn.network.subnets(network_id=network_id))
            if not subnets:
                raise ValueError("[오류] 네트워크에 서브넷이 없습니다.")
            conn.network.add_interface_to_router(router, subnet_id=subnets[0].id)
            print(f"    - 라우터 생성 완료 (서브넷 {subnets[0].cidr} 연결됨)")
        else:
            print(f"[*] 기존 라우터({router_name})를 사용합니다.")

    print(f"    - Flavor  : {flavor_id}")
    print(f"    - Network : {network_id}")
    print(f"    - Keypair : {key_name}")
    print(f"    - SG      : {sg_names}")

    # -------------------------
    # 2-3. 복구 VM 생성
    # image_id 자리에 Base OS 대신 snapshot_image_id 주입이 핵심
    # -------------------------
    recovered_name = f"{original_server_name}_recovered"
    print(f"\n[*] 복구 VM 생성을 요청합니다: {recovered_name}")

    # key_name이 None이면 파라미터 자체를 제외해야 함
    # Nova API는 key_name=None을 허용하지 않음 (400 BadRequest)
    server_params = dict(
        name=recovered_name,
        image_id=snapshot_image_id,   # ← 핵심: Base OS 아닌 스냅샷 ID
        flavor_id=flavor_id,
        networks=[{"uuid": network_id}],
        security_groups=security_groups
    )
    if key_name:
        server_params['key_name'] = key_name

    recovered_server = conn.compute.create_server(**server_params)

    # -------------------------
    # 2-4. ACTIVE 대기
    # -------------------------
    print("[*] 복구 VM이 ACTIVE 상태가 될 때까지 대기합니다. (최대 300초)")
    try:
        recovered_server = conn.compute.wait_for_server(
            recovered_server,
            status='ACTIVE',
            wait=300,
            interval=5
        )
        print(f"    - 복구 VM 생성 완료 (Status: ACTIVE, ID: {recovered_server.id})")
    except Exception as e:
        print(f"    - [오류] 복구 VM이 ACTIVE 상태가 되지 않았습니다: {e}")
        raise

    # -------------------------
    # 2-5. Floating IP 연결
    # 격리 네트워크 배포 시에는 외부 라우터가 없어 Floating IP 연결 생략
    # -------------------------
    if not isolated_network:
        print("[*] 유동 IP를 확보하고 복구 VM에 연결합니다.")
        public_net = conn.network.find_network("public", is_router_external=True)
        if not public_net:
            print("    - [경고] 외부 네트워크를 찾을 수 없어 Floating IP 연결을 건너뜁니다.")
        else:
            available_ips = list(conn.network.ips(status='DOWN'))
            if available_ips:
                fip = available_ips[0]
                print(f"    - 기존 유동 IP 재사용: {fip.floating_ip_address}")
            else:
                fip = conn.network.create_ip(floating_network_id=public_net.id)
                print(f"    - 신규 유동 IP 할당: {fip.floating_ip_address}")

            ports = list(conn.network.ports(device_id=recovered_server.id))
            if not ports:
                raise RuntimeError("[오류] 복구 VM에 연결된 포트를 찾을 수 없습니다.")

            conn.network.update_ip(fip.id, port_id=ports[0].id)
            print(f"    - 연결 완료! 접속 IP: {fip.floating_ip_address}")
            print(f"\n--- 복구 완료 ---")
            print(f"    SSH 접속: ssh -i {key_name}.pem <user>@{fip.floating_ip_address}")
    else:
        print("\n--- 복구 완료 (격리 네트워크, Floating IP 미연결) ---")
        print(f"    복구 VM ID: {recovered_server.id}")

    return recovered_server.id


# =============================================================
# 3. 스냅샷 라이프사이클 관리 (오래된 스냅샷 자동 삭제)
# =============================================================
def cleanup_old_snapshots(server_name: str, keep_days: int = 7):
    """
    특정 VM의 스냅샷 중 keep_days일보다 오래된 것을 자동 삭제

    스냅샷을 계속 쌓으면 Glance 스토리지 고갈 → 반드시 라이프사이클 관리 필요

    Args:
        server_name: 원본 VM 이름 (스냅샷 이름 패턴 매칭에 사용)
        keep_days: 보존 기간 (기본 7일)
    """
    conn = get_connection()
    print(f"\n--- 스냅샷 라이프사이클 관리 시작 (보존 기간: {keep_days}일) ---")

    cutoff = datetime.now(timezone.utc) - timedelta(days=keep_days)
    deleted_count = 0
    kept_count = 0

    for image in conn.image.images(visibility='private'):
        # 이름 패턴으로 해당 VM의 스냅샷만 필터링
        if not image.name.startswith(f"{server_name}_snapshot_"):
            continue

        created_at_str = image.created_at
        if not created_at_str:
            continue

        # 생성일 파싱 (예: "2026-05-02T06:04:10Z")
        try:
            created_at = datetime.fromisoformat(
                created_at_str.replace('Z', '+00:00')
            )
        except ValueError:
            print(f"    - [경고] 날짜 파싱 실패: {image.name}")
            continue

        age_days = (datetime.now(timezone.utc) - created_at).days

        if created_at < cutoff:
            print(f"    - 삭제: {image.name} (생성일: {created_at_str}, {age_days}일 경과)")
            try:
                conn.image.delete_image(image.id, ignore_missing=True)
                deleted_count += 1
            except Exception as e:
                print(f"    - [경고] 삭제 실패: {image.name} → {e}")
        else:
            print(f"    - 보존: {image.name} (생성일: {created_at_str}, {age_days}일 경과)")
            kept_count += 1

    print(f"\n--- 라이프사이클 관리 완료: 삭제 {deleted_count}개 / 보존 {kept_count}개 ---")


# =============================================================
# 실행 예시
# =============================================================
if __name__ == "__main__":

    # -------------------------------------------
    # 시나리오 A: 정기 백업 (스냅샷 생성)
    # -------------------------------------------
    # shutdown_before_snapshot=True → Cold Snapshot (안전, 서비스 잠깐 중단)
    # shutdown_before_snapshot=False → Hot Snapshot (빠름, 파일 깨질 위험)
    snapshot_id = create_snapshot(
        server_name="my_first_vm",
        shutdown_before_snapshot=True
    )

    # -------------------------------------------
    # 시나리오 B: 재난 복구 (원본 VM이 죽었을 때)
    # -------------------------------------------
    # isolated_network=False → 원본 네트워크에 바로 복구 (원본 VM 죽은 상태여야 함)
    recover_from_snapshot(
        snapshot_image_id=snapshot_id,
        original_server_name="my_first_vm",
        isolated_network=False
    )

    # -------------------------------------------
    # 시나리오 C: 테스트 복구 (원본 VM 살아있는 상태에서 검증)
    # -------------------------------------------
    # isolated_network=True → 격리 네트워크 배포 (MAC/호스트네임 충돌 방지)
    # recover_from_snapshot(
    #     snapshot_image_id=snapshot_id,
    #     original_server_name="my_first_vm",
    #     isolated_network=True
    # )

    # -------------------------------------------
    # 시나리오 D: 오래된 스냅샷 정리 (7일 초과 자동 삭제)
    # -------------------------------------------
    cleanup_old_snapshots(server_name="my_first_vm", keep_days=7)
