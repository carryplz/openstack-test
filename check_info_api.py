import requests
import json

# OpenStack 서비스별 API 엔드포인트 기본 주소 설정
AUTH_URL = 'http://10.0.2.15/identity/v3/auth/tokens'  # Keystone
NOVA_URL = 'http://10.0.2.15/compute/v2.1'             # Nova

def get_auth_token():
    """
    1. Keystone에 자격 증명을 보내 X-Auth-Token을 발급받습니다.
    """
    auth_payload = {
        "auth": {
            "identity": {
                "methods": ["password"],
                "password": {
                    "user": {
                        "name": "admin",
                        "domain": {"name": "Default"},
                        "password": "0000"
                    }
                }
            },
            "scope": {
                "project": {
                    "name": "admin",
                    "domain": {"name": "Default"}
                }
            }
        }
    }
    
    print("[*] Keystone 인증 토큰 발급 요청 중...")
    response = requests.post(AUTH_URL, json=auth_payload)
    
    if response.status_code == 201:
        # 인증 성공 시 토큰은 응답 바디가 아닌 '헤더(Headers)'에 포함되어 반환됩니다.
        token = response.headers.get('X-Subject-Token')
        print("✅ 토큰 발급 완료")
        return token
    else:
        raise Exception(f"인증 실패: {response.status_code}\n{response.text}")

def check_servers_with_api(token):
    """
    2. 발급받은 토큰을 사용해 Nova API로 서버 상세 정보를 조회합니다.
    """
    headers = {
        "X-Auth-Token": token,
        "Content-Type": "application/json"
    }
    
    print("[*] Nova API를 통해 서버 목록 상세 조회 중...")
    # 서버 상세 정보 조회 엔드포인트
    response = requests.get(f"{NOVA_URL}/servers/detail", headers=headers)
    
    if response.status_code == 200:
        servers = response.json().get('servers', [])
        if not servers:
            print("현재 생성된 가상머신이 없습니다.")
        else:
            print(f"총 {len(servers)}개의 서버를 찾았습니다.\n")
            print(json.dumps(servers, indent=4, ensure_ascii=False))
    else:
        print(f"❌ 서버 목록 조회 실패: {response.status_code}\n{response.text}")

if __name__ == "__main__":
    try:
        # 토큰을 발급받아 조회 함수에 전달
        token = get_auth_token()
        check_servers_with_api(token)
    except Exception as e:
        print(f"오류 발생: {e}")
