devstack과 openstacksdk를 통해 검증하였습니다.

이 문서는 OpenStack REST API와 Python SDK 구현 방식을 통합하여 비교 정리합니다. 이를 통해 개발 방식(API vs SDK) 결정에 참고할 수 있으며, 특히 장애 발생 시 자원을 재사용하는 **복구(Recovery) 로직**을 포함합니다.

![alt text](image-1.png)

---

### 1. API & SDK 통합 참조 테이블

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
| **유동 IP 조회** | Neutron | `GET` | `/v2.0/floatingips?status=DOWN` | `network.ips(status='DOWN')` | `create_VM.py` |
| **유동 IP 생성** | Neutron | `POST` | `/v2.0/floatingips` | `network.create_ip()` | `create_VM.py` |
| **유동 IP 연결** | Neutron | `PUT` | `/v2.0/floatingips/{id}` | `network.update_ip()` | `create_VM.py` |
| **라우터 생성** | Neutron | `POST` | `/v2.0/routers` | `network.create_router()` | `create_VM.py` |
| **서브넷 연결** | Neutron | `PUT` | `/v2.0/routers/{id}/add_router_interface` | `network.add_interface_to_router()` | `create_VM.py` |
| **서브넷 제거** | Neutron | `PUT` | `/v2.0/routers/{id}/remove_router_interface` | `network.remove_interface_from_router()` | `delete_server.py` |
| **VM 생성** | Nova | `POST` | `/v2.1/servers` | `compute.create_server()` | `create_server.py` |
| **VM 상태** | Nova | `GET` | `/v2.1/servers/{id}` | `compute.wait_for_server()` | `create_server.py` |
| **자원 삭제** | 공통 | `DELETE` | `.../{id}` | `delete_...()` | `delete_server.py` |

---

### 2. 복구 데이터 매핑 (Server Info for Recovery)

기존 VM의 상세 정보(`server`)에서 어떤 값을 추출하여 **복구(재생성)** 시 어떤 파라미터로 활용하는지 정의합니다.

| 자원 구분 | 서비스 | Method | API Endpoint | SDK 메서드 (server.*) | 복구시 활용 (Parameter) | 참고 코드 |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **이미지 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.image['id']` | `image_id` | `check_info.py` |
| **사양 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.flavor['id']` | `flavor_id` | `check_info.py` |
| **네트워크 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.addresses.keys()` | `find_network(name).id` | `check_info.py` |
| **키페어 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.key_name` | `key_name` | `check_info.py` |
| **보안 그룹 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.security_groups` | `security_groups=[{"name": ...}]` | `check_info.py` |
| **가용 구역 복구** | Nova | `GET` | `/v2.1/servers/{id}` | `server.availability_zone` | `availability_zone` | `check_info.py` |

---

### 3. 복구 및 안정화 로직 (Recovery Logic)

복구 프로세스의 핵심 로직과 이를 구현한 참조 코드입니다.

| 로직 구분 | 주요 내용 | 참고 소스 코드 |
| :--- | :--- | :--- |
| **Find or Create** | 자원 존재 여부 체크 후 없으면 생성 | `create_VM.py` (Keypair, SG, Router 체크 로직) |
| **IP 재사용** | `status='DOWN'` IP 우선 할당 | `create_VM.py` (Floating IP 확보 로직) |
| **의존성 삭제** | 의존 관계 고려한 역순 삭제 | `delete_server.py` (VM -> IP -> Router 순) |
| **상태 동기화** | `wait_for_server`로 ACTIVE 대기 | `create_server.py`, `create_VM.py` |
| **인프라 연결** | 라우터에 서브넷 인터페이스 추가 | `create_VM.py`, `create_net.py` |

---

### 4. 구현 가이드 (Implementation Reference)

*   **`find_materials.py`**: VM 생성 전 사용자에게 선택지로 제공할 모든 자원(이미지, 사양 등)을 조회하는 로직을 담고 있습니다.
*   **`create_VM.py`**: 프로젝트의 메인 복구 시나리오가 구현된 코드로, 네트워크/보안 설정부터 VM 생성 및 유동 IP 연결까지의 전체 워크플로우를 참고하기 가장 좋습니다.
*   **`check_info.py`**: `to_dict()` 메서드를 사용하여 VM의 상세 정보를 JSON 형태로 추출하고, 어떤 데이터를 복구에 사용할 수 있는지 분석할 때 유용합니다.
*   **`delete_server.py`**: 자원 정리 시 라우터 인터페이스 제거 등 까다로운 삭제 절차를 안전하게 처리하는 방법을 보여줍니다.
