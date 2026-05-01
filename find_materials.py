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

print("🔎 [현재 사용 가능한 재료 목록 확인]\n")

print("1. 이미지(Image) 목록:")
for img in conn.compute.images():
    print(f" - {img.name}")

print("\n2. 사양(Flavor) 목록:")
for flavor in conn.compute.flavors():
    print(f" - {flavor.name}")

print("\n3. 네트워크(Network) 목록:")
for net in conn.network.networks():
    print(f" - {net.name}")

