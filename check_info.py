import openstack
import json

# 1. 오픈스택 접속
conn = openstack.connect(
    auth_url='http://10.0.2.15/identity/v3',
    project_name='admin',
    username='admin',
    password='0000',
    user_domain_name='Default',
    project_domain_name='Default',
    region_name='RegionOne',
)

# 2. 서버 목록 가져오기
servers = list(conn.compute.servers())

if not servers:
    print("현재 생성된 가상머신이 없습니다.")
    print("하지만 서버가 있다면 아래와 같은 주요 정보들을 가져올 수 있습니다:")
    print("- id: 고유 식별자 (UUID)")
    print("- name: 가상머신 이름")
    print("- status: 현재 상태 (ACTIVE, BUILD, ERROR 등)")
    print("- addresses: 할당된 IP 주소 목록 (내부 IP, 외부 IP)")
    print("- flavor: CPU, RAM, 디스크 사양 정보")
    print("- image: 설치된 운영체제(OS) 이미지 정보")
    print("- created_at: 생성된 시간")
else:
    print(f"총 {len(servers)}개의 서버를 찾았습니다.\n")
    for server in servers:
        # server 객체를 파이썬 딕셔너리로 변환하여 보기 좋게 출력
        server_dict = server.to_dict()
        print(json.dumps(server_dict, indent=4, ensure_ascii=False))
