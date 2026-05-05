devstack과 openstacksdk를 통해 검증하였습니다.

이 문서는 OpenStack REST API와 Python SDK 구현 방식을 통합하여 비교 정리합니다. 이를 통해 개발 방식(API vs SDK) 결정에 참고할 수 있으며, 특히 장애 발생 시 자원을 재사용하는 **복구(Recovery) 로직**을 포함합니다.

> ⚠️ **SDK 버전 주의**: 이 문서의 모든 SDK 메서드는 **openstacksdk 4.12.0** 기준으로 검증되었습니다.  
> 버전에 따라 메서드명이 다를 수 있습니다. (예: `floating_ips()` → `ips()`, `create_floating_ip()` → `create_ip()`)

---

### 1. API & SDK 통합 참조 테이블

#### 1-1. 자원 조회 (Read)

| 자원 구분 | 서비스 | Method | API Endpoint | SDK 메서드 (conn.*) | 참고 코드 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **인증** | Keystone | `POST` | `/v3/auth/tokens` | `openstack.connect()` | `create_server.py` |
| **이미지** | Glance | `GET` | `/v2/images` | `image.images()` | `find_materials.py` |
| **사양** | Nova | `GET` | `/v2.1/flavors/detail` | `compute.flavors()` | `find_materials.py` |
| **네트워크** | Neutron | `GET` | `/v2.0/networks` | `network.networks()` | `create_net.py` |
| **서브넷** | Neutron | `GET` | `/v2.0/subnets` | `network.subnets()` | `create_net.py` |
| **보안 그룹** | Neutron | `GET` | `/v2.0/security-groups` | `network.security_groups()` | `create_VM.py` |
| **키페어** | Nova | `GET` | `/v2.1/os-keypairs` | `compute.keypairs()` | `create_VM.py` |
| **가용 구역** | Nova | `GET` | `/v2.1/os-availability-zone/detail` | `compute.availability_zones()` | `find_materials.py` |
| **유동 IP 조회** | Neutron | `GET` | `/v2.0/floatingips?status=DOWN` | `network.ips(status='DOWN')` | `find_materials.py` |
| **VM 상태 조회** | Nova | `GET` | `/v2.1/servers/{id}` | `compute.get_server(id)` | `check_info.py` |
| **VM 상태 대기** | Nova | `GET` | `/v2.1/servers/{id}` | `compute.wait_for_server(server, wait=300, interval=5)` | `create_VM.py` |

#### 1-2. 자원 생성 (Create)

| 자원 구분 | 서비스 | Method | API Endpoint | SDK 메서드 (conn.*) | 참고 코드 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **네트워크 생성** | Neutron | `POST` | `/v2.0/networks` | `network.create_network()` | `create_net.py` |
| **서브넷 생성** | Neutron | `POST` | `/v2.0/subnets` | `network.create_subnet()` | `create_net.py` |
| **보안 그룹 생성** | Neutron | `POST` | `/v2.0/security-groups` | `network.create_security_group()` | `create_VM.py` |
| **보안 그룹 규칙 추가** | Neutron | `POST` | `/v2.0/security-group-rules` | `network.create_security_group_rule()` | `create_VM.py` |
| **키페어 생성** | Nova | `POST` | `/v2.1/os-keypairs` | `compute.create_keypair()` | `create_VM.py` |
| **라우터 생성** | Neutron | `POST` | `/v2.0/routers` | `network.create_router()` | `create_VM.py` |
| **서브넷 연결** | Neutron | `PUT` | `/v2.0/routers/{id}/add_router_interface` | `network.add_interface_to_router()` | `create_VM.py` |
| **유동 IP 생성** | Neutron | `POST` | `/v2.0/floatingips` | `network.create_ip()` | `create_VM.py` |
| **유동 IP 연결** | Neutron | `PUT` | `/v2.0/floatingips/{id}` | `network.update_ip(fip_id, port_id=port.id)` | `create_VM.py` |
| **VM 생성** | Nova | `POST` | `/v2.1/servers` | `compute.create_server()` | `create_server.py` |

#### 1-3. 자원 삭제 (Delete)

| 자원 구분 | 서비스 | Method | API Endpoint | SDK 메서드 (conn.*) | 참고 코드 |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **VM 삭제** | Nova | `DELETE` | `/v2.1/servers/{id}` | `compute.delete_server(server, force=True)` | `delete_server.py` |
| **VM 삭제 대기** | Nova | `GET` | `/v2.1/servers/{id}` | `compute.wait_for_delete(server, wait=120)` | `delete_server.py` |
| **유동 IP 삭제** | Neutron | `DELETE` | `/v2.0/floatingips/{id}` | `network.delete_ip(fip_id)` | `delete_server.py` |
| **서브넷 제거** | Neutron | `PUT` | `/v2.0/routers/{id}/remove_router_interface` | `network.remove_interface_from_router()` | `delete_server.py` |
| **라우터 삭제** | Neutron | `DELETE` | `/v2.0/routers/{id}` | `network.delete_router(router)` | `delete_server.py` |
| **보안 그룹 삭제** | Neutron | `DELETE` | `/v2.0/security-groups/{id}` | `network.delete_security_group(sg)` | `delete_server.py` |
| **키페어 삭제** | Nova | `DELETE` | `/v2.1/os-keypairs/{id}` | `compute.delete_keypair(keypair)` | `delete_server.py` |

---

### 2. 복구 데이터 매핑 (Server Info for Recovery)

기존 VM의 상세 정보(`server`)에서 어떤 값을 추출하여 **복구(재생성)** 시 어떤 파라미터로 활용하는지 정의합니다.

| 자원 구분 | 서비스 | Method | API Endpoint | SDK 메서드 (server.*) | 복구시 활용 (Parameter) | 참고 코드 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **이미지 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.image['id']` | `image_id` | `check_info.py` |
| **사양 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.flavor['id']` | `flavor_id` | `check_info.py` |
| **네트워크 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.addresses.keys()` → `network.find_network(name).id` | `networks=[{"uuid": ...}]` | `check_info.py` |
| **키페어 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.key_name` | `key_name` | `check_info.py` |
| **보안 그룹 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.security_groups[n]['name']` | `security_groups=[{"name": ...}]` | `check_info.py` |
| **가용 구역 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.availability_zone` | `availability_zone` | `check_info.py` |

> ⚠️ **네트워크 복구 주의**: `server.addresses`는 `{네트워크이름: [IP목록]}` 형태라 UUID가 없음.  
> 반드시 `conn.network.find_network(name).id`로 한 번 더 조회해서 UUID를 얻어야 함.

---

### 3. 복구 및 안정화 로직 (Recovery Logic)

복구 프로세스의 핵심 로직과 이를 구현한 참조 코드입니다.

| 로직 구분 | 주요 내용 | 참고 소스 코드 |
| :--- | :--- | :--- |
| **Find or Create** | 자원 존재 여부 체크 후 없으면 생성 | `create_VM.py` (Keypair, SG, Router 체크 로직) |
| **IP 재사용** | `status='DOWN'` IP 우선 할당, 없으면 `create_ip()`로 신규 생성 | `create_VM.py` (Floating IP 확보 로직) |
| **의존성 삭제** | 의존 관계 고려한 역순 삭제: VM → Floating IP → 라우터 → 보안그룹 → 키페어 | `delete_server.py` |
| **상태 동기화** | `wait_for_server(wait=300, interval=5)`로 ACTIVE 대기, 타임아웃 필수 | `create_VM.py` |
| **인프라 연결** | 라우터에 서브넷 인터페이스 추가 (`add_interface_to_router`) | `create_VM.py`, `create_net.py` |
| **Floating IP 연결** | VM port 조회 후 `update_ip(fip_id, port_id=port.id)`로 연결 (Nova deprecated 방식 사용 금지) | `create_VM.py` |

---

### 4. 코드별 알려진 주의사항 (Code Notes)

| 파일 | 주의사항 |
| :--- | :--- |
| `create_server.py` | `wait_for_server()`에 `wait`, `interval` 파라미터 없음 → 타임아웃 없이 무한 대기 가능. 실서비스에선 `wait=300, interval=5` 추가 필요 |
| `create_server.py` | `conn.compute.find_image()`는 내부적으로 Glance 호출. 명시적으로 `conn.image.find_image()` 사용 권장 |
| `check_my_info.py` | `server.task_state` 속성이 SDK 버전에 따라 없을 수 있음 → `server.to_dict().get('OS-EXT-STS:task_state')` 방식이 안전 |
| `create_VM.py` | `private_key`는 `create_keypair()` 호출 시 **딱 한 번만** 반환됨. 즉시 파일로 저장 필수 |
| `delete_server.py` | 라우터 삭제 순서: 서브넷 인터페이스 제거 → 게이트웨이 제거 → 라우터 삭제. 순서 어기면 `router has active ports` 에러 |
| `find_materials.py` | 현재 `print` 방식. 실서비스 전환 시 `result dict` 반환 방식으로 교체 필요 (각 섹션 TODO 주석 참고) |

---

### 5. 구현 가이드 (Implementation Reference)

- **`find_materials.py`**: VM 생성 전 사용자에게 선택지로 제공할 모든 자원(이미지, 사양 등)을 조회하는 로직. 현재 `print` 방식이며 추후 `return result` 방식으로 전환 예정.
- **`create_net.py`**: 네트워크와 서브넷을 Find or Create 방식으로 생성. `create_VM.py`의 라우터 연결 전 선행 실행 필요.
- **`create_server.py`**: 기본 VM 생성 흐름(이미지/사양/네트워크 조회 → 생성 → ACTIVE 대기). Floating IP 연결 없는 단순 생성용.
- **`create_VM.py`**: 메인 복구 시나리오. 키페어/보안그룹/라우터 자동 생성 + VM 생성 + Floating IP 연결까지 전체 워크플로우.
- **`check_info.py`**: `to_dict()`로 VM 전체 정보를 JSON 추출. 복구에 필요한 파라미터 확인용.
- **`check_my_info.py`**: 특정 VM의 상태, IP, Raw Data를 확인. 디버깅용.
- **`check_error.py`**: VM의 `fault` 필드에서 에러 원인 추출. ERROR 상태 VM 디버깅용.
- **`delete_server.py`**: 의존성 역순 삭제 전체 자동화. 라우터 인터페이스 제거 등 까다로운 삭제 절차 포함.