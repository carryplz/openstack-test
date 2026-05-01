import openstack
import json

conn = openstack.connect(
    auth_url='http://10.0.2.15/identity/v3',
    project_name='admin',
    username='admin',
    password='0000',
    user_domain_name='Default',
    project_domain_name='Default',
    region_name='RegionOne',
)

# 내 가상머신 찾기
server_name = "my_first_vm"
server = conn.compute.find_server(server_name)

if server:
    print(f"=== [{server.name}] 상세 정보 ===")
    print(f"UUID: {server.id}")
    print(f"현재 상태: {server.status} (Task: {server.task_state})")
    print(f"생성 시간: {server.created_at}")
    
    # 네트워크 IP 주소 예쁘게 뽑아내기
    print("\n[네트워크 할당 정보]")
    for net_name, ip_list in server.addresses.items():
        for ip in ip_list:
            ip_type = ip.get('OS-EXT-IPS:type', 'unknown')
            print(f" - {net_name} ({ip_type}): {ip['addr']}")
            
    # 전체 원본 데이터(JSON) 구경하기
    print("\n[전체 Raw Data (딕셔너리 형태)]")
    # server.to_dict()를 하면 파이썬에서 다루기 쉬운 딕셔너리로 싹 바뀝니다.
    print(json.dumps(server.to_dict(), indent=2, ensure_ascii=False))

else:
    print(f"{server_name} 가상머신을 찾을 수 없습니다.")
