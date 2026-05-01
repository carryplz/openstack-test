import openstack
import sys

conn = openstack.connect(
	auth_url="http://10.0.2.15/identity/v3",
	project_name="admin",
	username="admin",
	password="0000",
	user_domain_name="Default",
	project_domain_name="Default",
	region_name="RegionOne",
)

print("open stack connect!")
NETWORK_NAME="my_test"
SUBNET_NAME="my_subnet"
CIDR="192.168.100.0/24"


try:
	print(f"\n{NETWORK_NAME} create")
	network = conn.network.find_network(NETWORK_NAME)
	if not network:
		network = conn.network.create_network(name=NETWORK_NAME)
		print(f"success network created: {network.id}")
	else:
		print(f"already network {NETWORK_NAME}")

	print(f"{SUBNET_NAME} create")
	subnet = conn.network.find_subnet(SUBNET_NAME)
	if not subnet:
		subnet = conn.network.create_subnet(
			name=SUBNET_NAME,
			network_id = network.id,
			ip_version=4,
			cidr=CIDR,
			gateway_ip="192.168.100.1"
		)
		print(f"success subnet created: {subnet.id}")
	else:
		print(f"already subnet {SUBNET_NAME}")
	print("\n all create")

except	Exception as e:
	print(f"error {e}")
	sys.exit(1)
