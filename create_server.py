import openstack
import sys

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

SERVER_NAME = "my_first_vm"
# DevStack을 설치하면 테스트용으로 기본 제공되는 초경량 OS 이미지와 사양입니다.
IMAGE_NAME = "cirros-0.6.3-x86_64-disk" 
FLAVOR_NAME = "m1.tiny" 
NETWORK_NAME = "my_test" # 캡처 화면에서 확인한 네트워크 이름

print(f"[{SERVER_NAME}] 가상머신 생성 준비 중...")

try:
    # 2. VM을 만드는데 필요한 재료(이미지, 사양, 네트워크) 찾기
    image = conn.compute.find_image(IMAGE_NAME)
    flavor = conn.compute.find_flavor(FLAVOR_NAME)
    network = conn.network.find_network(NETWORK_NAME)

    if not all([image, flavor, network]):
        print("❌ 에러: 이미지, 사양, 네트워크 중 하나를 찾을 수 없습니다.")
        sys.exit(1)

    # 3. 가상머신 생성 API 호출!
    print("API에 가상머신 생성 요청을 보냅니다...")
    server = conn.compute.create_server(
        name=SERVER_NAME,
        image_id=image.id,
        flavor_id=flavor.id,
        networks=[{"uuid": network.id}]
    )
    
    print(f"✅ 생성 요청 성공! (임시 ID: {server.id})")
    print("가상머신이 부팅될 때까지 기다리는 중입니다... (약 10~20초 소요)")

    # 4. 서버가 완전히 켜질 때까지(ACTIVE 상태) 코드에서 대기
    server = conn.compute.wait_for_server(server)
    print(f"\n🎉 짠! 가상머신 부팅이 완료되었습니다! 현재 상태: {server.status}")

except Exception as e:
    print(f"\n❌ 오류 발생: {e}")
