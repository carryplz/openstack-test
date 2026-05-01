import openstack

conn = openstack.connect(
    auth_url='http://10.0.2.15/identity/v3',
    project_name='admin',
    username='admin',
    password='0000',
    user_domain_name='Default',
    project_domain_name='Default',
    region_name='RegionOne',
)

server_name = "my_first_vm"
server = conn.compute.find_server(server_name)

if server:
    print(f"[{server_name}] 삭제를 요청합니다...")
    conn.compute.delete_server(server)
    print("✅ 삭제 완료!")
else:
    print("삭제할 서버가 없습니다.")
