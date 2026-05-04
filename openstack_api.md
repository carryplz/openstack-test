devstack과 openstacksdk를 통해 검증하였습니다.

궁금한점 - api를 사용해야 하는지? SDK까지는 사용해도 되는지?

horizon 대시보드에서 사용자가 생성을 요청하면
사용자의 token과 auth_url 값을 가지고 openstack.connect를 통해 연결하여
생성이 가능한 이미지, 네트워크, 사양을 조회한 후 사용자가 선택하면 그 값으로 VM을 생성

![alt text](image-1.png)


| 자원 구분 | 서비스 | Method | API Endpoint | 용도 |
| :--- | :--- | :--- | :--- | :--- |
| **인증** | Keystone | `POST` | `/v3/auth/tokens` | 모든 요청의 시작, `X-Auth-Token` 발급 |
| **이미지** | Glance | `GET` | `/v2/images` | 사용 가능한 OS 이미지 목록 조회 |
| **사양** | Nova | `GET` | `/v2.1/flavors/detail` | vCPU, RAM 등 상세 스펙을 포함한 사양 조회 |
| **네트워크** | Neutron | `GET` | `/v2.0/networks` | 가상 L2 네트워크 목록 조회 |
| **서브넷** | Neutron | `GET` | `/v2.0/subnets` | VM 생성 시 network당 subnet 명시에 사용 |
| **보안 그룹** | Neutron | `GET` | `/v2.0/security-groups` | 방화벽 정책 및 규칙 목록 조회 |
| **키페어** | Nova | `GET` | `/v2.1/os-keypairs` | SSH 접속을 위한 공개키 목록 조회 |
| **가용 구역** | Nova | `GET` | `/v2.1/os-availability-zone/detail` | 물리적 인프라 구역(AZ) 상세 정보 조회 |
| **유동 IP** | Neutron | `GET` | `/v2.0/floatingips?status=DOWN` | VM에 미연결된 사용 가능한 공인 IP 목록 조회 |
| **VM 생성** | Nova | `POST` | `/v2.1/servers` | 위 자원 선택값으로 VM 인스턴스 생성 |
| **유동 IP 연결** | Neutron | `PUT` | `/v2.0/floatingips/{id}` | VM ACTIVE 확인 후 공인 IP 연결 |

이미지와 사양은 미리 만들어둔 것에서만 선택이 가능
나머지는 사용자가 생성 가능


