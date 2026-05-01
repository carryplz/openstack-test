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

# 방금 에러가 난 가상머신 찾기
server = conn.compute.find_server("my_first_vm")

if server:
    print(f"현재 상태: {server.status}")
    if server.fault:
        print("\n🚨 [오류 상세 정보]")
        print(f"메시지: {server.fault.get('message')}")
        print(f"세부내용: {server.fault.get('details')}")
    else:
        print("기록된 오류 내용이 없습니다.")
else:
    print("해당 이름의 서버를 찾을 수 없습니다.")
