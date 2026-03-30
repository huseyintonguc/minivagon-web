import json
import base64

def decode_token(token):
    # Bearer kısmını at
    if token.startswith("Bearer "):
        token = token.split(" ")[1]

    parts = token.split(".")
    if len(parts) < 2:
        return None, None

    payload_b64 = parts[1]
    # Padding ekle
    payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)

    try:
        decoded_bytes = base64.b64decode(payload_b64)
        payload_dict = json.loads(decoded_bytes)

        user_id = payload_dict.get("sub")

        # company_id'yi privs anahtarından çek (örn: "76515000001")
        privs = payload_dict.get("privs", {})
        company_id = list(privs.keys())[0] if privs else None

        return user_id, company_id
    except Exception as e:
        print("Error decoding:", e)
        return None, None

t = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiI3NDQ3MCIsImVtbCI6InpvaGdsb2JhbHBhemFybGFtYUBnbWFpbC5jb20iLCJwcml2cyI6eyI3NjUxNTAwMDAwMSI6WyJFQVJDSElWRV9XUklURSIsIklOQ09NSU5HX0RFU1BBVENIX1JFQUQiLCJJTkNPTUlOR19FSU5WT0lDRV9XUklURSIsIkVBUkNISVZFX1JFQUQiLCJJTkNPTUlOR19FSU5WT0lDRV9SRUFEIiwiQ09NUEFOWV9VU0VSX1JFQUQiLCJPVVRHT0lOR19ERVNQQVRDSF9SRUFEIiwiT1VUR09JTkdfREVTUEFUQ0hfV1JJVEUiLCJPVVRHT0lOR19FSU5WT0lDRV9XUklURSIsIkNPTVBBTllfRURJVCIsIklOQ09NSU5HX0RFU1BBVENIX1dSSVRFIiwiT1VUR09JTkdfRUlOVk9JQ0VfUkVBRCIsIkNPTVBBTllfVVNFUl9XUklURSJdfSwicmxzIjpbXSwiaWF0IjoxNzc0ODczMTE2LCJleHAiOjE3NzQ5NTk1MTZ9.D9t5ZpScV9AX8Ma4RDq3J82B9hytfOnE5duCdXtcC5M"
print(decode_token(t))
